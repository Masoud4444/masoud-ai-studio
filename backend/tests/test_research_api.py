import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.main import app


@pytest.fixture()
def client():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    testing_session = sessionmaker(
        bind=engine, autoflush=False, expire_on_commit=False
    )
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def test_research_vault_http_source_evidence_claim_flow(client):
    project_response = client.post(
        "/api/v1/projects",
        json={"name": "Evidence Project", "project_type": "research"},
    )
    assert project_response.status_code == 201
    project_id = project_response.json()["id"]

    source_response = client.post(
        "/api/v1/research/sources",
        json={
            "source_type": "url",
            "title": "Primary source",
            "canonical_url": "https://example.org/report",
            "project_id": project_id,
            "author": "Research Group",
        },
    )
    assert source_response.status_code == 201
    source = source_response.json()
    assert source["project_ids"] == [project_id]

    evidence_response = client.post(
        f"/api/v1/research/sources/{source['id']}/evidence",
        json={
            "evidence_type": "quote",
            "excerpt": "The intervention improved the measured outcome.",
            "locator": "page 12, paragraph 3",
        },
    )
    assert evidence_response.status_code == 201
    evidence = evidence_response.json()

    claim_response = client.post(
        "/api/v1/research/claims",
        json={
            "project_id": project_id,
            "statement": "The intervention improved the measured outcome.",
            "claim_type": "factual",
        },
    )
    assert claim_response.status_code == 201
    claim = claim_response.json()
    assert claim["status"] == "draft"

    link_response = client.post(
        f"/api/v1/research/claims/{claim['id']}/evidence/{evidence['id']}",
        json={"relationship": "supports"},
    )
    assert link_response.status_code == 200

    accepted = client.patch(
        f"/api/v1/research/claims/{claim['id']}",
        json={"status": "accepted"},
    )
    assert accepted.status_code == 200
    assert accepted.json()["status"] == "accepted"
    assert accepted.json()["evidence"][0]["locator"] == "page 12, paragraph 3"

    source_page = client.get(
        "/api/v1/research/sources",
        params={"project_id": project_id, "limit": 10},
    )
    assert source_page.status_code == 200
    assert source_page.json()["total"] == 1


def test_research_vault_http_rejects_unsafe_urls_and_evidence_orphaning(client):
    project = client.post("/api/v1/projects", json={"name": "Safety Project"}).json()
    invalid = client.post(
        "/api/v1/research/sources",
        json={
            "source_type": "url",
            "title": "Unsafe URL",
            "canonical_url": "file:///etc/passwd",
            "project_id": project["id"],
        },
    )
    assert invalid.status_code == 422

    source = client.post(
        "/api/v1/research/sources",
        json={"source_type": "note", "title": "Notes", "project_id": project["id"]},
    ).json()
    evidence = client.post(
        f"/api/v1/research/sources/{source['id']}/evidence",
        json={"excerpt": "A source excerpt."},
    ).json()
    claim = client.post(
        "/api/v1/research/claims",
        json={"project_id": project["id"], "statement": "A claim."},
    ).json()
    client.post(
        f"/api/v1/research/claims/{claim['id']}/evidence/{evidence['id']}",
        json={"relationship": "supports"},
    )
    detach = client.delete(
        f"/api/v1/research/sources/{source['id']}/projects/{project['id']}"
    )
    assert detach.status_code == 409
    assert detach.json()["detail"]["code"] == "research_source_has_claim_evidence"
