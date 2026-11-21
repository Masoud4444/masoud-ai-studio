import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.task_manager import create_task, get_task, claim_task, update_task_execution, list_task_events


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    Base.metadata.create_all(engine)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        Base.metadata.drop_all(engine)
        engine.dispose()


def test_cloud_job_mode_and_remote_identity_survive_task_reload(db_session):
    created = create_task(db_session, "animation.render", {"scene_count": 4}, "cloud-mode-test-001",
                          execution_mode="cloud", estimated_duration_seconds=90,
                          payload_size_bytes=2048, cloud_recommended=True)
    assert created["execution_mode"] == "cloud"
    assert created["progress_stage"] == "queued"
    assert "_studio_execution" not in created["payload"]
    assert claim_task(db_session, "local-worker", execution_modes=["local"]) is None
    claimed = claim_task(db_session, "cloud-worker", execution_modes=["cloud"])
    assert claimed["id"] == created["id"]
    updated = update_task_execution(db_session, created["id"], "cloud-worker",
        remote_job_id="remote_job_123", progress_stage="processing", progress_percent=45,
        estimated_cost_usd=0.125)
    reloaded = get_task(db_session, created["id"])
    assert updated["remote_job_id"] == "remote_job_123"
    assert reloaded["progress_stage"] == "processing"
    assert reloaded["progress_percent"] == 45
    assert reloaded["estimated_cost_usd"] == 0.125
    assert reloaded["payload"] == {"scene_count": 4}
    events = list_task_events(db_session, created["id"])
    assert any(event["event_type"] == "execution_progress" for event in events)


def test_execution_progress_requires_current_worker_lease(db_session):
    created = create_task(db_session, "video.render", {}, "cloud-mode-test-002", execution_mode="cloud")
    claim_task(db_session, "actual-worker", execution_modes=["cloud"])
    with pytest.raises(HTTPException) as error:
        update_task_execution(db_session, created["id"], "other-worker",
                              progress_stage="processing", progress_percent=20)
    assert error.value.status_code == 409


def test_worker_dispatches_cloud_mode_through_cloud_handler(db_session):
    from backend.app.worker import TaskHandlerRegistry, WorkerSupervisor
    factory = sessionmaker(bind=db_session.get_bind(), expire_on_commit=False)
    created = create_task(db_session, "animation.render", {"frames": 24},
                          "cloud-worker-dispatch-003", execution_mode="cloud")
    registry = TaskHandlerRegistry()
    registry.register_cloud_handler(lambda payload: {
        "received_task_id": payload["_studio_task"]["id"], "rendered": True,
    })
    worker = WorkerSupervisor(factory, "cloud-dispatch-worker", registry)
    assert worker.run_once() is True
    db_session.expire_all()
    completed = get_task(db_session, created["id"])
    assert completed["status"] == "succeeded"
    assert completed["result"]["rendered"] is True
