from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import sys


def _digest(path: Path) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def audit_data(database_path: Path, storage_root: Path) -> dict:
    """Read-only integrity audit for the local SQLite database and content-addressed assets."""
    database_path = Path(database_path).expanduser().absolute()
    storage_root = Path(storage_root).expanduser().absolute()
    if not database_path.is_file():
        raise FileNotFoundError("Studio database was not found.")
    if storage_root.is_symlink():
        raise ValueError("Storage root is a symbolic link; audit stopped.")

    with sqlite3.connect(database_path.as_uri() + "?mode=ro", uri=True) as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()
        if not integrity or integrity[0] != "ok":
            raise ValueError("SQLite integrity_check did not return ok.")
        rows = db.execute("SELECT sha256, size_bytes, storage_key FROM assets ORDER BY sha256").fetchall()

    missing, corrupt, invalid = [], [], []
    expected_files = set()
    for sha, expected_size, storage_key in rows:
        expected_key = f"blobs/{sha[:2]}/{sha}"
        if storage_key != expected_key or len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha):
            invalid.append(storage_key)
            continue
        candidate = storage_root / Path(*expected_key.split("/"))
        try:
            resolved = candidate.resolve(strict=False)
            if storage_root.resolve() not in resolved.parents:
                invalid.append(storage_key)
                continue
        except OSError:
            invalid.append(storage_key)
            continue
        expected_files.add(candidate)
        if candidate.is_symlink() or not candidate.is_file():
            missing.append(storage_key)
            continue
        actual_hash, actual_size = _digest(candidate)
        if actual_hash != sha or actual_size != expected_size:
            corrupt.append(storage_key)

    orphaned = []
    if storage_root.exists():
        for current, dirs, names in os.walk(storage_root, followlinks=False):
            current_path = Path(current)
            for name in list(dirs):
                item = current_path / name
                if item.is_symlink():
                    invalid.append(item.relative_to(storage_root).as_posix())
                    dirs.remove(name)
            for name in names:
                item = current_path / name
                if item.is_symlink():
                    invalid.append(item.relative_to(storage_root).as_posix())
                elif item not in expected_files:
                    orphaned.append(item.relative_to(storage_root).as_posix())

    return {
        "database_integrity": "ok",
        "asset_records": len(rows),
        "verified_assets": len(rows) - len(missing) - len(corrupt) - len(invalid),
        "missing_assets": sorted(missing),
        "corrupt_assets": sorted(corrupt),
        "invalid_paths": sorted(invalid),
        "orphaned_files": sorted(orphaned),
        "read_only": True,
        "healthy": not (missing or corrupt or invalid),
        "note": "Orphaned files are reported only; this audit never deletes or modifies data.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only Masoud AI Studio data integrity audit.")
    parser.add_argument("--database", type=Path)
    parser.add_argument("--storage", type=Path)
    args = parser.parse_args()
    if sys.platform != "win32":
        parser.error("The packaged data audit utility is currently supported on Windows only.")
    app_root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Masoud AI Studio"
    settings_file = app_root / "desktop-settings.json"
    if settings_file.is_symlink() or (settings_file.exists() and settings_file.stat().st_size > 16384):
        parser.error("Desktop data settings file is unsafe.")
    settings = json.loads(settings_file.read_text(encoding="utf-8")) if settings_file.exists() else {}
    if not isinstance(settings, dict):
        parser.error("Desktop data settings file is invalid.")
    root = Path(settings.get("data_directory", app_root / "data")).expanduser()
    if not root.is_absolute() or root.is_symlink():
        parser.error("Configured data directory is invalid.")
    database = args.database or root / "masoud_studio.db"
    storage = args.storage or root / "storage"
    try:
        report = audit_data(database, storage)
        print(json.dumps(report, indent=2))
        return 0 if report["healthy"] else 2
    except Exception as exc:
        print(f"Data audit failed: {exc}")
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
