import sqlite3
from pathlib import Path

import pytest

from backend.app.backup import BackupError, create_backup, restore_backup, verify_backup


def _database(path: Path, value: str = "before"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE IF NOT EXISTS sample (value TEXT)")
        db.execute("DELETE FROM sample")
        db.execute("INSERT INTO sample(value) VALUES (?)", (value,))
        db.commit()


def test_backup_verifies_database_and_storage(tmp_path):
    db = tmp_path / "data" / "studio.sqlite3"
    storage = tmp_path / "data" / "storage"
    storage.mkdir(parents=True)
    _database(db)
    (storage / "asset.bin").write_bytes(b"asset-content")

    result = create_backup(db, storage, tmp_path / "backups")
    report = verify_backup(Path(result["path"]))

    assert report["valid"] is True
    assert report["database_integrity"] == "ok"
    assert report["file_count"] == 2
    assert report["credential_key_included"] is False


def test_restore_replaces_database_and_storage_and_keeps_rollback(tmp_path):
    db = tmp_path / "data" / "studio.sqlite3"
    storage = tmp_path / "data" / "storage"
    storage.mkdir(parents=True)
    _database(db, "saved")
    (storage / "saved.bin").write_bytes(b"saved")
    backup = create_backup(db, storage, tmp_path / "backups")["path"]

    _database(db, "current")
    (storage / "current.bin").write_bytes(b"current")
    result = restore_backup(Path(backup), db, storage)

    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT value FROM sample").fetchone()[0] == "saved"
    assert (storage / "saved.bin").read_bytes() == b"saved"
    assert not (storage / "current.bin").exists()
    assert result["restored"] is True
    assert Path(result["rollback_database"]).exists()
    assert Path(result["rollback_storage"]).exists()


def test_verification_rejects_tampered_archive(tmp_path):
    db = tmp_path / "studio.sqlite3"
    _database(db)
    backup = Path(create_backup(db, tmp_path / "missing-storage", tmp_path / "backups")["path"])
    data = bytearray(backup.read_bytes())
    data[-30] ^= 0x01
    backup.write_bytes(data)
    with pytest.raises(BackupError):
        verify_backup(backup)


def test_backup_refuses_symlink_in_storage(tmp_path):
    db = tmp_path / "studio.sqlite3"
    _database(db)
    storage = tmp_path / "storage"
    storage.mkdir()
    target = tmp_path / "outside.txt"
    target.write_text("private")
    (storage / "link.txt").symlink_to(target)
    with pytest.raises(BackupError):
        create_backup(db, storage, tmp_path / "backups")
