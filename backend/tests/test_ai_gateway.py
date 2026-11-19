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
