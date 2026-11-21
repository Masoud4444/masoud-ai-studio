import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from uuid import uuid4

from backend.app.database import Base
from backend.app.models import AIProvider, AgentEvent, StudioAgent
from backend.app.agent_schemas import AgentCreate, AgentUpdate, AgentToolsUpdate
from backend.app.agent_manager import (
    create_agent, get_agent, list_agents, replace_agent_tools,
    enable_agent, disable_agent, update_agent, reserve_agent_budget,
    start_agent_budget_reservation, settle_agent_budget_reservation,
    release_agent_budget_reservation,
)


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    try:
        yield db
    finally:
        db.close()
        engine.dispose()


def provider(db_session):
    item = AIProvider(
        name="Agent Test Provider", base_url="https://api.example/v1",
        models_json='["model-a"]', is_enabled=True,
    )
    db_session.add(item)
    db_session.commit()
    return item


def create_draft(db_session, provider_id=None, slug=None):
    return create_agent(db_session, AgentCreate(
        slug=slug or f"research-agent-{uuid4().hex[:8]}", name="Research Agent",
        purpose="Collect and synthesize source-backed research",
        system_prompt="You are a careful research assistant.",
        provider_id=provider_id, model_id="model-a" if provider_id else None,
        permissions=["research.read", "project.read", "ai.generate"],
        monthly_budget_usd=20, max_cost_per_run_usd=1,
    ))


def test_agent_create_starts_draft_and_paginates(db_session):
    created = create_draft(db_session)
    assert created["status"] == "draft"
    assert created["version"] == 1
    assert created["permissions"] == ["research.read", "project.read", "ai.generate"]
    page = list_agents(db_session, status="draft")
    assert page["total"] == 1
    assert page["items"][0]["id"] == created["id"]


def test_agent_enable_requires_registered_enabled_provider_and_model(db_session):
    with pytest.raises(HTTPException) as exc:
        enable_agent(db_session, create_draft(db_session)["id"])
    assert exc.value.detail["code"] == "agent_provider_model_required"

    p = provider(db_session)
    created = create_draft(db_session, p.id)
    enabled = enable_agent(db_session, created["id"])
    assert enabled["status"] == "enabled"
    assert enabled["version"] == 2
    with pytest.raises(HTTPException) as exc2:
        update_agent(db_session, created["id"], AgentUpdate(name="Changed Name"))
    assert exc2.value.detail["code"] == "disable_agent_before_editing"


def test_agent_write_and_execute_tools_require_approval(db_session):
    with pytest.raises(ValidationError):
        AgentToolsUpdate(grants=[{
            "tool_name": "filesystem.write", "permission": "write",
            "approval_required": False,
        }])
    created = create_draft(db_session)
    configured = replace_agent_tools(db_session, created["id"], AgentToolsUpdate(grants=[
        {"tool_name": "research.search", "permission": "read", "approval_required": False},
        {"tool_name": "filesystem.write", "permission": "write", "approval_required": True},
    ]))
    assert len(configured["tools"]) == 2
    assert next(tool for tool in configured["tools"] if tool["tool_name"] == "filesystem.write")["approval_required"] is True


def test_agent_disable_and_audit_events(db_session):
    p = provider(db_session)
    created = create_draft(db_session, p.id)
    enable_agent(db_session, created["id"])
    disabled = disable_agent(db_session, created["id"])
    assert disabled["status"] == "disabled"
    events = db_session.scalars(select(AgentEvent).where(AgentEvent.agent_id == created["id"])).all()
    assert {e.event_type for e in events} == {"agent_created", "agent_enabled", "agent_disabled"}


def test_agent_slug_conflict_is_structured(db_session):
    create_draft(db_session, slug="research-agent-conflict")
    with pytest.raises(HTTPException) as exc:
        create_draft(db_session, slug="research-agent-conflict")
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "agent_slug_conflict"


def test_agent_tool_grants_cannot_be_changed_while_enabled(db_session):
    p = provider(db_session)
    created = create_draft(db_session, p.id)
    enable_agent(db_session, created["id"])
    with pytest.raises(HTTPException) as exc:
        replace_agent_tools(db_session, created["id"], AgentToolsUpdate(grants=[]))
    assert exc.value.detail["code"] == "disable_agent_before_editing_tools"



def test_agent_patch_rejects_null_for_non_nullable_configuration():
    with pytest.raises(ValidationError):
        AgentUpdate(name=None)
    with pytest.raises(ValidationError):
        AgentUpdate(system_prompt=None)


def test_agent_patch_rejects_unknown_permissions():
    with pytest.raises(ValidationError):
        AgentUpdate(permissions=["admin.root"])



def enabled_agent(db_session, monthly_budget=2, per_run=1):
    p = provider(db_session)
    draft = create_agent(db_session, AgentCreate(
        slug="budget-agent", name="Budget Agent",
        purpose="Run budget controlled AI tasks",
        system_prompt="Follow the assigned task and permission boundaries.",
        provider_id=p.id, model_id="model-a",
        monthly_budget_usd=monthly_budget, max_cost_per_run_usd=per_run,
    ))
    enable_agent(db_session, draft["id"])
    return draft["id"]


def test_agent_budget_reservation_is_idempotent_and_settles_actual_cost(db_session):
    agent_id = enabled_agent(db_session)
    request_hash = "a" * 64
    reserved = reserve_agent_budget(db_session, agent_id, "budget-request-0001", request_hash, 1)
    replay = reserve_agent_budget(db_session, agent_id, "budget-request-0001", request_hash, 1)
    assert reserved["status"] == "reserved"
    assert replay["id"] == reserved["id"]
    assert replay["replayed"] is True

    started = start_agent_budget_reservation(db_session, reserved["id"])
    assert started["status"] == "running"
    settled = settle_agent_budget_reservation(db_session, reserved["id"], 0.35)
    assert settled["status"] == "succeeded"
    assert settled["actual_cost_usd"] == 0.35


def test_agent_budget_rejects_key_reuse_and_monthly_overspend(db_session):
    agent_id = enabled_agent(db_session, monthly_budget=1, per_run=1)
    reserve_agent_budget(db_session, agent_id, "budget-request-0002", "b" * 64, 0.8)
    with pytest.raises(HTTPException) as conflict:
        reserve_agent_budget(db_session, agent_id, "budget-request-0002", "c" * 64, 0.8)
    assert conflict.value.detail["code"] == "idempotency_key_conflict"

    with pytest.raises(HTTPException) as over:
        reserve_agent_budget(db_session, agent_id, "budget-request-0003", "d" * 64, 0.3)
    assert over.value.detail["code"] == "agent_monthly_budget_exceeded"


def test_agent_budget_reservation_enforces_per_run_ceiling_and_release(db_session):
    agent_id = enabled_agent(db_session, monthly_budget=5, per_run=0.5)
    with pytest.raises(HTTPException) as over:
        reserve_agent_budget(db_session, agent_id, "budget-request-0004", "e" * 64, 0.6)
    assert over.value.detail["code"] == "agent_per_run_budget_exceeded"

    reservation = reserve_agent_budget(db_session, agent_id, "budget-request-0005", "f" * 64, 0.4)
    released = release_agent_budget_reservation(db_session, reservation["id"])
    assert released["status"] == "released"
    with pytest.raises(HTTPException) as invalid:
        settle_agent_budget_reservation(db_session, reservation["id"], 0.1)
    assert invalid.value.detail["code"] == "agent_budget_reservation_not_settleable"


def test_agent_budget_cannot_settle_above_reserved_amount(db_session):
    agent_id = enabled_agent(db_session)
    reservation = reserve_agent_budget(db_session, agent_id, "budget-request-0006", "1" * 64, 0.5)
    start_agent_budget_reservation(db_session, reservation["id"])
    with pytest.raises(HTTPException) as over:
        settle_agent_budget_reservation(db_session, reservation["id"], 0.6)
    assert over.value.detail["code"] == "actual_cost_exceeds_reserved_budget"



def test_agent_budget_reservation_cannot_start_after_agent_is_disabled(db_session):
    agent_id = enabled_agent(db_session)
    reservation = reserve_agent_budget(db_session, agent_id, "budget-request-0007", "2" * 64, 0.5)
    disable_agent(db_session, agent_id)
    with pytest.raises(HTTPException) as exc:
        start_agent_budget_reservation(db_session, reservation["id"])
    assert exc.value.detail["code"] == "agent_not_enabled"



def test_agent_budget_start_is_idempotent_for_running_reservation(db_session):
    agent_id = enabled_agent(db_session)
    reservation = reserve_agent_budget(
        db_session, agent_id, "budget-request-recovery-01", "3" * 64, 0.5
    )
    first = start_agent_budget_reservation(db_session, reservation["id"])
    replay = start_agent_budget_reservation(db_session, reservation["id"])
    assert first["status"] == "running"
    assert replay["status"] == "running"
    assert replay["replayed"] is True
    events = db_session.scalars(
        select(AgentEvent).where(
            AgentEvent.agent_id == agent_id,
            AgentEvent.event_type == "budget_execution_started",
        )
    ).all()
    assert len(events) == 1


def test_agent_budget_settlement_is_idempotent_but_immutable(db_session):
    agent_id = enabled_agent(db_session)
    reservation = reserve_agent_budget(
        db_session, agent_id, "budget-request-settle-01", "4" * 64, 0.5
    )
    start_agent_budget_reservation(db_session, reservation["id"])
    first = settle_agent_budget_reservation(db_session, reservation["id"], 0.2)
    replay = settle_agent_budget_reservation(db_session, reservation["id"], 0.2)
    assert first["status"] == "succeeded"
    assert replay["status"] == "succeeded"
    assert replay["replayed"] is True
    with pytest.raises(HTTPException) as conflict:
        settle_agent_budget_reservation(db_session, reservation["id"], 0.3)
    assert conflict.value.detail["code"] == "agent_budget_reservation_already_settled"
