

## Read-only data integrity audit (source/developer utility)

The repository includes a non-destructive audit for the local SQLite database and content-addressed asset storage. From a source checkout on Windows with Python 3.11+, run `scripts/audit-data-windows.bat`. It checks SQLite `PRAGMA integrity_check`, validates each registered asset's SHA-256 digest and byte size, and reports missing, corrupt, unsafe-path and unreferenced files. The audit never edits or deletes data. Orphaned files are informational and require a separate, reviewed cleanup operation. This utility is currently a source/developer tool and is not included in the self-contained installer.


## Moving the local data directory (Windows desktop)

The offline migration utility can move the database, uploaded assets, backups and local settings to another drive without deleting the original copy.

1. Exit Masoud AI Studio from the system tray and make sure it is no longer running.
2. Open Command Prompt in the installed application folder.
3. Run `migrate-data-windows.bat --destination "D:\\Masoud AI Studio Data"`. The destination must be a new path that does not already exist.
4. Review the report. The utility checks SQLite integrity, validates every registered asset by SHA-256 and byte size, and compares the copied files before changing the active data-directory setting.
5. Start Masoud AI Studio. The launcher will use the new data directory.

The original data directory is deliberately preserved. If the migration fails before the setting is switched, the old location remains active. The destination copy is created on the destination volume before the configuration is atomically updated. Do not delete the original directory until you have opened the studio, checked your projects/assets and created a fresh backup.

The DPAPI credential key remains at `%LOCALAPPDATA%\\Masoud AI Studio\\credential-key.dpapi`; it is not copied to the destination. This is required so encrypted provider credentials continue to work under the same Windows user. Moving to another Windows account still requires re-entering provider credentials. Run the migration only while the app is stopped; the utility refuses to proceed when the local service is listening on port 8000.
