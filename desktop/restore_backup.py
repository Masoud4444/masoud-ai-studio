from __future__ import annotations

import argparse
from pathlib import Path
import socket
import sys


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

    app_data = Path(__import__("os").environ.get("LOCALAPPDATA", str(Path.home()))) / "Masoud AI Studio"
    settings_file = app_data / "desktop-settings.json"
    if settings_file.is_symlink() or (settings_file.exists() and settings_file.stat().st_size > 16384):
        print("Desktop data settings file is unsafe.")
        return 2
    import json
    settings = json.loads(settings_file.read_text(encoding="utf-8")) if settings_file.exists() else {}
    data_dir = Path(settings.get("data_directory", app_data / "data")).expanduser()
    if not data_dir.is_absolute() or data_dir.is_symlink():
        print("Configured data directory is invalid.")
        return 2
    database_path = data_dir / "masoud_studio.db"
    storage_root = data_dir / "storage"

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
