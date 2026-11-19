"""Durable task lifecycle primitives for the local-first production orchestrator."""
import hashlib
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Project, StudioTask, TaskDependency, TaskEvent, ProductionRun, ProductionStep


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _lease_is_valid(task: StudioTask) -> bool:
    expires = task.lease_expires_at
    if expires is None:
        return False
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    return expires > _now()


def _event(db: Session, task_id: str, event_type: str, before: str | None,
           after: str | None, detail: dict | None = None) -> None:
    db.add(TaskEvent(
        id=str(uuid4()), task_id=task_id, event_type=event_type,
        from_status=before, to_status=after,
        detail_json=json.dumps(detail or {}, ensure_ascii=False, separators=(",", ":")),
    ))



def _hold_retry_for_paused_run(db: Session, task: StudioTask) -> bool:
    """Keep a retried production step paused while its parent run is pausing/paused."""
    run_status = db.scalar(
        select(ProductionRun.status)
        .join(ProductionStep, ProductionStep.run_id == ProductionRun.id)
        .where(ProductionStep.task_id == task.id)
    )
    if run_status not in {"pausing", "paused"}:
        return False
    task.paused_from_status = "queued"
    task.status = "paused"
    return True


def serialize_task(task: StudioTask, include_payload: bool = True) -> dict:
    result = {
        "id": task.id, "project_id": task.project_id, "task_type": task.task_type,
        "status": task.status, "priority": task.priority, "attempt_count": task.attempt_count,
        "max_attempts": task.max_attempts, "available_at": task.available_at,
        "lease_expires_at": task.lease_expires_at, "locked_by": task.locked_by,
        "error_code": task.error_code, "error_message": task.error_message,
        "created_at": task.created_at, "updated_at": task.updated_at,
        "started_at": task.started_at, "finished_at": task.finished_at,
        "result": json.loads(task.result_json) if task.result_json else None,
    }
    if include_payload:
        result["payload"] = json.loads(task.payload_json)
    return result


def _request_hash(task_type: str, project_id: str | None, priority: int,
                  payload: dict, dependencies: list[str], max_attempts: int) -> str:
    canonical = json.dumps({
        "task_type": task_type, "project_id": project_id, "priority": priority,
        "payload": payload, "dependencies": sorted(dependencies),
        "max_attempts": max_attempts,
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def create_task(db: Session, task_type: str, payload: dict, idempotency_key: str,
                project_id: str | None = None, priority: int = 100,
                dependencies: list[str] | None = None, max_attempts: int = 3,
                depends_on: list[str] | None = None) -> dict:
    # `depends_on` is retained as a compatibility alias for direct callers.
    if dependencies is not None and depends_on is not None and set(dependencies) != set(depends_on):
        raise HTTPException(status_code=422, detail={"code": "conflicting_task_dependencies"})
    dependencies = list(dict.fromkeys(dependencies if dependencies is not None else (depends_on or [])))
    if not idempotency_key or len(idempotency_key) > 200:
        raise HTTPException(status_code=422, detail={"code": "invalid_idempotency_key"})
    key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    request_hash = _request_hash(task_type, project_id, priority, payload, dependencies, max_attempts)
    existing = db.scalar(select(StudioTask).where(StudioTask.idempotency_hash == key_hash))
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(status_code=409, detail={"code": "idempotency_key_conflict"})
        return {**serialize_task(existing), "replayed": True}

    if project_id and db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail={"code": "project_not_found"})
    if len(dependencies) > 100:
        raise HTTPException(status_code=422, detail={"code": "too_many_task_dependencies"})
    if dependencies:
        found = set(db.scalars(select(StudioTask.id).where(StudioTask.id.in_(dependencies))).all())
        if found != set(dependencies):
            raise HTTPException(status_code=404, detail={"code": "task_dependency_not_found"})

    now = _now()
    task = StudioTask(
        id=str(uuid4()), project_id=project_id, task_type=task_type,
        status="queued", priority=priority,
        payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        request_hash=request_hash, idempotency_hash=key_hash,
        max_attempts=max_attempts, available_at=now, created_at=now, updated_at=now,
    )
    db.add(task)
    try:
        db.flush()
        for dependency_id in dependencies:
            db.add(TaskDependency(
                id=str(uuid4()), task_id=task.id, depends_on_task_id=dependency_id,
                created_at=now,
            ))
        _event(db, task.id, "created", None, "queued", {"dependency_count": len(dependencies)})
        db.commit()
        db.refresh(task)
    except IntegrityError:
        db.rollback()
        raced = db.scalar(select(StudioTask).where(StudioTask.idempotency_hash == key_hash))
        if raced and raced.request_hash == request_hash:
            return {**serialize_task(raced), "replayed": True}
        if raced:
            raise HTTPException(status_code=409, detail={"code": "idempotency_key_conflict"})
        raise HTTPException(status_code=409, detail={"code": "task_dependency_conflict"})
    return {**serialize_task(task), "replayed": False}


def get_task(db: Session, task_id: str) -> dict:
    task = db.get(StudioTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "task_not_found"})
    dependencies = db.scalars(
        select(TaskDependency.depends_on_task_id).where(TaskDependency.task_id == task_id)
    ).all()
    return {**serialize_task(task), "depends_on": dependencies}


def list_tasks(db: Session, limit: int = 50, offset: int = 0,
               status: str | None = None, project_id: str | None = None) -> dict:
    query = select(StudioTask)
    count_query = select(func.count()).select_from(StudioTask)
    if status:
        query = query.where(StudioTask.status == status)
        count_query = count_query.where(StudioTask.status == status)
    if project_id:
        query = query.where(StudioTask.project_id == project_id)
        count_query = count_query.where(StudioTask.project_id == project_id)
    total = db.scalar(count_query) or 0
    rows = db.scalars(query.order_by(StudioTask.priority.asc(), StudioTask.created_at.desc())
                      .offset(offset).limit(limit)).all()
    return {"items": [serialize_task(row) for row in rows], "total": total,
            "limit": limit, "offset": offset}


def cancel_task(db: Session, task_id: str) -> dict:
    task = db.get(StudioTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "task_not_found"})
    if task.status not in {"queued", "blocked", "waiting_approval"}:
        raise HTTPException(status_code=409, detail={"code": "task_not_cancellable", "status": task.status})
    before = task.status
    task.status = "cancelled"
    task.finished_at = _now()
    task.updated_at = _now()
    task.lease_expires_at = None
    task.locked_by = None
    _event(db, task.id, "cancelled", before, "cancelled")
    db.commit()
    db.refresh(task)
    return serialize_task(task)


def retry_task(db: Session, task_id: str) -> dict:
    task = db.get(StudioTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "task_not_found"})
    if task.status not in {"failed", "blocked"}:
        raise HTTPException(status_code=409, detail={"code": "task_not_retryable", "status": task.status})
    if task.attempt_count >= task.max_attempts:
        raise HTTPException(status_code=409, detail={"code": "task_attempt_limit_reached"})
    before = task.status
    task.status = "queued"
    task.available_at = _now()
    _hold_retry_for_paused_run(db, task)
    task.finished_at = None
    task.error_code = None
    task.error_message = None
    task.updated_at = _now()
    _event(db, task.id, "manual_retry", before, task.status)
    db.commit()
    db.refresh(task)
    return serialize_task(task)


def claim_task(db: Session, worker_id: str, lease_seconds: int = 120,
               task_types: list[str] | None = None) -> dict | None:
    """Claim one eligible task. SQLite deployments should run a single worker process."""
    if not worker_id or len(worker_id) > 120 or not 10 <= lease_seconds <= 3600:
        raise HTTPException(status_code=422, detail={"code": "invalid_worker_claim"})
    now = _now()
    candidate_query = select(StudioTask).where(
        StudioTask.status == "queued", StudioTask.available_at <= now,
        StudioTask.attempt_count < StudioTask.max_attempts,
    )
    if task_types is not None:
        if not task_types:
            return None
        candidate_query = candidate_query.where(StudioTask.task_type.in_(task_types))
    candidates = db.scalars(
        candidate_query.order_by(StudioTask.priority.asc(), StudioTask.created_at.asc())
        .limit(100).with_for_update(skip_locked=True)
    ).all()
    for task in candidates:
        dependencies = db.scalars(
            select(StudioTask.status).join(
                TaskDependency, TaskDependency.depends_on_task_id == StudioTask.id
            ).where(TaskDependency.task_id == task.id)
        ).all()
        if any(state in {"failed", "cancelled", "blocked"} for state in dependencies):
            before = task.status
            task.status = "blocked"
            task.finished_at = now
            task.error_code = "dependency_failed"
            task.error_message = "A prerequisite task did not succeed"
            _event(db, task.id, "dependency_blocked", before, "blocked")
            continue
        if any(state != "succeeded" for state in dependencies):
            continue
        before = task.status
        task.status = "running"
        task.attempt_count += 1
        task.started_at = task.started_at or now
        task.lease_expires_at = now + timedelta(seconds=lease_seconds)
        task.locked_by = worker_id
        task.updated_at = now
        _event(db, task.id, "claimed", before, "running", {"worker_id": worker_id})
        db.commit()
        db.refresh(task)
        return serialize_task(task)
    db.commit()
    return None


def complete_task(db: Session, task_id: str, worker_id: str, result: dict) -> dict:
    task = db.get(StudioTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "task_not_found"})
    if task.status != "running" or task.locked_by != worker_id or not _lease_is_valid(task):
        raise HTTPException(status_code=409, detail={"code": "task_lease_not_owned"})
    before = task.status
    task.status = "succeeded"
    task.result_json = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    task.finished_at = _now()
    task.updated_at = _now()
    task.lease_expires_at = None
    task.locked_by = None
    task.error_code = None
    task.error_message = None
    _event(db, task.id, "completed", before, "succeeded")
    db.commit()
    db.refresh(task)
    return serialize_task(task)


def fail_task(db: Session, task_id: str, worker_id: str, error_code: str,
              error_message: str, retry_delay_seconds: int = 30) -> dict:
    task = db.get(StudioTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "task_not_found"})
    if task.status != "running" or task.locked_by != worker_id or not _lease_is_valid(task):
        raise HTTPException(status_code=409, detail={"code": "task_lease_not_owned"})
    if not 0 <= retry_delay_seconds <= 86400:
        raise HTTPException(status_code=422, detail={"code": "invalid_retry_delay"})
    before = task.status
    retry = task.attempt_count < task.max_attempts
    task.status = "queued" if retry else "failed"
    task.available_at = _now() + timedelta(seconds=retry_delay_seconds) if retry else task.available_at
    if retry:
        _hold_retry_for_paused_run(db, task)
    task.finished_at = None if retry else _now()
    task.lease_expires_at = None
    task.locked_by = None
    task.error_code = (error_code or "task_failed")[:80]
    task.error_message = (error_message or "Task execution failed")[:500]
    task.updated_at = _now()
    _event(db, task.id, "retry_scheduled" if retry else "failed", before, task.status,
           {"error_code": task.error_code})
    db.commit()
    db.refresh(task)
    return serialize_task(task)


def recover_expired_leases(db: Session) -> int:
    now = _now()
    expired = db.scalars(select(StudioTask).where(
        StudioTask.status == "running", StudioTask.lease_expires_at <= now
    )).all()
    recovered = 0
    for task in expired:
        before = task.status
        retry = task.attempt_count < task.max_attempts
        task.status = "queued" if retry else "failed"
        task.available_at = now if retry else task.available_at
        if retry:
            _hold_retry_for_paused_run(db, task)
        task.finished_at = None if retry else now
        task.lease_expires_at = None
        task.locked_by = None
        task.error_code = "lease_expired"
        task.error_message = "Worker lease expired before task completion"
        task.updated_at = now
        _event(db, task.id, "lease_recovered", before, task.status)
        recovered += 1
    if recovered:
        db.commit()
    return recovered



def approve_task(db: Session, task_id: str, reviewer: str = "local_owner") -> dict:
    task = db.get(StudioTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "task_not_found"})
    if task.status != "waiting_approval":
        raise HTTPException(status_code=409, detail={"code": "task_not_waiting_for_approval", "status": task.status})
    before = task.status
    task.status = "queued"
    task.updated_at = _now()
    task.error_code = None
    task.error_message = None
    _event(db, task.id, "human_approved", before, "queued", {"reviewer": reviewer[:120]})
    db.commit()
    db.refresh(task)
    return serialize_task(task)


def reject_task_approval(db: Session, task_id: str, reason: str = "Human approval rejected") -> dict:
    task = db.get(StudioTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "task_not_found"})
    if task.status != "waiting_approval":
        raise HTTPException(status_code=409, detail={"code": "task_not_waiting_for_approval", "status": task.status})
    before = task.status
    task.status = "cancelled"
    task.finished_at = _now()
    task.updated_at = _now()
    task.error_code = "approval_rejected"
    task.error_message = (reason or "Human approval rejected")[:500]
    _event(db, task.id, "human_rejected", before, "cancelled", {"reason": task.error_message})
    db.commit()
    db.refresh(task)
    return serialize_task(task)



def renew_task_lease(db: Session, task_id: str, worker_id: str,
                     lease_seconds: int = 120) -> bool:
    """Extend a live lease only while the caller still owns an unexpired task."""
    if not worker_id or len(worker_id) > 120 or not 10 <= lease_seconds <= 3600:
        raise HTTPException(status_code=422, detail={"code": "invalid_worker_lease"})
    task = db.get(StudioTask, task_id)
    if task is None or task.status != "running" or task.locked_by != worker_id:
        return False
    now = _now()
    if not _lease_is_valid(task):
        return False
    task.lease_expires_at = now + timedelta(seconds=lease_seconds)
    task.updated_at = now
    _event(db, task.id, "lease_renewed", "running", "running",
           {"worker_id": worker_id, "lease_seconds": lease_seconds})
    db.commit()
    return True
