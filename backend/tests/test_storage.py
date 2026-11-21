import hashlib
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app import storage

@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path / "storage")
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

def create_project(client):
    response = client.post("/api/v1/projects", json={"name": "Asset Test"})
    assert response.status_code == 201
    return response.json()["id"]

def test_upload_hashes_and_lists_asset(client, tmp_path):
    project_id = create_project(client)
    content = b"\x89PNG\r\n\x1a\n" + b"image-data"
    response = client.post(f"/api/v1/projects/{project_id}/assets",
                           files={"file": ("../unsafe name.png", content, "text/plain")})
    assert response.status_code == 201
    item = response.json()
    assert item["sha256"] == hashlib.sha256(content).hexdigest()
    assert item["mime_type"] == "image/png"
    assert item["filename"] == "unsafe name.png"
    blob = tmp_path / "storage" / "blobs" / item["sha256"][:2] / item["sha256"]
    assert blob.read_bytes() == content
    listed = client.get(f"/api/v1/projects/{project_id}/assets")
    assert listed.status_code == 200 and len(listed.json()) == 1

def test_detach_keeps_blob_bytes(client, tmp_path):
    project_id = create_project(client)
    content = b"ordinary text asset"
    item = client.post(f"/api/v1/projects/{project_id}/assets",
                       files={"file": ("memo.txt", content, "text/plain")}).json()
    blob = tmp_path / "storage" / "blobs" / item["sha256"][:2] / item["sha256"]
    response = client.delete(f"/api/v1/projects/{project_id}/assets/{item['id']}")
    assert response.status_code == 204
    assert blob.exists()
    assert client.get(f"/api/v1/projects/{project_id}/assets").json() == []

def test_empty_upload_rejected(client):
    project_id = create_project(client)
    response = client.post(f"/api/v1/projects/{project_id}/assets",
                           files={"file": ("empty.bin", b"", "application/octet-stream")})
    assert response.status_code == 400
