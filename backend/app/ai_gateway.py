"""Secure provider registry primitives for the private AI Gateway.

Provider URLs are checked at registration. The outbound adapter must repeat
this validation immediately before every connection; registration-time DNS
validation alone is not a complete DNS-rebinding defense.
"""
import base64
import ipaddress
import json
import os
import socket
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import AIProvider
from .gateway_schemas import ProviderCreate

KEY_ENV = "MASOUD_STUDIO_CREDENTIAL_KEY"
KEY_VERSION = int(os.getenv("MASOUD_STUDIO_CREDENTIAL_KEY_VERSION", "1"))


def _master_key(version: int = KEY_VERSION) -> bytes:
    encoded = os.getenv(f"{KEY_ENV}_V{version}", "") or (os.getenv(KEY_ENV, "") if version == 1 else "")
    if not encoded:
        raise HTTPException(status_code=503, detail={"code": "credential_encryption_not_configured"})
    try:
        key = base64.urlsafe_b64decode(encoded.encode("ascii"))
    except Exception:
        raise HTTPException(status_code=503, detail={"code": "credential_key_invalid"})
    if len(key) != 32:
        raise HTTPException(status_code=503, detail={"code": "credential_key_invalid"})
    return key


def encrypt_secret(secret: str) -> str:
    nonce = os.urandom(12)
    ciphertext = AESGCM(_master_key(KEY_VERSION)).encrypt(nonce, secret.encode("utf-8"), f"masoud-ai-studio:provider:v{KEY_VERSION}".encode("ascii"))
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_secret(ciphertext: str, key_version: int = KEY_VERSION) -> str:
    raw = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
    aad = f"masoud-ai-studio:provider:v{key_version}".encode("ascii")
    return AESGCM(_master_key(key_version)).decrypt(raw[:12], raw[12:], aad).decode("utf-8")


def validate_provider_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError
        host = parsed.hostname.rstrip(".").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal", ".test")):
            raise ValueError
        try:
            addresses = {ipaddress.ip_address(host)}
        except ValueError:
            answers = socket.getaddrinfo(host, parsed.port or 443, type=socket.SOCK_STREAM)
            addresses = {ipaddress.ip_address(answer[4][0]) for answer in answers}
        if not addresses or any(not address.is_global for address in addresses):
            raise ValueError
        # Normalize away fragments/query and preserve an optional provider API path.
        authority = f"[{host}]" if ":" in host else host
        port = parsed.port
        if port and port != 443:
            authority = f"{authority}:{port}"
        return urlunsplit(("https", authority, parsed.path.rstrip("/"), "", ""))
    except Exception:
        raise HTTPException(status_code=422, detail={"code": "provider_url_rejected"})


def _serialize(provider: AIProvider) -> dict:
    return {
        "id": provider.id,
        "name": provider.name,
        "provider_type": provider.provider_type,
        "base_url": provider.base_url,
        "models": json.loads(provider.models_json),
        "is_enabled": provider.is_enabled,
        "created_at": provider.created_at,
        "updated_at": provider.updated_at,
    }


def create_provider(db: Session, payload: ProviderCreate) -> dict:
    base_url = validate_provider_url(payload.base_url)
    key = payload.api_key.get_secret_value() if payload.api_key else None
    encrypted = encrypt_secret(key) if key else None
    provider = AIProvider(
        id=str(uuid4()),
        name=payload.name.strip(),
        provider_type="openai_compatible",
        base_url=base_url,
        encrypted_api_key=encrypted,
        key_version=KEY_VERSION,
        models_json=json.dumps(payload.models),
        is_enabled=True,
    )
    db.add(provider)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "provider_name_conflict"})
    db.refresh(provider)
    return _serialize(provider)


def list_providers(db: Session) -> list[dict]:
    rows = db.scalars(select(AIProvider).order_by(AIProvider.name.asc())).all()
    return [_serialize(row) for row in rows]


def delete_provider(db: Session, provider_id: str) -> None:
    provider = db.get(AIProvider, provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail={"code": "provider_not_found"})
    db.delete(provider)
    db.commit()
