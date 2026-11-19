import asyncio

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.models import AIModelPricing, AIProvider
from backend.app.agent_manager import create_agent, enable_agent
from backend.app.agent_schemas import AgentCreate
from backend.app.agent_runtime import run_agent


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


def configured_agent(db, permissions=None):
    provider = AIProvider(
        name="Runtime Test Provider",
        base_url="https://api.example/v1",
        models_json='["runtime-model"]',
        is_enabled=True,
    )
    db.add(provider)
    db.flush()
    db.add(AIModelPricing(
        provider_id=provider.id,
        model_id="runtime-model",
        input_usd_per_million=1,
        output_usd_per_million=2,
        version=1,
    ))
    db.commit()
    created = create_agent(db, AgentCreate(
        slug="runtime-agent",
        name="Runtime Agent",
        purpose="Execute bounded text generation requests",
        system_prompt="Be concise and accurate.",
        provider_id=provider.id,
        model_id="runtime-model",
        permissions=permissions if permissions is not None else ["ai.generate"],
        monthly_budget_usd=5,
        max_cost_per_run_usd=1,
        max_output_tokens=100,
    ))
    enable_agent(db, created["id"])
    return created["id"]


def test_runtime_requires_ai_generate_permission(db_session):
    agent_id = configured_agent(db_session, permissions=["research.read"])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(run_agent(db_session, agent_id, "Research this", "runtime-key-0001"))
    assert exc.value.status_code == 403
    assert exc.value.detail["code"] == "agent_permission_denied"


def test_runtime_requires_configured_model_pricing(db_session):
    agent_id = configured_agent(db_session)
    db_session.query(AIModelPricing).delete()
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        asyncio.run(run_agent(db_session, agent_id, "Research this", "runtime-key-0002"))
    assert exc.value.status_code == 409
    assert exc.value.detail["code"] == "agent_model_pricing_required"


def test_runtime_reserves_budget_and_replays_stored_gateway_result(db_session, monkeypatch):
    agent_id = configured_agent(db_session)
    calls = []

    async def fake_gateway(_db, _payload, _key):
        calls.append(_key)
        return {
            "id": "gateway-response",
            "model": "runtime-model",
            "content": "A grounded answer.",
            "prompt_tokens": 12,
            "completion_tokens": 8,
            "total_tokens": 20,
            "replayed": False,
        }

    monkeypatch.setattr("backend.app.agent_runtime.generate_chat_completion", fake_gateway)
    first = asyncio.run(run_agent(db_session, agent_id, "Summarize the evidence.", "runtime-key-0003"))
    second = asyncio.run(run_agent(db_session, agent_id, "Summarize the evidence.", "runtime-key-0003"))

    assert first["content"] == "A grounded answer."
    assert first["reservation"]["status"] == "succeeded"
    assert second["content"] == "A grounded answer."
    assert second["replayed"] is True
    assert len(calls) == 2
    assert calls[0] == calls[1]
