from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import sys
import tempfile


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _reject_links(root: Path) -> None:
    if root.is_symlink():
        raise ValueError("Data directory cannot be a symbolic link.")
    for current, dirs, names in os.walk(root, followlinks=False):
        base = Path(current)
        for name in dirs + names:
            if (base / name).is_symlink():
                raise ValueError("Data directory contains a symbolic link; migration stopped.")


def _verify_data(data_dir: Path) -> dict:
    database = data_dir / "masoud_studio.db"
    storage = data_dir / "storage"
    if not database.is_file() or database.is_symlink():
        raise ValueError("Source database is missing or unsafe.")
    if storage.exists():
        _reject_links(storage)
    with sqlite3.connect(database) as db:
        result = db.execute("PRAGMA integrity_check").fetchone()
        if not result or result[0] != "ok":
            raise ValueError("Database integrity check failed.")
        rows = db.execute("SELECT sha256, size_bytes, storage_key FROM assets").fetchall()
    checked = 0
    for digest, size, key in rows:
        expected = f"blobs/{digest[:2]}/{digest}"
        if key != expected or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Database contains an invalid asset storage key.")
        blob = storage.joinpath(*expected.split("/"))
        if blob.is_symlink() or not blob.is_file():
            raise ValueError(f"An asset is missing: {key}")
        if blob.stat().st_size != size or _sha256(blob) != digest:
            raise ValueError(f"An asset failed SHA-256 verification: {key}")
        checked += 1
    return {"database_integrity": "ok", "verified_assets": checked}


def _write_config(settings_path: Path, destination: Path) -> None:
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if settings_path.is_symlink():
        raise ValueError("Desktop settings file is a symbolic link.")
    current = {}
    if settings_path.exists():
        if settings_path.stat().st_size > 16384:
            raise ValueError("Desktop settings file exceeds the size limit.")
        current = json.loads(settings_path.read_text(encoding="utf-8"))
        if not isinstance(current, dict):
            raise ValueError("Desktop settings file has an invalid structure.")
    current["data_directory"] = str(destination)
    temp = settings_path.with_name(settings_path.name + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as stream:
            json.dump(current, stream, ensure_ascii=False, sort_keys=True, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, settings_path)
    finally:
        temp.unlink(missing_ok=True)


def migrate_data(source: Path, destination: Path, settings_path: Path) -> dict:
    """Copy, verify and atomically switch the configured data directory; never delete source."""
    source = Path(source).expanduser().absolute()
    destination = Path(destination).expanduser().absolute()
    settings_path = Path(settings_path).expanduser().absolute()
    if not source.is_dir():
        raise FileNotFoundError("Current Studio data directory was not found.")
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Destination must not already exist; choose a new empty path.")
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("Source and destination directories must not overlap.")
    if settings_path.is_symlink():
        raise ValueError("Desktop settings file is a symbolic link.")
    _reject_links(source)
    source_report = _verify_data(source)
    destination.parent.mkdir(parents=True, exist_ok=True)

    stage = Path(tempfile.mkdtemp(prefix=".masoud-data-migration-", dir=destination.parent))
    try:
        shutil.rmtree(stage)
        shutil.copytree(source, stage, copy_function=shutil.copy2)
        _reject_links(stage)
        staged_report = _verify_data(stage)
        source_files = {p.relative_to(source).as_posix(): _sha256(p)
                        for p in source.rglob("*") if p.is_file()}
        staged_files = {p.relative_to(stage).as_posix(): _sha256(p)
                        for p in stage.rglob("*") if p.is_file()}
        if source_files != staged_files:
            raise ValueError("Destination copy differs from source; configuration was not changed.")
        os.replace(stage, destination)
        try:
            _write_config(settings_path, destination)
        except Exception:
            # Keep the verified copy for inspection; the old path remains configured and untouched.
            raise
        return {
            "migrated": True,
            "source_preserved": True,
            "source": str(source),
            "destination": str(destination),
            "database_integrity": staged_report["database_integrity"],
            "verified_assets": staged_report["verified_assets"],
            "verified_files": len(staged_files),
            "credential_key_moved": False,
            "credential_key_note": "The DPAPI key remains in the original application profile directory.",
            "source_verification": source_report,
        }
    finally:
        if stage.exists():
            shutil.rmtree(stage, ignore_errors=True)


def _port_is_open(host: str = "127.0.0.1", port: int = 8000) -> bool:
    with socket.socket() as probe:
        probe.settimeout(0.5)
        return probe.connect_ex((host, port)) == 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Safely relocate Masoud AI Studio data while preserving the original.")
    parser.add_argument("--destination", required=True, type=Path, help="New data directory; it must not exist.")
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("The desktop data migration utility is supported on Windows only.")
    if _port_is_open():
        print("Masoud AI Studio appears to be running. Exit it from the system tray first.")
        return 3
    app_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Masoud AI Studio"
    settings = app_root / "desktop-settings.json"
    try:
        if settings.is_symlink() or (settings.exists() and settings.stat().st_size > 16384):
            raise ValueError("Desktop data settings file is unsafe.")
        config = json.loads(settings.read_text(encoding="utf-8")) if settings.exists() else {}
        if not isinstance(config, dict):
            raise ValueError("Desktop data settings file is invalid.")
        current = Path(config.get("data_directory", app_root / "data")).expanduser()
        if not current.is_absolute() or current.is_symlink():
            raise ValueError("Configured source data directory is invalid.")
        result = migrate_data(current, args.destination, settings)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except Exception as exc:
        print(f"Data migration failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
