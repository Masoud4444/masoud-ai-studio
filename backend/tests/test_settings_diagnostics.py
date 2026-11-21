import pytest
from fastapi.testclient import TestClient
from types import SimpleNamespace

from backend.app.main import app
import backend.app.api as api_module


def test_system_settings_reports_local_paths_and_storage_without_secrets(tmp_path, monkeypatch):
    database = tmp_path / "data" / "studio.db"
    database.parent.mkdir()
    database.write_bytes(b"sqlite-placeholder")
    storage = tmp_path / "storage"
    (storage / "blobs").mkdir(parents=True)
    (storage / "blobs" / "asset.bin").write_bytes(b"asset-data")
    backups = database.parent / "backups"
    backups.mkdir()
    (backups / "masoud-studio-sample.zip").write_bytes(b"backup")
    monkeypatch.setattr(api_module, "engine", SimpleNamespace(url=SimpleNamespace(database=str(database))))
    monkeypatch.setattr(api_module, "STORAGE_ROOT", storage)
    monkeypatch.setenv("MASOUD_STUDIO_MAX_UPLOAD_BYTES", "4096")
    monkeypatch.setenv("MASOUD_STUDIO_DESKTOP_MODE", "true")
    response = TestClient(app).get("/api/v1/settings/system", headers={"host": "127.0.0.1:8000"})
    assert response.status_code == 200
    body = response.json()
    assert body["database_path"] == str(database.resolve())
    assert body["storage"] == {"bytes": 10, "files": 1}
    assert body["backup_count"] == 1
    assert body["max_upload_bytes"] == 4096
    assert body["desktop_mode"] is True
    assert "credential" not in body or "credential_key_present" in body
    assert not any("secret" in key.lower() or "key_material" in key.lower() for key in body)
