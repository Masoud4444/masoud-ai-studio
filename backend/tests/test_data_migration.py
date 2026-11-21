import hashlib
import json
import sqlite3

import pytest

from desktop.migrate_data import migrate_data


def _source(path):
    storage = path / "storage"
    payload = b"verified studio content"
    digest = hashlib.sha256(payload).hexdigest()
    blob = storage / "blobs" / digest[:2] / digest
    blob.parent.mkdir(parents=True)
    blob.write_bytes(payload)
    with sqlite3.connect(path / "masoud_studio.db") as db:
        db.execute("CREATE TABLE assets (sha256 TEXT, size_bytes INTEGER, storage_key TEXT)")
        db.execute("INSERT INTO assets VALUES (?, ?, ?)",
                   (digest, len(payload), f"blobs/{digest[:2]}/{digest}"))
    return blob


def test_migration_verifies_copy_switches_config_and_preserves_source(tmp_path):
    source = tmp_path / "old-data"
    source.mkdir()
    original_blob = _source(source)
    app_root = tmp_path / "profile" / "Masoud AI Studio"
    app_root.mkdir(parents=True)
    key_file = app_root / "credential-key.dpapi"
    key_file.write_bytes(b"protected-key-placeholder")
    settings = app_root / "desktop-settings.json"
    settings.write_text(json.dumps({"existing_option": True}), encoding="utf-8")
    destination = tmp_path / "new-drive" / "MasoudData"

    report = migrate_data(source, destination, settings)

    config = json.loads(settings.read_text(encoding="utf-8"))
    assert report["migrated"] is True
    assert report["source_preserved"] is True
    assert config == {"existing_option": True, "data_directory": str(destination)}
    assert (destination / "masoud_studio.db").is_file()
    assert original_blob.is_file()
    assert key_file.read_bytes() == b"protected-key-placeholder"


def test_migration_refuses_existing_destination_and_keeps_config_unchanged(tmp_path):
    source = tmp_path / "old-data"
    source.mkdir()
    _source(source)
    destination = tmp_path / "existing"
    destination.mkdir()
    settings = tmp_path / "desktop-settings.json"
    settings.write_text("{}", encoding="utf-8")

    with pytest.raises(FileExistsError):
        migrate_data(source, destination, settings)

    assert json.loads(settings.read_text(encoding="utf-8")) == {}
    assert (source / "masoud_studio.db").is_file()


def test_migration_rejects_corrupt_asset_without_switching_config(tmp_path):
    source = tmp_path / "old-data"
    source.mkdir()
    blob = _source(source)
    blob.write_bytes(b"corrupt")
    destination = tmp_path / "new-data"
    settings = tmp_path / "desktop-settings.json"
    settings.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError, match="failed SHA-256"):
        migrate_data(source, destination, settings)

    assert not destination.exists()
    assert json.loads(settings.read_text(encoding="utf-8")) == {}
