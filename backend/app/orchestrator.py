"""Deterministic production workflow planning and atomic run creation."""
import hashlib
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import Project, ProductionRun, ProductionStep, StudioTask, TaskDependency, TaskEvent


WORKFLOWS = {
    "creative.preproduction": {
        "version": 1,
        "description": "Research, story, character/world, visual development, storyboard, and production handoff.",
        "steps": [
            {"key": "research_intake", "task_type": "research.intake", "depends_on": [], "approval_required": False},
            {"key": "story_development", "task_type": "story.development", "depends_on": ["research_intake"], "approval_required": False},
            {"key": "character_world_bible", "task_type": "story.character_world_bible", "depends_on": ["story_development"], "approval_required": True},
            {"key": "visual_development", "task_type": "visual.development", "depends_on": ["character_world_bible"], "approval_required": False},
            {"key": "storyboard", "task_type": "visual.storyboard", "depends_on": ["visual_development"], "approval_required": True},
            {"key": "production_handoff", "task_type": "production.handoff", "depends_on": ["storyboard"], "approval_required": False},
        ],
    }
}


def _now():
    return datetime.now(timezone.utc)


def list_workflows():
    return [
        {"workflow_key": key, "version": spec["version"],
         "description": spec["description"],
         "steps": [{"key": s["key"], "task_type": s["task_type"],
                    "depends_on": s["depends_on"],
                    "approval_required": s["approval_required"]} for s in spec["steps"]]}
        for key, spec in WORKFLOWS.items()
    ]


def _run_payload(run: ProductionRun, db: Session, replayed: bool = False) -> dict:
    rows = db.execute(
        select(ProductionStep, StudioTask)
        .join(StudioTask, StudioTask.id == ProductionStep.task_id)
        .where(ProductionStep.run_id == run.id)
        .order_by(ProductionStep.position.asc())
    ).all()
    steps = []
    states = []
    for step, task in rows:
        states.append(task.status)
        steps.append({
            "step_key": step.step_key, "task_id": task.id,
            "task_type": task.task_type, "position": step.position,
            "status": task.status, "approval_required": step.approval_required,
            "depends_on": db.scalars(select(TaskDependency.depends_on_task_id)
                .where(TaskDependency.task_id == task.id)).all(),
            "error_code": task.error_code,
        })
    if states and all(s == "succeeded" for s in states):
        status = "succeeded"
    elif any(s in {"failed", "cancelled"} for s in states):
        status = "failed"
    elif any(s == "running" for s in states):
        status = "running"
    elif any(s == "waiting_approval" for s in states):
        status = "waiting_approval"
    elif any(s == "blocked" for s in states):
        status = "blocked"
    else:
        status = "queued"
    if run.status != status:
        run.status = status
        run.updated_at = _now()
        db.commit()
    return {
        "id": run.id, "project_id": run.project_id,
        "workflow_key": run.workflow_key, "workflow_version": run.workflow_version,
        "status": status, "inputs": json.loads(run.input_json),
        "steps": steps, "created_at": run.created_at,
        "updated_at": run.updated_at, "replayed": replayed,
    }


def create_production_run(db: Session, workflow_key: str, inputs: dict,
                          idempotency_key: str, project_id: str | None = None) -> dict:
    spec = WORKFLOWS.get(workflow_key)
    if spec is None:
        raise HTTPException(status_code=422, detail={"code": "unknown_workflow"})
    if not idempotency_key or len(idempotency_key) > 200:
        raise HTTPException(status_code=422, detail={"code": "invalid_idempotency_key"})
    key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    canonical = json.dumps({
        "workflow_key": workflow_key, "workflow_version": spec["version"],
        "project_id": project_id, "inputs": inputs,
    }, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    request_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    existing = db.scalar(select(ProductionRun).where(ProductionRun.idempotency_hash == key_hash))
    if existing:
        if existing.request_hash != request_hash:
            raise HTTPException(status_code=409, detail={"code": "idempotency_key_conflict"})
        return _run_payload(existing, db, replayed=True)
    if project_id and db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail={"code": "project_not_found"})

    now = _now()
    run_id = str(uuid4())
    run = ProductionRun(
        id=run_id, project_id=project_id, workflow_key=workflow_key,
        workflow_version=spec["version"], status="queued",
        input_json=json.dumps(inputs, ensure_ascii=False, separators=(",", ":")),
        idempotency_hash=key_hash, request_hash=request_hash,
        created_at=now, updated_at=now,
    )
    db.add(run)
    task_ids = {}
    try:
        for position, step in enumerate(spec["steps"]):
            task_id = str(uuid4())
            task_ids[step["key"]] = task_id
            payload = {
                "production_run_id": run_id,
                "step_key": step["key"],
                "inputs": inputs,
            }
            task_key = hashlib.sha256(f"{run_id}:{step['key']}".encode()).hexdigest()
            task_hash = hashlib.sha256(json.dumps({
                "task_type": step["task_type"], "payload": payload,
                "dependencies": step["depends_on"], "position": position,
            }, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()
            task = StudioTask(
                id=task_id, project_id=project_id, task_type=step["task_type"],
                status="waiting_approval" if step["approval_required"] else "queued",
                priority=100, payload_json=json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                request_hash=task_hash, idempotency_hash=task_key,
                max_attempts=3, attempt_count=0, available_at=now,
                created_at=now, updated_at=now,
            )
            db.add(task)
            db.add(ProductionStep(
                id=str(uuid4()), run_id=run_id, step_key=step["key"],
                task_id=task_id, position=position,
                approval_required=step["approval_required"], created_at=now,
            ))
            db.add(TaskEvent(
                id=str(uuid4()), task_id=task_id, event_type="created_by_orchestrator",
                from_status=None, to_status=task.status,
                detail_json=json.dumps({"run_id": run_id, "step_key": step["key"]}),
                created_at=now,
            ))
        for step in spec["steps"]:
            for dependency_key in step["depends_on"]:
                db.add(TaskDependency(
                    id=str(uuid4()), task_id=task_ids[step["key"]],
                    depends_on_task_id=task_ids[dependency_key], created_at=now,
                ))
        db.commit()
        db.refresh(run)
    except IntegrityError:
        db.rollback()
        raced = db.scalar(select(ProductionRun).where(ProductionRun.idempotency_hash == key_hash))
        if raced and raced.request_hash == request_hash:
            return _run_payload(raced, db, replayed=True)
        if raced:
            raise HTTPException(status_code=409, detail={"code": "idempotency_key_conflict"})
        raise HTTPException(status_code=409, detail={"code": "production_run_conflict"})
    return _run_payload(run, db, replayed=False)


def get_production_run(db: Session, run_id: str) -> dict:
    run = db.get(ProductionRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"code": "production_run_not_found"})
    return _run_payload(run, db)


def list_production_runs(db: Session, limit: int = 50, offset: int = 0,
                         project_id: str | None = None) -> dict:
    query = select(ProductionRun)
    if project_id:
        query = query.where(ProductionRun.project_id == project_id)
    total = len(db.scalars(query).all())
    rows = db.scalars(query.order_by(ProductionRun.created_at.desc())
                      .offset(offset).limit(limit)).all()
    return {"items": [_run_payload(row, db) for row in rows],
            "total": total, "limit": limit, "offset": offset}
