import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.models import StudioTask, ProductionStep, ProductionRun
from backend.app.orchestrator import (create_production_run, get_production_run, list_workflows, pause_production_run, resume_production_run, cancel_production_run)
from backend.app.task_manager import claim_task, complete_task, approve_task


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


def test_workflow_registry_has_ordered_preproduction_graph():
    workflows = list_workflows()
    assert workflows[0]["workflow_key"] == "creative.preproduction"
    steps = workflows[0]["steps"]
    assert len(steps) == 6
    assert steps[2]["approval_required"] is True
    assert steps[4]["approval_required"] is True


def test_run_creation_is_atomic_idempotent_and_conflict_safe(db_session):
    run = create_production_run(
        db_session, "creative.preproduction",
        {"brief": "A short film about memory"}, "production-key-0001",
    )
    assert len(run["steps"]) == 6
    assert run["status"] == "waiting_approval"
    replay = create_production_run(
        db_session, "creative.preproduction",
        {"brief": "A short film about memory"}, "production-key-0001",
    )
    assert replay["id"] == run["id"] and replay["replayed"] is True
    assert len(db_session.scalars(select(ProductionStep)).all()) == 6
    with pytest.raises(HTTPException) as exc:
        create_production_run(
            db_session, "creative.preproduction",
            {"brief": "Different brief"}, "production-key-0001",
        )
    assert exc.value.status_code == 409


def test_dependency_execution_pauses_for_human_approval(db_session):
    run = create_production_run(
        db_session, "creative.preproduction", {"brief": "Test"}, "production-key-0002",
    )
    tasks = {step["step_key"]: step["task_id"] for step in run["steps"]}

    first = claim_task(db_session, "worker-orchestrator")
    assert first["id"] == tasks["research_intake"]
    complete_task(db_session, first["id"], "worker-orchestrator", {"research": "ready"})

    second = claim_task(db_session, "worker-orchestrator")
    assert second["id"] == tasks["story_development"]
    complete_task(db_session, second["id"], "worker-orchestrator", {"story": "draft"})

    assert claim_task(db_session, "worker-orchestrator") is None
    approved = approve_task(db_session, tasks["character_world_bible"])
    assert approved["status"] == "queued"

    third = claim_task(db_session, "worker-orchestrator")
    assert third["id"] == tasks["character_world_bible"]


def test_unknown_workflow_rejected(db_session):
    with pytest.raises(HTTPException) as exc:
        create_production_run(db_session, "unknown.workflow", {}, "production-key-0003")
    assert exc.value.status_code == 422



def test_run_status_is_projected_without_mutating_persisted_run(db_session):
    run = create_production_run(
        db_session, "creative.preproduction", {"brief": "Read-only"}, "production-key-readonly",
    )
    stored = db_session.get(ProductionRun, run["id"])
    assert run["status"] == "waiting_approval"
    assert stored.status == "queued"
    assert not db_session.dirty

    fetched = get_production_run(db_session, run["id"])
    assert fetched["status"] == "waiting_approval"
    assert stored.status == "queued"
    assert not db_session.dirty



def test_run_pause_and_resume_restore_queued_and_approval_states(db_session):
    run = create_production_run(
        db_session, "creative.preproduction", {"brief": "Pause safely"}, "production-key-pause-01",
    )
    task_ids = [step["task_id"] for step in run["steps"]]
    paused = pause_production_run(db_session, run["id"])
    assert paused["status"] == "paused"
    assert all(step["status"] == "paused" for step in paused["steps"])
    assert claim_task(db_session, "worker-paused") is None

    resumed = resume_production_run(db_session, run["id"])
    assert resumed["status"] == "waiting_approval"
    assert [step["status"] for step in resumed["steps"]] == [
        "queued", "queued", "waiting_approval", "queued", "waiting_approval", "queued"
    ]
    assert all(db_session.get(StudioTask, task_id).paused_from_status is None for task_id in task_ids)


def test_run_cancellation_cancels_pending_tasks_and_is_audited(db_session):
    run = create_production_run(
        db_session, "creative.preproduction", {"brief": "Cancel safely"}, "production-key-cancel-01",
    )
    cancelled = cancel_production_run(db_session, run["id"])
    assert cancelled["status"] == "cancelled"
    assert all(step["status"] == "cancelled" for step in cancelled["steps"])


def test_run_cancellation_refuses_while_task_is_running(db_session):
    run = create_production_run(
        db_session, "creative.preproduction", {"brief": "Do not kill active work"}, "production-key-cancel-02",
    )
    claimed = claim_task(db_session, "worker-active")
    assert claimed is not None
    with pytest.raises(HTTPException) as exc:
        cancel_production_run(db_session, run["id"])
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "production_run_has_running_tasks"
