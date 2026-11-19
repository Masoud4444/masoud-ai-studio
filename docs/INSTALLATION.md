

## Read-only data integrity audit (source/developer utility)

The repository includes a non-destructive audit for the local SQLite database and content-addressed asset storage. From a source checkout on Windows with Python 3.11+, run `scripts/audit-data-windows.bat`. It checks SQLite `PRAGMA integrity_check`, validates each registered asset's SHA-256 digest and byte size, and reports missing, corrupt, unsafe-path and unreferenced files. The audit never edits or deletes data. Orphaned files are informational and require a separate, reviewed cleanup operation. This utility is currently a source/developer tool and is not included in the self-contained installer.
