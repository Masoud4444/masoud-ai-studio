import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base
from backend.app.models import Project
from backend.app.research_schemas import ResearchClaimCreate, ResearchEvidenceCreate, ResearchSourceCreate
from backend.app.research_vault import create_claim, create_evidence, create_source
from backend.app.research_search import search_research


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


def make_project(db, slug):
    item = Project(slug=slug, name=slug.title())
    db.add(item)
    db.commit()
    db.refresh(item)
    return item


def test_search_matches_sources_evidence_claims_and_respects_project_scope(db_session):
    p1 = make_project(db_session, "vault-search-one")
    p2 = make_project(db_session, "vault-search-two")
    source1 = create_source(db_session, ResearchSourceCreate(
        source_type="note", title="Aurora field report", summary="Northern lights survey", project_id=p1.id,
    ))
    create_source(db_session, ResearchSourceCreate(
        source_type="note", title="Aurora second report", project_id=p2.id,
    ))
    evidence = create_evidence(db_session, source1["id"], ResearchEvidenceCreate(
        evidence_type="quote", excerpt="Aurora observations increased after midnight.", locator="page 8",
    ))
    claim = create_claim(db_session, ResearchClaimCreate(
        project_id=p1.id, statement="Aurora visibility increased in winter.",
        rationale="Based on repeated field observations.",
    ))
    scoped = search_research(db_session, "aurora", project_id=p1.id)
    assert scoped["totals"] == {"sources": 1, "evidence": 1, "claims": 1}
    assert scoped["sources"][0]["id"] == source1["id"]
    assert scoped["evidence"][0]["id"] == evidence["id"]
    assert scoped["claims"][0]["id"] == claim["id"]
    assert search_research(db_session, "aurora")["totals"]["sources"] == 2


def test_search_escapes_wildcards_and_rejects_short_queries(db_session):
    p = make_project(db_session, "vault-search-wildcard")
    create_source(db_session, ResearchSourceCreate(
        source_type="note", title="100% original _ draft", project_id=p.id,
    ))
    assert search_research(db_session, "100%")["totals"]["sources"] == 1
    with pytest.raises(HTTPException) as exc:
        search_research(db_session, " ")
    assert exc.value.status_code == 422
