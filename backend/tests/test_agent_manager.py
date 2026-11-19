import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.models import AIProvider, AgentEvent, StudioAgent
from backend.app.agent_schemas import AgentCreate, AgentUpdate, AgentToolsUpdate
from backend.app.agent_manager import (
    create_agent, get_agent, list_agents, replace_agent_tools,
    enable_agent, disable_agent, update_agent,
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


def create_draft(db_session, provider_id=None):
    return create_agent(db_session, AgentCreate(
        slug="research-agent", name="Research Agent",
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
    assert configured["tools"][1]["approval_required"] is True


def test_agent_disable_and_audit_events(db_session):
    p = provider(db_session)
    created = create_draft(db_session, p.id)
    enable_agent(db_session, created["id"])
    disabled = disable_agent(db_session, created["id"])
    assert disabled["status"] == "disabled"
    events = db_session.scalars(select(AgentEvent).where(AgentEvent.agent_id == created["id"])).all()
    assert {e.event_type for e in events} == {"agent_created", "agent_enabled", "agent_disabled"}


def test_agent_slug_conflict_is_structured(db_session):
    create_draft(db_session)
    with pytest.raises(HTTPException) as exc:
        create_draft(db_session)
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "agent_slug_conflict"


def test_agent_tool_grants_cannot_be_changed_while_enabled(db_session):
    p = provider(db_session)
    created = create_draft(db_session, p.id)
    enable_agent(db_session, created["id"])
    with pytest.raises(HTTPException) as exc:
        replace_agent_tools(db_session, created["id"], AgentToolsUpdate(grants=[]))
    assert exc.value.detail["code"] == "disable_agent_before_editing_tools"
