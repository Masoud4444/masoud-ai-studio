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
    data_dir = app_data / "data"
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
