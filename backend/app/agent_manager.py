"""Agent Manager: versioned agent configuration, bounded budgets and explicit tool grants.

This module configures agents only. It does not execute tools or call model providers.
"""
import json
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import AIProvider, AgentEvent, AgentToolGrant, StudioAgent
from .agent_schemas import AgentCreate, AgentUpdate, AgentToolsUpdate


def _now():
    return datetime.now(timezone.utc)


def _event(db: Session, agent_id: str, event_type: str, detail: dict | None = None):
    db.add(AgentEvent(
        id=str(uuid4()), agent_id=agent_id, event_type=event_type,
        detail_json=json.dumps(detail or {}, ensure_ascii=False, allow_nan=False, separators=(",", ":")),
        created_at=_now(),
    ))


def _serialize(agent: StudioAgent, db: Session) -> dict:
    grants = db.scalars(
        select(AgentToolGrant).where(AgentToolGrant.agent_id == agent.id)
        .order_by(AgentToolGrant.tool_name.asc())
    ).all()
    return {
        "id": agent.id, "slug": agent.slug, "name": agent.name,
        "description": agent.description, "purpose": agent.purpose,
        "system_prompt": agent.system_prompt, "status": agent.status,
        "provider_id": agent.provider_id, "model_id": agent.model_id,
        "temperature": float(agent.temperature),
        "max_output_tokens": agent.max_output_tokens,
        "max_cost_per_run_usd": float(agent.max_cost_per_run_usd),
        "monthly_budget_usd": float(agent.monthly_budget_usd),
        "permissions": json.loads(agent.permissions_json),
        "version": agent.version,
        "tools": [{
            "tool_name": g.tool_name, "permission": g.permission,
            "approval_required": g.approval_required, "is_enabled": g.is_enabled,
        } for g in grants],
        "created_at": agent.created_at, "updated_at": agent.updated_at,
    }


def create_agent(db: Session, payload: AgentCreate) -> dict:
    if (payload.provider_id is None) != (payload.model_id is None):
        raise HTTPException(status_code=422, detail={"code": "provider_and_model_must_be_paired"})
    if payload.provider_id:
        provider = db.get(AIProvider, payload.provider_id)
        if provider is None or not provider.is_enabled:
            raise HTTPException(status_code=422, detail={"code": "agent_provider_unavailable"})
        if payload.model_id not in json.loads(provider.models_json):
            raise HTTPException(status_code=422, detail={"code": "agent_model_not_registered"})
    agent = StudioAgent(
        slug=payload.slug, name=payload.name.strip(), description=payload.description,
        purpose=payload.purpose.strip(), system_prompt=payload.system_prompt,
        provider_id=payload.provider_id, model_id=payload.model_id,
        temperature=payload.temperature, max_output_tokens=payload.max_output_tokens,
        max_cost_per_run_usd=payload.max_cost_per_run_usd,
        monthly_budget_usd=payload.monthly_budget_usd,
        permissions_json=json.dumps(payload.permissions, ensure_ascii=False, allow_nan=False),
        status="draft", version=1, created_at=_now(), updated_at=_now(),
    )
    db.add(agent)
    try:
        db.flush()
        _event(db, agent.id, "agent_created", {"version": 1})
        db.commit()
        db.refresh(agent)
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "agent_slug_conflict"})
    return _serialize(agent, db)


def get_agent(db: Session, agent_id: str) -> dict:
    agent = db.get(StudioAgent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail={"code": "agent_not_found"})
    return _serialize(agent, db)


def list_agents(db: Session, limit: int = 50, offset: int = 0, status: str | None = None) -> dict:
    query = select(StudioAgent)
    count = select(func.count()).select_from(StudioAgent)
    if status:
        query = query.where(StudioAgent.status == status)
        count = count.where(StudioAgent.status == status)
    total = db.scalar(count) or 0
    agents = db.scalars(query.order_by(StudioAgent.created_at.desc()).offset(offset).limit(limit)).all()
    return {"items": [_serialize(a, db) for a in agents], "total": total, "limit": limit, "offset": offset}


def update_agent(db: Session, agent_id: str, payload: AgentUpdate) -> dict:
    agent = db.get(StudioAgent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail={"code": "agent_not_found"})
    if agent.status == "enabled":
        raise HTTPException(status_code=409, detail={"code": "disable_agent_before_editing"})
    changes = payload.model_dump(exclude_unset=True)
    if not changes:
        return _serialize(agent, db)
    provider_id = changes.get("provider_id", agent.provider_id)
    model_id = changes.get("model_id", agent.model_id)
    if (provider_id is None) != (model_id is None):
        raise HTTPException(status_code=422, detail={"code": "provider_and_model_must_be_paired"})
    if provider_id:
        provider = db.get(AIProvider, provider_id)
        if provider is None or not provider.is_enabled:
            raise HTTPException(status_code=422, detail={"code": "agent_provider_unavailable"})
        if model_id not in json.loads(provider.models_json):
            raise HTTPException(status_code=422, detail={"code": "agent_model_not_registered"})
    if "permissions" in changes:
        changes["permissions_json"] = json.dumps(changes.pop("permissions"), ensure_ascii=False, allow_nan=False)
    for key, value in changes.items():
        setattr(agent, key, value.strip() if key in {"name", "purpose"} and isinstance(value, str) else value)
    agent.version += 1
    agent.updated_at = _now()
    _event(db, agent.id, "agent_updated", {"version": agent.version, "fields": sorted(changes.keys())})
    db.commit()
    db.refresh(agent)
    return _serialize(agent, db)


def replace_agent_tools(db: Session, agent_id: str, payload: AgentToolsUpdate) -> dict:
    agent = db.get(StudioAgent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail={"code": "agent_not_found"})
    if agent.status == "enabled":
        raise HTTPException(status_code=409, detail={"code": "disable_agent_before_editing_tools"})
    names = [g.tool_name for g in payload.grants]
    if len(names) != len(set(names)):
        raise HTTPException(status_code=422, detail={"code": "duplicate_tool_grant"})
    db.query(AgentToolGrant).filter(AgentToolGrant.agent_id == agent_id).delete(synchronize_session=False)
    for grant in payload.grants:
        db.add(AgentToolGrant(
            id=str(uuid4()), agent_id=agent_id, tool_name=grant.tool_name,
            permission=grant.permission, approval_required=grant.approval_required,
            is_enabled=grant.is_enabled, created_at=_now(),
        ))
    agent.version += 1
    agent.updated_at = _now()
    _event(db, agent.id, "agent_tools_replaced", {"tool_count": len(payload.grants), "version": agent.version})
    db.commit()
    db.refresh(agent)
    return _serialize(agent, db)


def enable_agent(db: Session, agent_id: str) -> dict:
    agent = db.get(StudioAgent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail={"code": "agent_not_found"})
    if agent.status == "enabled":
        return _serialize(agent, db)
    if not agent.system_prompt.strip():
        raise HTTPException(status_code=409, detail={"code": "agent_system_prompt_required"})
    if not agent.provider_id or not agent.model_id:
        raise HTTPException(status_code=409, detail={"code": "agent_provider_model_required"})
    provider = db.get(AIProvider, agent.provider_id)
    if provider is None or not provider.is_enabled or agent.model_id not in json.loads(provider.models_json):
        raise HTTPException(status_code=409, detail={"code": "agent_provider_model_unavailable"})
    grants = db.scalars(select(AgentToolGrant).where(
        AgentToolGrant.agent_id == agent_id, AgentToolGrant.is_enabled.is_(True)
    )).all()
    if any(g.permission in {"write", "execute"} and not g.approval_required for g in grants):
        raise HTTPException(status_code=409, detail={"code": "unsafe_tool_grant"})
    agent.status = "enabled"
    agent.version += 1
    agent.updated_at = _now()
    _event(db, agent.id, "agent_enabled", {"version": agent.version})
    db.commit()
    db.refresh(agent)
    return _serialize(agent, db)


def disable_agent(db: Session, agent_id: str) -> dict:
    agent = db.get(StudioAgent, agent_id)
    if agent is None:
        raise HTTPException(status_code=404, detail={"code": "agent_not_found"})
    if agent.status != "disabled":
        before = agent.status
        agent.status = "disabled"
        agent.version += 1
        agent.updated_at = _now()
        _event(db, agent.id, "agent_disabled", {"from_status": before, "version": agent.version})
        db.commit()
        db.refresh(agent)
    return _serialize(agent, db)
