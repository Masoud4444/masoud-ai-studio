import base64
import socket

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.ai_gateway import encrypt_secret, decrypt_secret, validate_provider_url, create_provider
from backend.app.gateway_schemas import ProviderCreate


def set_key(monkeypatch):
    monkeypatch.setenv("MASOUD_STUDIO_CREDENTIAL_KEY", base64.urlsafe_b64encode(b"k" * 32).decode("ascii"))


def test_secret_encryption_round_trip(monkeypatch):
    set_key(monkeypatch)
    encrypted = encrypt_secret("never-log-this")
    assert "never-log-this" not in encrypted
    assert decrypt_secret(encrypted) == "never-log-this"


def test_secret_requires_configured_key(monkeypatch):
    monkeypatch.delenv("MASOUD_STUDIO_CREDENTIAL_KEY", raising=False)
    with pytest.raises(HTTPException) as exc:
        encrypt_secret("secret")
    assert exc.value.status_code == 503
    assert exc.value.detail["code"] == "credential_encryption_not_configured"


@pytest.mark.parametrize("url", [
    "http://example.com/v1",
    "https://localhost/v1",
    "https://127.0.0.1/v1",
    "https://user:pass@example.com/v1",
    "https://example.com/v1?x=1",
])
def test_provider_url_rejects_unsafe_forms(url):
    with pytest.raises(HTTPException):
        validate_provider_url(url)


def test_provider_url_rejects_private_dns(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [(None, None, None, None, ("10.0.0.4", 443))])
    with pytest.raises(HTTPException):
        validate_provider_url("https://provider.example/v1")


def test_provider_create_never_returns_credential(monkeypatch):
    set_key(monkeypatch)
    monkeypatch.setattr("backend.app.ai_gateway.validate_provider_url", lambda value: "https://api.example/v1")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    with Session() as db:
        result = create_provider(db, ProviderCreate(name="Example Provider", base_url="https://api.example/v1", api_key="secret", models=["model-a"]))
        assert "api_key" not in result and "encrypted_api_key" not in result
        assert result["models"] == ["model-a"]
    engine.dispose()


import asyncio
from backend.app.ai_gateway import generate_chat_completion, set_model_pricing, get_usage_summary
from backend.app.models import AIProvider, AIRequest, AIUsage
from backend.app.gateway_schemas import ChatCompletionRequest, ModelPricingUpdate


def gateway_db():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, expire_on_commit=False)
    return engine, Session


def test_provider_disable_preserves_history(monkeypatch):
    from backend.app.ai_gateway import delete_provider
    engine, Session = gateway_db()
    with Session() as db:
        provider = AIProvider(name="History Provider", base_url="https://api.example/v1", models_json='["m1"]')
        db.add(provider)
        db.commit()
        delete_provider(db, provider.id)
        assert db.get(AIProvider, provider.id).is_enabled is False
    engine.dispose()


def test_idempotent_chat_replays_without_second_provider_call(monkeypatch):
    engine, Session = gateway_db()
    monkeypatch.setenv("MASOUD_STUDIO_CREDENTIAL_KEY", base64.urlsafe_b64encode(b"z" * 32).decode("ascii"))
    calls = {"count": 0}

    async def fake_send(provider, payload):
        calls["count"] += 1
        return {"id": "response-1", "model": payload.model, "content": "hello", "prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5}

    monkeypatch.setattr("backend.app.ai_gateway._send_chat_completion", fake_send)
    request = ChatCompletionRequest(model="m1", messages=[{"role": "user", "content": "hello"}])
    with Session() as db:
        provider = AIProvider(name="Gateway Provider", base_url="https://api.example/v1", models_json='["m1"]')
        db.add(provider)
        db.commit()
        set_model_pricing(db, provider.id, "m1", ModelPricingUpdate(input_usd_per_million=1, output_usd_per_million=2))
        first = asyncio.run(generate_chat_completion(db, request, "stable-key-001"))
        second = asyncio.run(generate_chat_completion(db, request, "stable-key-001"))
        assert first["content"] == "hello"
        assert first["replayed"] is False
        assert second["replayed"] is True
        assert calls["count"] == 1
        assert db.query(AIUsage).count() == 1
        usage = db.query(AIUsage).one()
        assert str(usage.estimated_cost_usd) == "0.00000700"
        summary = get_usage_summary(db)
        assert summary["requests"] == 1
        assert summary["estimated_cost_usd"] == "0.00000700"
    engine.dispose()


def test_idempotency_key_cannot_be_reused_for_different_payload(monkeypatch):
    engine, Session = gateway_db()
    monkeypatch.setenv("MASOUD_STUDIO_CREDENTIAL_KEY", base64.urlsafe_b64encode(b"y" * 32).decode("ascii"))
    async def fake_send(provider, payload):
        return {"id": "response-2", "model": payload.model, "content": "ok", "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    monkeypatch.setattr("backend.app.ai_gateway._send_chat_completion", fake_send)
    with Session() as db:
        db.add(AIProvider(name="Conflict Provider", base_url="https://api.example/v1", models_json='["m1"]'))
        db.commit()
        first = ChatCompletionRequest(model="m1", messages=[{"role":"user","content":"one"}])
        second = ChatCompletionRequest(model="m1", messages=[{"role":"user","content":"two"}])
        asyncio.run(generate_chat_completion(db, first, "stable-key-002"))
        with pytest.raises(HTTPException) as exc:
            asyncio.run(generate_chat_completion(db, second, "stable-key-002"))
        assert exc.value.status_code == 409
        assert exc.value.detail["code"] == "idempotency_key_conflict"
    engine.dispose()


def test_model_capabilities_are_marked_as_declared_not_verified():
    from backend.app.ai_gateway import update_model_capability, list_model_capabilities
    from backend.app.gateway_schemas import ModelCapabilityUpdate
    engine, Session = gateway_db()
    with Session() as db:
        provider = AIProvider(name="Capability Provider", base_url="https://api.example/v1", models_json='["vision-model"]')
        db.add(provider)
        db.commit()
        result = update_model_capability(
            db, provider.id, "vision-model",
            ModelCapabilityUpdate(capabilities=["chat", "vision"], context_window=64000, supports_vision=True),
        )
        assert result["verification_status"] == "declared"
        assert result["context_window"] == 64000
        assert list_model_capabilities(db)[0]["capabilities"] == ["chat", "vision"]
    engine.dispose()


def test_provider_connection_marks_only_matching_declared_models_verified(monkeypatch):
    from backend.app.ai_gateway import test_provider_connection
    engine, Session = gateway_db()
    async def fake_models(provider):
        return ["declared-model", "remote-only-model"]
    monkeypatch.setattr("backend.app.ai_gateway._fetch_provider_model_list", fake_models)
    with Session() as db:
        provider = AIProvider(name="Probe Provider", base_url="https://api.example/v1", models_json='["declared-model", "missing-model"]')
        db.add(provider)
        db.commit()
        result = asyncio.run(test_provider_connection(db, provider.id))
        assert result["status"] == "model_id_verified"
        assert result["verified_models"] == ["declared-model"]
        assert result["unmatched_declared_models"] == ["missing-model"]
    engine.dispose()


def test_expired_idempotency_lease_can_be_recovered(monkeypatch):
    import hashlib
    from backend.app.ai_gateway import _request_hash
    engine, Session = gateway_db()
    monkeypatch.setenv("MASOUD_STUDIO_CREDENTIAL_KEY", base64.urlsafe_b64encode(b"r" * 32).decode("ascii"))
    calls = {"count": 0}
    async def fake_send(provider, payload):
        calls["count"] += 1
        return {"id": "recovered", "model": payload.model, "content": "recovered", "prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}
    monkeypatch.setattr("backend.app.ai_gateway._send_chat_completion", fake_send)
    request = ChatCompletionRequest(model="m1", messages=[{"role":"user","content":"recover"}])
    with Session() as db:
        provider = AIProvider(name="Lease Provider", base_url="https://api.example/v1", models_json='["m1"]')
        db.add(provider)
        db.commit()
        db.add(AIRequest(
            id="expired-request", idempotency_hash=hashlib.sha256(b"lease-key-001").hexdigest(),
            request_hash=_request_hash(request), provider_id=provider.id, model="m1",
            status="pending", lease_expires_at=1,
        ))
        db.commit()
        result = asyncio.run(generate_chat_completion(db, request, "lease-key-001"))
        assert result["content"] == "recovered"
        assert calls["count"] == 1
    engine.dispose()

def test_model_pricing_versions_are_explicit_and_auditable():
    from backend.app.ai_gateway import set_model_pricing
    from backend.app.gateway_schemas import ModelPricingUpdate
    engine, Session = gateway_db()
    with Session() as db:
        provider = AIProvider(name="Pricing Provider", base_url="https://api.example/v1", models_json='["priced-model"]')
        db.add(provider)
        db.commit()
        first = set_model_pricing(db, provider.id, "priced-model", ModelPricingUpdate(input_usd_per_million=0.2, output_usd_per_million=0.8, source_note="Provider pricing page, checked manually"))
        second = set_model_pricing(db, provider.id, "priced-model", ModelPricingUpdate(input_usd_per_million=0.3, output_usd_per_million=0.9))
        assert first["version"] == 1
        assert second["version"] == 2
        assert second["input_usd_per_million"] == 0.3
    engine.dispose()
