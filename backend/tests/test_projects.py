import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.app.database import Base, get_db
from backend.app.main import app

@pytest.fixture()
def client():
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    TestingSession = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)
    def override_get_db():
        db = TestingSession()
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

def test_project_lifecycle_and_versioning(client):
    response = client.post("/api/v1/projects", json={"name": "My First Film", "project_type": "documentary", "settings": {"language": "fa"}})
    assert response.status_code == 201
    project = response.json()
    assert project["slug"] == "my-first-film" and project["version"] == 1
    updated = client.patch(f"/api/v1/projects/{project['id']}", json={"expected_version": 1, "description": "A test project"})
    assert updated.status_code == 200 and updated.json()["version"] == 2
    conflict = client.patch(f"/api/v1/projects/{project['id']}", json={"expected_version": 1, "name": "Lost update"})
    assert conflict.status_code == 409
    archived = client.post(f"/api/v1/projects/{project['id']}/archive")
    assert archived.status_code == 200 and archived.json()["status"] == "archived"
    restored = client.post(f"/api/v1/projects/{project['id']}/restore")
    assert restored.status_code == 200 and restored.json()["status"] == "active"

def test_duplicate_slug_returns_conflict(client):
    assert client.post("/api/v1/projects", json={"name": "Same Name"}).status_code == 201
    assert client.post("/api/v1/projects", json={"name": "Same Name"}).status_code == 409
