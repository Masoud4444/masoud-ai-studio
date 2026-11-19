"""Manual-curation Research Vault with explicit provenance and evidence links."""
import hashlib
import json
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from .models import (
    Asset, Project, ResearchClaim, ResearchClaimEvidence, ResearchEvidence,
    ResearchEvent, ResearchSource, ProjectResearchSource,
)
from .research_schemas import (
    ResearchClaimCreate, ResearchClaimUpdate, ResearchEvidenceCreate,
    ResearchSourceCreate,
)


def _now():
    return datetime.now(timezone.utc)


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _event(db: Session, entity_type: str, entity_id: str, event_type: str, detail=None):
    db.add(ResearchEvent(
        entity_type=entity_type, entity_id=entity_id, event_type=event_type,
        detail_json=_json(detail or {}),
    ))


def _canonical_url(value: str | None) -> str | None:
    if value is None:
        return None
    parsed = urlsplit(value.strip())
    host = parsed.hostname.lower() if parsed.hostname else ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    port = parsed.port
    netloc = host
    if port and not ((parsed.scheme.lower() == "http" and port == 80) or
                     (parsed.scheme.lower() == "https" and port == 443)):
        netloc = f"{host}:{port}"
    return urlunsplit((parsed.scheme.lower(), netloc, parsed.path or "/", parsed.query, ""))


def _source_payload(db: Session, source: ResearchSource) -> dict:
    project_ids = db.scalars(
        select(ProjectResearchSource.project_id)
        .where(ProjectResearchSource.source_id == source.id)
        .order_by(ProjectResearchSource.created_at.asc())
    ).all()
    return {
        "id": source.id, "source_type": source.source_type, "title": source.title,
        "canonical_url": source.canonical_url, "author": source.author,
        "publisher": source.publisher, "published_at": source.published_at,
        "retrieved_at": source.retrieved_at, "language": source.language,
        "summary": source.summary, "asset_id": source.asset_id,
        "content_hash": source.content_hash, "metadata": json.loads(source.metadata_json),
        "project_ids": project_ids, "created_at": source.created_at,
        "updated_at": source.updated_at,
    }


def _evidence_payload(item: ResearchEvidence, replayed=False) -> dict:
    return {
        "id": item.id, "source_id": item.source_id, "evidence_type": item.evidence_type,
        "excerpt": item.excerpt, "locator": item.locator, "content_hash": item.content_hash,
        "metadata": json.loads(item.metadata_json), "created_at": item.created_at,
        "replayed": replayed,
    }


def _claim_payload(db: Session, claim: ResearchClaim) -> dict:
    rows = db.execute(
        select(ResearchClaimEvidence, ResearchEvidence)
        .join(ResearchEvidence, ResearchEvidence.id == ResearchClaimEvidence.evidence_id)
        .where(ResearchClaimEvidence.claim_id == claim.id)
        .order_by(ResearchClaimEvidence.created_at.asc())
    ).all()
    evidence = [{
        "id": item.id, "source_id": item.source_id, "evidence_type": item.evidence_type,
        "excerpt": item.excerpt, "locator": item.locator,
        "relationship": link.relationship, "note": link.note,
    } for link, item in rows]
    return {
        "id": claim.id, "project_id": claim.project_id, "statement": claim.statement,
        "claim_type": claim.claim_type, "status": claim.status,
        "rationale": claim.rationale, "evidence": evidence,
        "created_at": claim.created_at, "updated_at": claim.updated_at,
    }


def create_source(db: Session, payload: ResearchSourceCreate) -> dict:
    project = db.get(Project, payload.project_id) if payload.project_id else None
    if payload.project_id and project is None:
        raise HTTPException(status_code=404, detail={"code": "project_not_found"})
    if project is not None and project.status != "active":
        raise HTTPException(status_code=409, detail={"code": "project_archived"})
    asset = db.get(Asset, payload.asset_id) if payload.asset_id else None
    if payload.asset_id and asset is None:
        raise HTTPException(status_code=404, detail={"code": "asset_not_found"})
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=422, detail={"code": "source_title_required"})
    source = ResearchSource(
        source_type=payload.source_type, title=title,
        canonical_url=_canonical_url(payload.canonical_url),
        author=payload.author.strip() if payload.author else None,
        publisher=payload.publisher.strip() if payload.publisher else None,
        published_at=payload.published_at, retrieved_at=_now(),
        language=payload.language.strip() if payload.language else None,
        summary=payload.summary, asset_id=asset.id if asset else None,
        content_hash=asset.sha256 if asset else None, metadata_json=_json(payload.metadata),
    )
    db.add(source)
    db.flush()
    if project is not None:
        db.add(ProjectResearchSource(project_id=project.id, source_id=source.id))
    _event(db, "source", source.id, "source_created", {
        "source_type": source.source_type, "asset_id": source.asset_id,
        "project_id": project.id if project else None,
    })
    db.commit()
    db.refresh(source)
    return _source_payload(db, source)


def get_source(db: Session, source_id: str) -> dict:
    source = db.get(ResearchSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail={"code": "research_source_not_found"})
    return _source_payload(db, source)


def list_sources(db: Session, limit=50, offset=0, project_id: str | None = None) -> dict:
    query = select(ResearchSource)
    count_query = select(func.count()).select_from(ResearchSource)
    if project_id:
        query = query.join(ProjectResearchSource, ProjectResearchSource.source_id == ResearchSource.id).where(
            ProjectResearchSource.project_id == project_id
        )
        count_query = count_query.join(
            ProjectResearchSource, ProjectResearchSource.source_id == ResearchSource.id
        ).where(ProjectResearchSource.project_id == project_id)
    total = db.scalar(count_query) or 0
    items = db.scalars(query.order_by(ResearchSource.created_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [_source_payload(db, item) for item in items],
            "total": total, "limit": limit, "offset": offset}


def link_source_to_project(db: Session, source_id: str, project_id: str, notes: str | None = None) -> dict:
    source = db.get(ResearchSource, source_id)
    if source is None:
        raise HTTPException(status_code=404, detail={"code": "research_source_not_found"})
    project = db.get(Project, project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"code": "project_not_found"})
    if project.status != "active":
        raise HTTPException(status_code=409, detail={"code": "project_archived"})
    link = db.scalar(select(ProjectResearchSource).where(
        ProjectResearchSource.source_id == source_id,
        ProjectResearchSource.project_id == project_id,
    ))
    if link:
        if notes is not None and link.notes != notes:
            link.notes = notes
            db.commit()
            db.refresh(link)
        return {"source_id": source_id, "project_id": project_id,
                "notes": link.notes, "replayed": True}
    link = ProjectResearchSource(source_id=source_id, project_id=project_id, notes=notes)
    db.add(link)
    _event(db, "source", source_id, "source_linked_to_project", {"project_id": project_id})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "research_source_link_conflict"})
    db.refresh(link)
    return {"source_id": source_id, "project_id": project_id,
            "notes": link.notes, "replayed": False}


def detach_source_from_project(db: Session, source_id: str, project_id: str):
    link = db.scalar(select(ProjectResearchSource).where(
        ProjectResearchSource.source_id == source_id,
        ProjectResearchSource.project_id == project_id,
    ))
    if link is None:
        raise HTTPException(status_code=404, detail={"code": "research_source_link_not_found"})
    db.delete(link)
    _event(db, "source", source_id, "source_detached_from_project", {"project_id": project_id})
    db.commit()


def create_evidence(db: Session, source_id: str, payload: ResearchEvidenceCreate) -> dict:
    if db.get(ResearchSource, source_id) is None:
        raise HTTPException(status_code=404, detail={"code": "research_source_not_found"})
    excerpt = payload.excerpt.strip()
    if not excerpt:
        raise HTTPException(status_code=422, detail={"code": "evidence_excerpt_required"})
    digest_input = _json({
        "source_id": source_id, "evidence_type": payload.evidence_type,
        "excerpt": excerpt, "locator": payload.locator,
    })
    digest = hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
    existing = db.scalar(select(ResearchEvidence).where(
        ResearchEvidence.source_id == source_id, ResearchEvidence.content_hash == digest,
    ))
    if existing:
        return _evidence_payload(existing, replayed=True)
    item = ResearchEvidence(
        source_id=source_id, evidence_type=payload.evidence_type, excerpt=excerpt,
        locator=payload.locator, content_hash=digest, metadata_json=_json(payload.metadata),
    )
    db.add(item)
    _event(db, "source", source_id, "evidence_recorded", {"evidence_hash": digest})
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(ResearchEvidence).where(
            ResearchEvidence.source_id == source_id, ResearchEvidence.content_hash == digest,
        ))
        if existing:
            return _evidence_payload(existing, replayed=True)
        raise HTTPException(status_code=409, detail={"code": "research_evidence_conflict"})
    db.refresh(item)
    return _evidence_payload(item)


def list_evidence(db: Session, source_id: str, limit=100, offset=0) -> dict:
    if db.get(ResearchSource, source_id) is None:
        raise HTTPException(status_code=404, detail={"code": "research_source_not_found"})
    query = select(ResearchEvidence).where(ResearchEvidence.source_id == source_id)
    count_query = select(func.count()).select_from(ResearchEvidence).where(
        ResearchEvidence.source_id == source_id
    )
    total = db.scalar(count_query) or 0
    items = db.scalars(query.order_by(ResearchEvidence.created_at.asc()).limit(limit).offset(offset)).all()
    return {"items": [_evidence_payload(item) for item in items],
            "total": total, "limit": limit, "offset": offset}


def create_claim(db: Session, payload: ResearchClaimCreate) -> dict:
    project = db.get(Project, payload.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"code": "project_not_found"})
    if project.status != "active":
        raise HTTPException(status_code=409, detail={"code": "project_archived"})
    statement = payload.statement.strip()
    if not statement:
        raise HTTPException(status_code=422, detail={"code": "claim_statement_required"})
    claim = ResearchClaim(
        project_id=project.id, statement=statement, claim_type=payload.claim_type,
        status="draft", rationale=payload.rationale,
    )
    db.add(claim)
    db.flush()
    _event(db, "claim", claim.id, "claim_created", {
        "project_id": project.id, "claim_type": claim.claim_type,
    })
    db.commit()
    db.refresh(claim)
    return _claim_payload(db, claim)


def list_claims(db: Session, project_id: str, limit=50, offset=0) -> dict:
    query = select(ResearchClaim).where(ResearchClaim.project_id == project_id)
    count_query = select(func.count()).select_from(ResearchClaim).where(
        ResearchClaim.project_id == project_id
    )
    total = db.scalar(count_query) or 0
    items = db.scalars(query.order_by(ResearchClaim.created_at.desc()).limit(limit).offset(offset)).all()
    return {"items": [_claim_payload(db, item) for item in items],
            "total": total, "limit": limit, "offset": offset}


def get_claim(db: Session, claim_id: str) -> dict:
    claim = db.get(ResearchClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail={"code": "research_claim_not_found"})
    return _claim_payload(db, claim)


def link_evidence_to_claim(db: Session, claim_id: str, evidence_id: str,
                           relationship: str, note: str | None = None) -> dict:
    claim = db.get(ResearchClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail={"code": "research_claim_not_found"})
    evidence = db.get(ResearchEvidence, evidence_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail={"code": "research_evidence_not_found"})
    source_link = db.scalar(select(ProjectResearchSource.id).where(
        ProjectResearchSource.project_id == claim.project_id,
        ProjectResearchSource.source_id == evidence.source_id,
    ))
    if source_link is None:
        raise HTTPException(status_code=409, detail={"code": "research_source_not_linked_to_project"})
    existing = db.scalar(select(ResearchClaimEvidence).where(
        ResearchClaimEvidence.claim_id == claim_id,
        ResearchClaimEvidence.evidence_id == evidence_id,
    ))
    if existing:
        if existing.relationship == relationship and existing.note == note:
            return {"claim_id": claim_id, "evidence_id": evidence_id,
                    "relationship": relationship, "note": note, "replayed": True}
        existing.relationship = relationship
        existing.note = note
        _event(db, "claim", claim_id, "claim_evidence_relation_updated", {
            "evidence_id": evidence_id, "relationship": relationship,
        })
        db.commit()
        return {"claim_id": claim_id, "evidence_id": evidence_id,
                "relationship": relationship, "note": note, "replayed": False}
    link = ResearchClaimEvidence(
        claim_id=claim_id, evidence_id=evidence_id, relationship=relationship, note=note,
    )
    db.add(link)
    _event(db, "claim", claim_id, "claim_evidence_linked", {
        "evidence_id": evidence_id, "relationship": relationship,
    })
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "research_claim_evidence_conflict"})
    return {"claim_id": claim_id, "evidence_id": evidence_id,
            "relationship": relationship, "note": note, "replayed": False}


def update_claim(db: Session, claim_id: str, payload: ResearchClaimUpdate) -> dict:
    claim = db.get(ResearchClaim, claim_id)
    if claim is None:
        raise HTTPException(status_code=404, detail={"code": "research_claim_not_found"})
    values = payload.model_dump(exclude_unset=True)
    next_status = values.get("status", claim.status)
    if next_status in {"accepted", "rejected", "reviewed"}:
        relations = set(db.scalars(select(ResearchClaimEvidence.relationship).where(
            ResearchClaimEvidence.claim_id == claim_id
        )).all())
        if next_status == "accepted" and "supports" not in relations:
            raise HTTPException(status_code=409, detail={"code": "claim_acceptance_requires_supporting_evidence"})
        if next_status == "rejected" and "contradicts" not in relations:
            raise HTTPException(status_code=409, detail={"code": "claim_rejection_requires_contradicting_evidence"})
        if next_status == "reviewed" and not relations:
            raise HTTPException(status_code=409, detail={"code": "claim_review_requires_evidence"})
    for key, value in values.items():
        if key == "status":
            claim.status = value
        elif value is not None or key == "rationale":
            setattr(claim, key, value)
    claim.updated_at = _now()
    _event(db, "claim", claim.id, "claim_updated", {
        "status": claim.status, "fields": sorted(values.keys()),
    })
    db.commit()
    db.refresh(claim)
    return _claim_payload(db, claim)
