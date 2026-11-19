import pytest
import time
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.task_manager import create_task, get_task
from backend.app.worker import TaskHandlerRegistry, WorkerSupervisor


@pytest.fixture()
def session_factory():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()


def add_task(factory, task_type, key, payload=None):
    db = factory()
    try:
        return create_task(db, task_type, payload or {}, key)
    finally:
        db.close()


def read_task(factory, task_id):
    db = factory()
    try:
        return get_task(db, task_id)
    finally:
        db.close()


def test_registry_validates_and_deduplicates_handlers():
    registry = TaskHandlerRegistry()
    registry.register("system.healthcheck", lambda payload: {"ok": True})
    assert registry.task_types == ["system.healthcheck"]
    with pytest.raises(ValueError):
        registry.register("system.healthcheck", lambda payload: {})
    with pytest.raises(ValueError):
        registry.register("../unsafe", lambda payload: {})


def test_worker_only_claims_registered_task_types(session_factory):
    unsupported = add_task(session_factory, "story.development", "worker-unsupported")
    supported = add_task(session_factory, "system.healthcheck", "worker-supported")
    registry = TaskHandlerRegistry()
    registry.register("system.healthcheck", lambda payload: {"ok": True})
    worker = WorkerSupervisor(session_factory, "worker-test", registry, poll_interval_seconds=0.1)

    assert worker.run_once() is True
    assert read_task(session_factory, supported["id"])["status"] == "succeeded"
    assert read_task(session_factory, unsupported["id"])["status"] == "queued"


def test_worker_sanitizes_handler_exceptions(session_factory):
    task = add_task(session_factory, "system.failure", "worker-failure")
    registry = TaskHandlerRegistry()

    def fail(_payload):
        raise RuntimeError("secret=do-not-persist prompt body")

    registry.register("system.failure", fail)
    worker = WorkerSupervisor(session_factory, "worker-test", registry, poll_interval_seconds=0.1)
    worker.run_once()
    result = read_task(session_factory, task["id"])
    assert result["status"] == "queued"
    assert result["error_code"] == "handler_error"
    assert "secret" not in result["error_message"]



def test_worker_renews_lease_for_long_running_handler(session_factory):
    task = add_task(session_factory, "system.slow", "worker-slow")
    registry = TaskHandlerRegistry()

    def slow_handler(_payload):
        time.sleep(4.2)
        return {"completed": True}

    registry.register("system.slow", slow_handler)
    worker = WorkerSupervisor(
        session_factory, "worker-slow", registry,
        lease_seconds=10, poll_interval_seconds=0.1,
    )
    assert worker.run_once() is True
    assert read_task(session_factory, task["id"])["status"] == "succeeded"

    db = session_factory()
    try:
        from backend.app.models import TaskEvent
        events = db.query(TaskEvent).filter_by(task_id=task["id"], event_type="lease_renewed").all()
        assert len(events) >= 1
    finally:
        db.close()
