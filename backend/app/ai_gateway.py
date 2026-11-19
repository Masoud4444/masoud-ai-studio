"""Private AI Gateway: provider registry, pinned outbound requests and idempotency."""
import asyncio
import base64
import hashlib
import ipaddress
import json
import os
import socket
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

import aiohttp
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import AIProvider, AIRequest, AIUsage
from .gateway_schemas import ProviderCreate, ChatCompletionRequest

KEY_ENV = "MASOUD_STUDIO_CREDENTIAL_KEY"
KEY_VERSION = int(os.getenv("MASOUD_STUDIO_CREDENTIAL_KEY_VERSION", "1"))
MAX_PROVIDER_RESPONSE_BYTES = 4 * 1024 * 1024
PROVIDER_TIMEOUT_SECONDS = 90


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


def encrypt_secret(secret: str, purpose: str = "provider", key_version: int = KEY_VERSION) -> str:
    nonce = os.urandom(12)
    aad = f"masoud-ai-studio:{purpose}:v{key_version}".encode("ascii")
    ciphertext = AESGCM(_master_key(key_version)).encrypt(nonce, secret.encode("utf-8"), aad)
    return base64.urlsafe_b64encode(nonce + ciphertext).decode("ascii")


def decrypt_secret(ciphertext: str, purpose: str = "provider", key_version: int = KEY_VERSION) -> str:
    raw = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
    if len(raw) < 29:
        raise ValueError("Invalid encrypted payload")
    aad = f"masoud-ai-studio:{purpose}:v{key_version}".encode("ascii")
    return AESGCM(_master_key(key_version)).decrypt(raw[:12], raw[12:], aad).decode("utf-8")


def _validate_ip_addresses(addresses: set[str]) -> list[str]:
    parsed = [ipaddress.ip_address(value) for value in addresses]
    if not parsed or any(not address.is_global for address in parsed):
        raise ValueError("Provider host resolves to a non-public address")
    return sorted({str(address) for address in parsed})


def validate_provider_url(value: str) -> str:
    try:
        if any(ord(ch) < 32 for ch in value) or "\\" in value:
            raise ValueError
        parsed = urlsplit(value.strip())
        if parsed.scheme.lower() != "https" or not parsed.hostname:
            raise ValueError
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError
        if parsed.port not in (None, 443):
            raise ValueError
        host = parsed.hostname.rstrip(".").encode("idna").decode("ascii").lower()
        if host in {"localhost", "localhost.localdomain"} or host.endswith((".localhost", ".local", ".internal", ".test")):
            raise ValueError
        try:
            addresses = {str(ipaddress.ip_address(host))}
        except ValueError:
            answers = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            addresses = {answer[4][0] for answer in answers}
        _validate_ip_addresses(addresses)
        authority = f"[{host}]" if ":" in host else host
        return urlunsplit(("https", authority, parsed.path.rstrip("/"), "", ""))
    except Exception:
        raise HTTPException(status_code=422, detail={"code": "provider_url_rejected"})


async def _resolve_public_addresses(host: str) -> list[str]:
    try:
        try:
            addresses = {str(ipaddress.ip_address(host))}
        except ValueError:
            loop = asyncio.get_running_loop()
            answers = await loop.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
            addresses = {answer[4][0] for answer in answers}
        return _validate_ip_addresses(addresses)
    except Exception:
        raise HTTPException(status_code=422, detail={"code": "provider_dns_rejected"})


class _PinnedResolver(aiohttp.abc.AbstractResolver):
    def __init__(self, pinned: list[str]):
        self.pinned = pinned

    async def resolve(self, host, port=0, family=socket.AF_INET):
        results = []
        for address in self.pinned:
            parsed = ipaddress.ip_address(address)
            if family not in (socket.AF_UNSPEC, parsed.version == 4 and socket.AF_INET or socket.AF_INET6):
                continue
            results.append({
                "hostname": host,
                "host": address,
                "port": port,
                "family": socket.AF_INET if parsed.version == 4 else socket.AF_INET6,
                "proto": 0,
                "flags": 0,
            })
        if not results:
            raise OSError("No pinned address for provider host")
        return results

    async def close(self):
        return None


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
    encrypted = encrypt_secret(key, "provider", KEY_VERSION) if key else None
    provider = AIProvider(
        id=str(uuid4()), name=payload.name.strip(), provider_type="openai_compatible",
        base_url=base_url, encrypted_api_key=encrypted, key_version=KEY_VERSION,
        models_json=json.dumps(payload.models), is_enabled=True,
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
    provider.is_enabled = False
    db.commit()


def _select_provider(db: Session, request: ChatCompletionRequest) -> AIProvider:
    query = select(AIProvider).where(AIProvider.is_enabled.is_(True))
    if request.provider_id:
        query = query.where(AIProvider.id == request.provider_id)
    providers = db.scalars(query.order_by(AIProvider.created_at.asc())).all()
    for provider in providers:
        if request.model in json.loads(provider.models_json):
            return provider
    raise HTTPException(status_code=404, detail={"code": "model_provider_not_found"})


def _request_hash(request: ChatCompletionRequest) -> str:
    payload = request.model_dump(mode="json", exclude={"provider_id"})
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _encrypt_response(response: dict) -> str:
    return encrypt_secret(json.dumps(response, separators=(",", ":"), ensure_ascii=False), "response", KEY_VERSION)


def _decrypt_response(response: str, key_version: int) -> dict:
    return json.loads(decrypt_secret(response, "response", key_version))


async def _send_chat_completion(provider: AIProvider, payload: ChatCompletionRequest) -> dict:
    parsed = urlsplit(provider.base_url)
    host = parsed.hostname
    if not host or parsed.scheme != "https" or parsed.port not in (None, 443):
        raise HTTPException(status_code=422, detail={"code": "provider_url_rejected"})
    pinned = await _resolve_public_addresses(host)
    resolver = _PinnedResolver(pinned)
    connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False, ssl=True)
    timeout = aiohttp.ClientTimeout(total=PROVIDER_TIMEOUT_SECONDS, connect=15, sock_read=75)
    endpoint = provider.base_url.rstrip("/") + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if provider.encrypted_api_key:
        secret = decrypt_secret(provider.encrypted_api_key, "provider", provider.key_version)
        headers["Authorization"] = f"Bearer {secret}"
    body = {
        "model": payload.model,
        "messages": [message.model_dump() for message in payload.messages],
        "stream": False,
    }
    if payload.temperature is not None:
        body["temperature"] = payload.temperature
    if payload.max_tokens is not None:
        body["max_tokens"] = payload.max_tokens
    try:
        async with aiohttp.ClientSession(
            connector=connector, timeout=timeout, trust_env=False,
            raise_for_status=False,
        ) as session:
            async with session.post(endpoint, json=body, headers=headers, allow_redirects=False) as response:
                raw = await response.content.read(MAX_PROVIDER_RESPONSE_BYTES + 1)
                if len(raw) > MAX_PROVIDER_RESPONSE_BYTES:
                    raise HTTPException(status_code=502, detail={"code": "provider_response_too_large"})
                if response.status < 200 or response.status >= 300:
                    if response.status == 429:
                        raise HTTPException(status_code=429, detail={"code": "provider_rate_limited"})
                    if response.status >= 500:
                        raise HTTPException(status_code=502, detail={"code": "provider_unavailable"})
                    raise HTTPException(status_code=502, detail={"code": "provider_request_rejected"})
                try:
                    data = json.loads(raw.decode("utf-8"))
                    content = data["choices"][0]["message"]["content"]
                    usage = data.get("usage") or {}
                    if not isinstance(content, str):
                        raise ValueError
                    return {
                        "id": str(data.get("id") or uuid4()),
                        "model": str(data.get("model") or payload.model),
                        "content": content,
                        "prompt_tokens": max(0, int(usage.get("prompt_tokens") or 0)),
                        "completion_tokens": max(0, int(usage.get("completion_tokens") or 0)),
                        "total_tokens": max(0, int(usage.get("total_tokens") or 0)),
                    }
                except (ValueError, KeyError, TypeError, IndexError):
                    raise HTTPException(status_code=502, detail={"code": "provider_response_invalid"})
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail={"code": "provider_timeout"})
    except aiohttp.ClientError:
        raise HTTPException(status_code=502, detail={"code": "provider_connection_failed"})


async def generate_chat_completion(db: Session, payload: ChatCompletionRequest, idempotency_key: str) -> dict:
    if not idempotency_key or len(idempotency_key) > 200:
        raise HTTPException(status_code=400, detail={"code": "idempotency_key_invalid"})
    provider = _select_provider(db, payload)
    idem_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    req_hash = _request_hash(payload)
    existing = db.scalar(select(AIRequest).where(AIRequest.idempotency_hash == idem_hash))
    if existing:
        if existing.request_hash != req_hash:
            raise HTTPException(status_code=409, detail={"code": "idempotency_key_conflict"})
        if existing.status == "completed" and existing.encrypted_response:
            result = _decrypt_response(existing.encrypted_response, existing.response_key_version)
            result["replayed"] = True
            return result
        if existing.status == "pending":
            raise HTTPException(status_code=409, detail={"code": "request_in_progress"})
        existing.status = "pending"
        existing.provider_id = provider.id
        existing.model = payload.model
        existing.encrypted_response = None
        request_row = existing
    else:
        request_row = AIRequest(
            id=str(uuid4()), idempotency_hash=idem_hash, request_hash=req_hash,
            provider_id=provider.id, model=payload.model, status="pending",
            response_key_version=KEY_VERSION,
        )
        db.add(request_row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "request_in_progress"})
    try:
        result = await _send_chat_completion(provider, payload)
        request_row.status = "completed"
        request_row.encrypted_response = _encrypt_response(result)
        request_row.response_key_version = KEY_VERSION
        db.add(AIUsage(
            id=str(uuid4()), request_id=request_row.id, provider_id=provider.id,
            model=payload.model, prompt_tokens=result["prompt_tokens"],
            completion_tokens=result["completion_tokens"], total_tokens=result["total_tokens"],
        ))
        db.commit()
        result["replayed"] = False
        return result
    except Exception:
        db.rollback()
        failed = db.get(AIRequest, request_row.id)
        if failed:
            failed.status = "failed"
            db.commit()
        raise
