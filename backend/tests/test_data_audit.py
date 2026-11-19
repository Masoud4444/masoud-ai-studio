import hashlib
import sqlite3

from desktop.data_audit import audit_data


def _database(path, records):
    with sqlite3.connect(path) as db:
        db.execute("CREATE TABLE assets (sha256 TEXT, size_bytes INTEGER, storage_key TEXT)")
        db.executemany("INSERT INTO assets VALUES (?, ?, ?)", records)


def test_audit_verifies_content_addressed_assets_without_mutation(tmp_path):
    storage = tmp_path / "storage"
    payload = b"studio asset bytes"
    digest = hashlib.sha256(payload).hexdigest()
    blob = storage / "blobs" / digest[:2] / digest
    blob.parent.mkdir(parents=True)
    blob.write_bytes(payload)
    database = tmp_path / "studio.db"
    _database(database, [(digest, len(payload), f"blobs/{digest[:2]}/{digest}")])

    before = database.read_bytes(), blob.read_bytes()
    report = audit_data(database, storage)

    assert report["healthy"] is True
    assert report["verified_assets"] == 1
    assert report["orphaned_files"] == []
    assert (database.read_bytes(), blob.read_bytes()) == before


def test_audit_reports_missing_corrupt_and_orphaned_files(tmp_path):
    storage = tmp_path / "storage"
    storage.mkdir()
    payload = b"expected"
    digest = hashlib.sha256(payload).hexdigest()
    corrupt = storage / "blobs" / digest[:2] / digest
    corrupt.parent.mkdir(parents=True)
    corrupt.write_bytes(b"changed")
    orphan = storage / "untracked.bin"
    orphan.write_bytes(b"orphan")
    missing_hash = hashlib.sha256(b"missing").hexdigest()
    database = tmp_path / "studio.db"
    _database(database, [
        (digest, len(payload), f"blobs/{digest[:2]}/{digest}"),
        (missing_hash, 7, f"blobs/{missing_hash[:2]}/{missing_hash}"),
    ])

    report = audit_data(database, storage)

    assert report["healthy"] is False
    assert len(report["corrupt_assets"]) == 1
    assert len(report["missing_assets"]) == 1
    assert report["orphaned_files"] == ["untracked.bin"]
