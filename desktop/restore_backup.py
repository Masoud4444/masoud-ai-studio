from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import sys


def _contains_symlink(path: Path) -> bool:
    current = path
    while True:
        if current.is_symlink():
            return True
        if current.parent == current:
            return False
        current = current.parent


def _configured_data_directory(app_data: Path) -> Path:
    settings_file = app_data / "desktop-settings.json"
    if _contains_symlink(app_data) or _contains_symlink(settings_file):
        raise ValueError("Desktop data settings path is unsafe.")
    if not settings_file.exists():
        return app_data / "data"
    if not settings_file.is_file() or settings_file.stat().st_size > 16384:
        raise ValueError("Desktop data settings file is invalid or too large.")
    try:
        settings = json.loads(settings_file.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("Desktop data settings file cannot be read.") from exc
    if not isinstance(settings, dict):
        raise ValueError("Desktop data settings file must contain an object.")
    configured = settings.get("data_directory")
    if configured is None:
        return app_data / "data"
    if not isinstance(configured, str) or not configured.strip():
        raise ValueError("Configured data directory must be a non-empty path.")
    data_dir = Path(configured).expanduser()
    if not data_dir.is_absolute() or _contains_symlink(data_dir):
        raise ValueError("Configured data directory must be absolute and contain no symbolic links.")
    return data_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify or restore a Masoud AI Studio backup (offline).")
    parser.add_argument("backup", type=Path, help="Path to a .zip backup archive")
    parser.add_argument("--verify", action="store_true", help="Verify archive integrity without restoring")
    args = parser.parse_args()

    if sys.platform != "win32":
        parser.error("The packaged restore utility is currently supported on Windows only.")
    with socket.socket() as probe:
        probe.settimeout(0.5)
        if probe.connect_ex(("127.0.0.1", 8000)) == 0:
            print("Masoud AI Studio appears to be running. Exit it from the system tray before restoring.")
            return 3

    app_data = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Masoud AI Studio"
    try:
        data_dir = _configured_data_directory(app_data)
    except (OSError, ValueError) as exc:
        print(f"Restore configuration rejected: {exc}")
        return 2

    database_path = data_dir / "masoud_studio.db"
    storage_root = data_dir / "storage"
    if _contains_symlink(database_path) or _contains_symlink(storage_root):
        print("Configured database or storage path contains a symbolic link.")
        return 2

    from backend.app.backup import restore_backup, verify_backup
    try:
        if args.verify:
            print(verify_backup(args.backup))
        else:
            print(restore_backup(args.backup, database_path, storage_root))
            print("Restore completed. Previous database/storage copies were retained for rollback.")
            print("Encrypted provider credentials require the original Windows account and DPAPI key.")
        return 0
    except Exception as exc:
        print(f"Backup operation failed: {exc}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
