import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.task_manager import (
    create_task, claim_task, complete_task, fail_task, retry_task,
    recover_expired_leases, cancel_task,
)
from backend.app.models import StudioTask
from datetime import datetime, timedelta, timezone


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    db = Session()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def create(db, key, **kwargs):
    return create_task(
        db, task_type=kwargs.pop("task_type", "research.collect"),
        payload=kwargs.pop("payload", {"query": "test"}),
        idempotency_key=key, **kwargs,
    )


def test_task_creation_is_idempotent_and_detects_conflicts(db_session):
    first = create(db_session, "task-key-0001")
    replay = create(db_session, "task-key-0001")
    assert first["id"] == replay["id"]
    assert replay["replayed"] is True
    with pytest.raises(HTTPException) as exc:
        create(db_session, "task-key-0001", payload={"query": "different"})
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "idempotency_key_conflict"


def test_dependency_blocks_claim_until_prerequisite_succeeds(db_session):
    parent = create(db_session, "task-parent-01")
    child = create(db_session, "task-child-001", depends_on=[parent["id"]])
    claimed_parent = claim_task(db_session, "worker-a")
    assert claimed_parent["id"] == parent["id"]
    assert claim_task(db_session, "worker-a") is None
    complete_task(db_session, parent["id"], "worker-a", {"artifact_id": "asset-1"})
    claimed_child = claim_task(db_session, "worker-a")
    assert claimed_child["id"] == child["id"]


def test_failed_dependency_marks_child_blocked(db_session):
    parent = create(db_session, "task-parent-02", max_attempts=1)
    child = create(db_session, "task-child-002", depends_on=[parent["id"]])
    claim_task(db_session, "worker-b")
    fail_task(db_session, parent["id"], "worker-b", "provider_error", "Provider unavailable", 0)
    assert claim_task(db_session, "worker-b") is None
    assert db_session.get(StudioTask, child["id"]).status == "blocked"


def test_retry_budget_and_lease_recovery(db_session):
    task = create(db_session, "task-retry-001", max_attempts=2)
    claim_task(db_session, "worker-c")
    fail_task(db_session, task["id"], "worker-c", "temporary", "Temporary failure", 0)
    claim_task(db_session, "worker-c")
    failed = fail_task(db_session, task["id"], "worker-c", "temporary", "Still failing", 0)
    assert failed["status"] == "failed"
    with pytest.raises(HTTPException):
        retry_task(db_session, task["id"])

    recoverable = create(db_session, "task-recover-01", max_attempts=2)
    claimed = claim_task(db_session, "worker-d", lease_seconds=10)
    assert claimed["id"] == recoverable["id"]
    row = db_session.get(StudioTask, recoverable["id"])
    row.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db_session.commit()
    assert recover_expired_leases(db_session) == 1
    assert row.status == "queued" and row.locked_by is None


def test_queued_task_can_be_cancelled_but_running_task_cannot(db_session):
    queued = create(db_session, "task-cancel-01")
    assert cancel_task(db_session, queued["id"])["status"] == "cancelled"
    running = create(db_session, "task-cancel-02")
    claim_task(db_session, "worker-e")
    with pytest.raises(HTTPException) as exc:
        cancel_task(db_session, running["id"])
    assert exc.value.status_code == 409



def test_naive_sqlite_lease_timestamp_is_accepted_for_completion(db_session):
    task = create(db_session, "task-naive-complete")
    claimed = claim_task(db_session, "worker-naive")
    assert claimed["id"] == task["id"]
    row = db_session.get(StudioTask, task["id"])
    row.lease_expires_at = (datetime.now(timezone.utc) + timedelta(minutes=1)).replace(tzinfo=None)
    db_session.commit()
    completed = complete_task(db_session, task["id"], "worker-naive", {"ok": True})
    assert completed["status"] == "succeeded"


def test_naive_sqlite_lease_timestamp_is_accepted_for_failure(db_session):
    task = create(db_session, "task-naive-fail", max_attempts=1)
    claimed = claim_task(db_session, "worker-naive-fail")
    assert claimed["id"] == task["id"]
    row = db_session.get(StudioTask, task["id"])
    row.lease_expires_at = (datetime.now(timezone.utc) + timedelta(minutes=1)).replace(tzinfo=None)
    db_session.commit()
    failed = fail_task(db_session, task["id"], "worker-naive-fail", "test_error", "expected", 0)
    assert failed["status"] == "failed"



def test_worker_lease_renewal_requires_live_owner(db_session):
    from backend.app.task_manager import renew_task_lease
    task = create(db_session, "task-lease-renewal")
    claimed = claim_task(db_session, "worker-renewal", lease_seconds=10)
    assert claimed["id"] == task["id"]
    assert renew_task_lease(db_session, task["id"], "another-worker", 10) is False
    assert renew_task_lease(db_session, task["id"], "worker-renewal", 10) is True
    row = db_session.get(StudioTask, task["id"])
    assert row.lease_expires_at > datetime.now(timezone.utc)
