from fastapi.testclient import TestClient
from pathlib import Path
from types import SimpleNamespace
import backend.app.api as api_module
from backend.app.main import app


def test_preferences_validate_and_persist_atomically(tmp_path, monkeypatch):
    database = tmp_path / "data" / "studio.db"
    database.parent.mkdir()
    monkeypatch.setattr(api_module, "engine", SimpleNamespace(url=SimpleNamespace(database=str(database))))
    client = TestClient(app)
    headers = {"host": "127.0.0.1:8000"}
    initial = client.get("/api/v1/settings/preferences", headers=headers)
    assert initial.status_code == 200
    assert initial.json()["backup_retention_count"] == 20
    invalid = client.put("/api/v1/settings/preferences", headers=headers, json={"backup_retention_count": 2})
    assert invalid.status_code == 422
    saved = client.put("/api/v1/settings/preferences", headers=headers, json={"backup_retention_count": 10})
    assert saved.status_code == 200
    assert saved.json()["backup_retention_count"] == 10
    assert client.get("/api/v1/settings/preferences", headers=headers).json()["backup_retention_count"] == 10
    assert (database.parent / "studio-settings.json").is_file()


def test_preferences_reject_unknown_fields(tmp_path, monkeypatch):
    database = tmp_path / "data" / "studio.db"
    database.parent.mkdir()
    monkeypatch.setattr(api_module, "engine", SimpleNamespace(url=SimpleNamespace(database=str(database))))
    response = TestClient(app).put("/api/v1/settings/preferences", headers={"host": "127.0.0.1:8000"},
                                  json={"backup_retention_count": 10, "api_key": "not-allowed"})
    assert response.status_code == 422
