"""Agent Runtime: budget-gated, tool-free model execution.

This first runtime slice deliberately supports text generation only. It does not
execute tools, access project files, or perform external write actions.
"""
import hashlib
import json
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from .agent_manager import (
    reserve_agent_budget,
    start_agent_budget_reservation,
    settle_agent_budget_reservation,
    release_agent_budget_reservation,
)
from .ai_gateway import generate_chat_completion
from .gateway_schemas import ChatCompletionRequest, ChatMessage
from .models import AIModelPricing, AIRequest, AIUsage, StudioAgent


def _hash_payload(payload: dict) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _upper_bound_cost(agent: StudioAgent, pricing: AIModelPricing, user_message: str) -> Decimal:
    # UTF-8 byte count is intentionally used as a conservative token upper bound.
    # The configured maximum output is reserved in full before the provider call.
    input_bytes = len((agent.system_prompt + user_message).encode("utf-8"))
    input_tokens_upper = max(1, input_bytes)
    output_tokens_upper = agent.max_output_tokens
    amount = (
        Decimal(input_tokens_upper) * Decimal(str(pricing.input_usd_per_million))
        + Decimal(output_tokens_upper) * Decimal(str(pricing.output_usd_per_million))
    ) / Decimal(1_000_000)
    return max(amount, Decimal("0.00000001")).quantize(Decimal("0.00000001"))


async def run_agent(db: Session, agent_id: str, user_message: str, idempotency_key: str) -> dict:
    if not idempotency_key or not 8 <= len(idempotency_key) <= 180:
        raise HTTPException(status_code=422, detail={"code": "invalid_idempotency_key"})
    if not user_message or len(user_message) > 100_000:
        raise HTTPException(status_code=422, detail={"code": "invalid_agent_message"})

    agent = db.get(StudioAgent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail={"code": "agent_not_found"})
    if agent.status != "enabled":
        raise HTTPException(status_code=409, detail={"code": "agent_not_enabled"})
    permissions = json.loads(agent.permissions_json)
    if "ai.generate" not in permissions:
        raise HTTPException(status_code=403, detail={"code": "agent_permission_denied"})
    if not agent.provider_id or not agent.model_id:
        raise HTTPException(status_code=409, detail={"code": "agent_provider_model_required"})

    pricing = db.scalar(select(AIModelPricing).where(
        AIModelPricing.provider_id == agent.provider_id,
        AIModelPricing.model_id == agent.model_id,
    ))
    if pricing is None:
        raise HTTPException(status_code=409, detail={"code": "agent_model_pricing_required"})

    request_identity = {
        "agent_id": agent.id,
        "agent_version": agent.version,
        "model_id": agent.model_id,
        "system_prompt": agent.system_prompt,
        "user_message": user_message,
        "temperature": float(agent.temperature),
        "max_output_tokens": agent.max_output_tokens,
    }
    request_hash = _hash_payload(request_identity)
    # Hash caller-controlled keys so the persisted composite key stays bounded.
    caller_key_hash = hashlib.sha256(idempotency_key.encode("utf-8")).hexdigest()
    runtime_key = f"agent:{agent.id}:{caller_key_hash}"
    reservation = reserve_agent_budget(
        db, agent.id, runtime_key, request_hash,
        _upper_bound_cost(agent, pricing, user_message),
    )
    gateway_key = hashlib.sha256(runtime_key.encode("utf-8")).hexdigest()
    payload = ChatCompletionRequest(
        model=agent.model_id,
        provider_id=agent.provider_id,
        temperature=float(agent.temperature),
        max_tokens=agent.max_output_tokens,
        messages=[
            ChatMessage(role="system", content=agent.system_prompt),
            ChatMessage(role="user", content=user_message),
        ],
    )
    if reservation["status"] == "succeeded":
        result = await generate_chat_completion(db, payload, gateway_key)
        return {
            "agent_id": agent.id,
            "content": result["content"],
            "model": result["model"],
            "usage": {
                "prompt_tokens": result["prompt_tokens"],
                "completion_tokens": result["completion_tokens"],
                "total_tokens": result["total_tokens"],
            },
            "reservation": reservation,
            "replayed": True,
        }
    if reservation["status"] == "failed":
        raise HTTPException(status_code=409, detail={"code": "agent_previous_run_failed_use_new_idempotency_key"})
    if reservation["status"] == "released":
        raise HTTPException(status_code=409, detail={"code": "agent_budget_reservation_released"})

    started = False
    try:
        reservation = start_agent_budget_reservation(db, reservation["id"])
        started = True
        result = await generate_chat_completion(db, payload, gateway_key)
        gateway_idem_hash = hashlib.sha256(gateway_key.encode("utf-8")).hexdigest()
        usage = db.scalar(
            select(AIUsage).join(AIRequest, AIUsage.request_id == AIRequest.id).where(
                AIRequest.idempotency_hash == gateway_idem_hash
            )
        )
        actual_cost = (
            Decimal(str(usage.estimated_cost_usd))
            if usage is not None and usage.estimated_cost_usd is not None
            else Decimal(str(reservation["reserved_usd"]))
        )
        settled = settle_agent_budget_reservation(
            db, reservation["id"], actual_cost, succeeded=True
        )
        return {
            "agent_id": agent.id,
            "content": result["content"],
            "model": result["model"],
            "usage": {
                "prompt_tokens": result["prompt_tokens"],
                "completion_tokens": result["completion_tokens"],
                "total_tokens": result["total_tokens"],
            },
            "reservation": settled,
            "replayed": bool(result.get("replayed", False)),
        }
    except Exception:
        if started:
            # On ambiguous provider failures, charge the full reserved upper bound
            # in the ledger rather than assuming that no billable work occurred.
            try:
                settle_agent_budget_reservation(
                    db, reservation["id"], reservation["reserved_usd"], succeeded=False
                )
            except Exception:
                db.rollback()
        else:
            try:
                release_agent_budget_reservation(db, reservation["id"])
            except Exception:
                db.rollback()
        raise
