from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo, BadZipFile

FORMAT_VERSION = 1
MAX_ARCHIVE_BYTES = 10 * 1024 * 1024 * 1024
MAX_FILES = 100_000
MAX_TOTAL_UNCOMPRESSED = 20 * 1024 * 1024 * 1024
MANIFEST_NAME = "manifest.json"


class BackupError(ValueError):
    pass


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_snapshot(source: Path, destination: Path) -> None:
    if not source.is_file():
        raise BackupError("Database file does not exist.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source.resolve().as_posix()}?mode=ro", uri=True, timeout=30) as src:
        with sqlite3.connect(destination) as dst:
            src.backup(dst, pages=256, sleep=0.05)
            result = dst.execute("PRAGMA integrity_check").fetchone()
            if not result or result[0] != "ok":
                raise BackupError("SQLite snapshot failed integrity validation.")
            dst.commit()


def _storage_files(root: Path):
    if not root.exists():
        return
    if root.is_symlink():
        raise BackupError("Storage root must not be a symbolic link.")
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            raise BackupError("Storage contains a symbolic link; backup aborted.")
        if path.is_file():
            yield path


def create_backup(database_path: Path, storage_root: Path, backup_dir: Path) -> dict:
    database_path = Path(database_path).expanduser().resolve()
    storage_root = Path(storage_root).expanduser().resolve()
    backup_dir = Path(backup_dir).expanduser().resolve()
    if storage_root == database_path.parent or storage_root in database_path.parents:
        raise BackupError("Database and storage paths overlap unexpectedly.")
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    final_path = backup_dir / f"masoud-studio-{stamp}.zip"
    counter = 1
    while final_path.exists():
        final_path = backup_dir / f"masoud-studio-{stamp}-{counter}.zip"
        counter += 1

    with tempfile.TemporaryDirectory(prefix="masoud-backup-") as temp_name:
        temp_root = Path(temp_name)
        snapshot = temp_root / "studio.sqlite3"
        _sqlite_snapshot(database_path, snapshot)
        entries = []
        temp_archive = backup_dir / (final_path.name + ".tmp")
        try:
            with ZipFile(temp_archive, "w", compression=ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
                def add_file(source: Path, archive_name: str):
                    digest = hashlib.sha256()
                    size = 0
                    info = ZipInfo(archive_name)
                    info.compress_type = ZIP_DEFLATED
                    with source.open("rb") as src, archive.open(info, "w", force_zip64=True) as dst:
                        for chunk in iter(lambda: src.read(1024 * 1024), b""):
                            dst.write(chunk)
                            digest.update(chunk)
                            size += len(chunk)
                    entries.append({"path": archive_name, "size": size, "sha256": digest.hexdigest()})

                add_file(snapshot, "database/studio.sqlite3")
                for source in _storage_files(storage_root) or ():
                    relative = source.relative_to(storage_root).as_posix()
                    add_file(source, "storage/" + relative)

                manifest = {
                    "format": "masoud-ai-studio-backup",
                    "format_version": FORMAT_VERSION,
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "database": "database/studio.sqlite3",
                    "storage_root": "storage",
                    "files": entries,
                    "credential_key_included": False,
                    "notes": ["The Windows DPAPI credential key is intentionally excluded."]
                }
                archive.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2))
            with temp_archive.open("rb") as stream:
                os.fsync(stream.fileno())
            os.replace(temp_archive, final_path)
        finally:
            temp_archive.unlink(missing_ok=True)

    return {"id": final_path.name, "path": str(final_path), "size_bytes": final_path.stat().st_size,
            "created_at": datetime.now(timezone.utc).isoformat(), "file_count": len(entries)}


def _safe_member(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(part in {"", ".", ".."} for part in path.parts):
        raise BackupError("Archive contains an unsafe path.")
    if "\\" in name or ":" in name or name.startswith("/"):
        raise BackupError("Archive contains an invalid path.")
    return path


def verify_backup(archive_path: Path) -> dict:
    archive_path = Path(archive_path)
    if not archive_path.is_file() or archive_path.stat().st_size > MAX_ARCHIVE_BYTES:
        raise BackupError("Backup archive is missing or exceeds the size limit.")
    try:
        with ZipFile(archive_path, "r") as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES:
                raise BackupError("Backup contains too many entries.")
            names = set()
            total = 0
            for info in infos:
                safe = _safe_member(info.filename)
                if info.filename in names:
                    raise BackupError("Backup contains duplicate paths.")
                names.add(info.filename)
                mode = (info.external_attr >> 16) & 0xFFFF
                if mode & 0o170000 == 0o120000:
                    raise BackupError("Backup contains a symbolic link.")
                total += info.file_size
                if total > MAX_TOTAL_UNCOMPRESSED:
                    raise BackupError("Backup expands beyond the allowed size.")
            if MANIFEST_NAME not in names:
                raise BackupError("Backup manifest is missing.")
            manifest = json.loads(archive.read(MANIFEST_NAME))
            if manifest.get("format") != "masoud-ai-studio-backup" or manifest.get("format_version") != FORMAT_VERSION:
                raise BackupError("Unsupported backup format.")
            records = manifest.get("files")
            if not isinstance(records, list) or len(records) + 1 != len(infos):
                raise BackupError("Backup manifest does not match archive contents.")
            expected = {record.get("path") for record in records if isinstance(record, dict)}
            if expected != names - {MANIFEST_NAME}:
                raise BackupError("Backup file list is inconsistent.")
            for record in records:
                name = record["path"]
                _safe_member(name)
                raw = archive.read(name)
                if len(raw) != record.get("size") or hashlib.sha256(raw).hexdigest() != record.get("sha256"):
                    raise BackupError(f"Integrity check failed for {name}.")
            db_name = manifest.get("database")
            if db_name != "database/studio.sqlite3":
                raise BackupError("Backup database path is invalid.")
            with tempfile.TemporaryDirectory(prefix="masoud-verify-") as temp:
                db_copy = Path(temp) / "studio.sqlite3"
                db_copy.write_bytes(archive.read(db_name))
                with sqlite3.connect(db_copy) as db:
                    check = db.execute("PRAGMA integrity_check").fetchone()
                    if not check or check[0] != "ok":
                        raise BackupError("Database integrity check failed.")
            return {"valid": True, "format_version": FORMAT_VERSION, "created_at": manifest.get("created_at"),
                    "file_count": len(records), "database_integrity": "ok",
                    "credential_key_included": False}
    except (BadZipFile, KeyError, json.JSONDecodeError, OSError) as exc:
        if isinstance(exc, BackupError):
            raise
        raise BackupError("Backup archive is unreadable or corrupt.") from exc


def restore_backup(archive_path: Path, database_path: Path, storage_root: Path) -> dict:
    """Offline restore. Caller must ensure the application is fully stopped."""
    archive_path = Path(archive_path).expanduser().resolve()
    database_path = Path(database_path).expanduser().resolve()
    storage_root = Path(storage_root).expanduser().resolve()
    report = verify_backup(archive_path)
    database_path.parent.mkdir(parents=True, exist_ok=True)
    storage_root.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="masoud-restore-", dir=str(database_path.parent)) as temp_name:
        stage = Path(temp_name)
        staged_db = stage / "studio.sqlite3"
        staged_storage = stage / "storage"
        staged_storage.mkdir()
        with ZipFile(archive_path, "r") as archive:
            staged_db.write_bytes(archive.read("database/studio.sqlite3"))
            for info in archive.infolist():
                if info.filename.startswith("storage/") and not info.is_dir():
                    relative = _safe_member(info.filename).relative_to("storage")
                    target = staged_storage.joinpath(*relative.parts)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.read(info.filename))
        with sqlite3.connect(staged_db) as db:
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BackupError("Staged database failed integrity validation.")

        suffix = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
        old_db = database_path.with_name(database_path.name + ".pre-restore-" + suffix)
        old_storage = storage_root.with_name(storage_root.name + ".pre-restore-" + suffix)
        db_moved = storage_moved = False
        try:
            if database_path.exists():
                os.replace(database_path, old_db)
                db_moved = True
            if storage_root.exists():
                os.replace(storage_root, old_storage)
                storage_moved = True
            os.replace(staged_db, database_path)
            os.replace(staged_storage, storage_root)
        except Exception:
            if database_path.exists():
                database_path.unlink()
            if storage_root.exists():
                shutil.rmtree(storage_root, ignore_errors=True)
            if db_moved and old_db.exists():
                os.replace(old_db, database_path)
            if storage_moved and old_storage.exists():
                os.replace(old_storage, storage_root)
            raise

    return {"restored": True, "database": str(database_path), "storage": str(storage_root),
            "rollback_database": str(old_db) if db_moved else None,
            "rollback_storage": str(old_storage) if storage_moved else None,
            "credential_key_included": False, "verification": report}
