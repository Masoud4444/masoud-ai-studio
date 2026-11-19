import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.models import Project, ResearchEvent
from backend.app.research_schemas import (
    ResearchClaimCreate, ResearchClaimUpdate, ResearchEvidenceCreate, ResearchSourceCreate,
)
from backend.app.research_vault import (
    create_claim, create_evidence, create_source, detach_source_from_project,
    get_claim, get_source, link_evidence_to_claim, link_source_to_project,
    list_claims, list_evidence, list_sources, update_claim,
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


def project(db, slug):
    item = Project(slug=slug, name=slug.title())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def test_source_create_links_to_project_and_normalizes_url(db_session):
    p = project(db_session, "research-one")
    source = create_source(db_session, ResearchSourceCreate(
        source_type="url", title="Primary report",
        canonical_url="HTTPS://Example.COM:443/report#section-2",
        project_id=p.id, author=" Analyst ", metadata={"topic": "policy"},
    ))
    assert source["canonical_url"] == "https://example.com/report"
    assert source["project_ids"] == [p.id]
    assert source["author"] == "Analyst"
    page = list_sources(db_session, project_id=p.id)
    assert page["total"] == 1
    assert page["items"][0]["id"] == source["id"]


def test_url_source_requires_safe_http_scheme():
    with pytest.raises(ValidationError):
        ResearchSourceCreate(source_type="url", title="Bad URL", canonical_url="javascript:alert(1)")
    with pytest.raises(ValidationError):
        ResearchSourceCreate(source_type="url", title="Credential URL", canonical_url="https://user:pass@example.com")
    with pytest.raises(ValidationError):
        ResearchSourceCreate(source_type="url", title="Bad port", canonical_url="https://example.com:99999")


def test_source_link_is_idempotent_and_detach_keeps_source(db_session):
    p1 = project(db_session, "research-two")
    p2 = project(db_session, "research-three")
    source = create_source(db_session, ResearchSourceCreate(
        source_type="note", title="Field notes", project_id=p1.id
    ))
    first = link_source_to_project(db_session, source["id"], p2.id, "Related project")
    replay = link_source_to_project(db_session, source["id"], p2.id, "Related project")
    assert first["replayed"] is False
    assert replay["replayed"] is True
    detach_source_from_project(db_session, source["id"], p1.id)
    assert get_source(db_session, source["id"])["project_ids"] == [p2.id]


def test_evidence_deduplicates_and_preserves_locator(db_session):
    source = create_source(db_session, ResearchSourceCreate(
        source_type="note", title="Interview notes"
    ))
    payload = ResearchEvidenceCreate(
        evidence_type="quote", excerpt="The project reduced processing time.",
        locator="page 4, paragraph 2",
    )
    first = create_evidence(db_session, source["id"], payload)
    replay = create_evidence(db_session, source["id"], payload)
    assert first["id"] == replay["id"]
    assert first["replayed"] is False
    assert replay["replayed"] is True
    page = list_evidence(db_session, source["id"])
    assert page["total"] == 1
    assert page["items"][0]["locator"] == "page 4, paragraph 2"


def test_claim_requires_project_linked_evidence_before_acceptance(db_session):
    p = project(db_session, "claim-project")
    source = create_source(db_session, ResearchSourceCreate(
        source_type="note", title="Evidence source"
    ))
    evidence = create_evidence(db_session, source["id"], ResearchEvidenceCreate(
        excerpt="Observed result."
    ))
    claim = create_claim(db_session, ResearchClaimCreate(
        project_id=p.id, statement="The intervention reduced processing time."
    ))
    with pytest.raises(HTTPException) as unlinked:
        link_evidence_to_claim(db_session, claim["id"], evidence["id"], "supports")
    assert unlinked.value.detail["code"] == "research_source_not_linked_to_project"
    link_source_to_project(db_session, source["id"], p.id)
    link_evidence_to_claim(db_session, claim["id"], evidence["id"], "supports")
    accepted = update_claim(db_session, claim["id"], ResearchClaimUpdate(status="accepted"))
    assert accepted["status"] == "accepted"
    assert len(accepted["evidence"]) == 1
    assert get_claim(db_session, claim["id"])["evidence"][0]["relationship"] == "supports"


def test_claim_rejection_requires_contradicting_evidence_and_events(db_session):
    p = project(db_session, "claim-review")
    source = create_source(db_session, ResearchSourceCreate(
        source_type="note", title="Counter evidence", project_id=p.id
    ))
    evidence = create_evidence(db_session, source["id"], ResearchEvidenceCreate(
        excerpt="Counter observation."
    ))
    claim = create_claim(db_session, ResearchClaimCreate(
        project_id=p.id, statement="A disputed claim."
    ))
    with pytest.raises(HTTPException) as rejected:
        update_claim(db_session, claim["id"], ResearchClaimUpdate(status="rejected"))
    assert rejected.value.detail["code"] == "claim_rejection_requires_contradicting_evidence"
    link_evidence_to_claim(db_session, claim["id"], evidence["id"], "contradicts")
    result = update_claim(db_session, claim["id"], ResearchClaimUpdate(status="rejected"))
    assert result["status"] == "rejected"
    assert len(db_session.scalars(select(ResearchEvent)).all()) >= 4
