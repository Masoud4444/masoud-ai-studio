"""Read-only full-text search for Research Vault records."""
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Project, ProjectResearchSource, ResearchClaim, ResearchEvidence, ResearchSource


def search_research(db: Session, query_text: str, project_id: str | None = None, limit: int = 25) -> dict:
    term = query_text.strip()
    if len(term) < 2:
        raise HTTPException(status_code=422, detail={"code": "research_query_too_short"})
    if len(term) > 200:
        raise HTTPException(status_code=422, detail={"code": "research_query_too_long"})
    if project_id and db.get(Project, project_id) is None:
        raise HTTPException(status_code=404, detail={"code": "project_not_found"})
    bounded_limit = max(1, min(int(limit), 100))
    escaped = term.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"

    source_filter = (
        ResearchSource.title.ilike(pattern, escape="\\")
        | ResearchSource.canonical_url.ilike(pattern, escape="\\")
        | ResearchSource.author.ilike(pattern, escape="\\")
        | ResearchSource.publisher.ilike(pattern, escape="\\")
        | ResearchSource.summary.ilike(pattern, escape="\\")
    )
    source_query = select(ResearchSource).where(source_filter)
    source_count = select(func.count()).select_from(ResearchSource).where(source_filter)
    if project_id:
        source_query = source_query.join(ProjectResearchSource).where(ProjectResearchSource.project_id == project_id)
        source_count = source_count.join(ProjectResearchSource).where(ProjectResearchSource.project_id == project_id)
    source_rows = db.scalars(source_query.order_by(ResearchSource.updated_at.desc()).limit(bounded_limit)).all()
    sources = [{
        "id": row.id, "kind": "source", "title": row.title,
        "source_type": row.source_type, "excerpt": row.summary or row.canonical_url or "",
        "source_id": row.id,
        "project_ids": db.scalars(select(ProjectResearchSource.project_id).where(
            ProjectResearchSource.source_id == row.id
        )).all(),
    } for row in source_rows]

    evidence_filter = (
        ResearchEvidence.excerpt.ilike(pattern, escape="\\")
        | ResearchEvidence.locator.ilike(pattern, escape="\\")
    )
    evidence_query = select(ResearchEvidence, ResearchSource).join(
        ResearchSource, ResearchSource.id == ResearchEvidence.source_id
    ).where(evidence_filter)
    evidence_count = select(func.count()).select_from(ResearchEvidence).where(evidence_filter)
    if project_id:
        evidence_query = evidence_query.join(ProjectResearchSource).where(ProjectResearchSource.project_id == project_id)
        evidence_count = evidence_count.join(
            ProjectResearchSource, ProjectResearchSource.source_id == ResearchEvidence.source_id
        ).where(ProjectResearchSource.project_id == project_id)
    evidence_rows = db.execute(
        evidence_query.order_by(ResearchEvidence.created_at.desc()).limit(bounded_limit)
    ).all()
    evidence = [{
        "id": item.id, "kind": "evidence", "title": source.title,
        "source_type": source.source_type, "excerpt": item.excerpt[:500],
        "locator": item.locator, "source_id": source.id,
    } for item, source in evidence_rows]

    claim_filter = (
        ResearchClaim.statement.ilike(pattern, escape="\\")
        | ResearchClaim.rationale.ilike(pattern, escape="\\")
    )
    claim_query = select(ResearchClaim).where(claim_filter)
    claim_count = select(func.count()).select_from(ResearchClaim).where(claim_filter)
    if project_id:
        claim_query = claim_query.where(ResearchClaim.project_id == project_id)
        claim_count = claim_count.where(ResearchClaim.project_id == project_id)
    claim_rows = db.scalars(claim_query.order_by(ResearchClaim.updated_at.desc()).limit(bounded_limit)).all()
    claims = [{
        "id": row.id, "kind": "claim", "title": row.statement,
        "claim_type": row.claim_type, "status": row.status,
        "excerpt": row.rationale or "", "project_id": row.project_id,
    } for row in claim_rows]

    return {
        "query": term, "project_id": project_id, "limit_per_kind": bounded_limit,
        "totals": {
            "sources": db.scalar(source_count) or 0,
            "evidence": db.scalar(evidence_count) or 0,
            "claims": db.scalar(claim_count) or 0,
        },
        "sources": sources, "evidence": evidence, "claims": claims,
    }
