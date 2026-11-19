# Local Windows installation

This guide describes the current installable local-browser workflow. It is intentionally separate from the future signed native Windows desktop package.

## Supported baseline

- Windows 10 or Windows 11 (64-bit recommended)
- Python 3.11 or newer on PATH
- Node.js 20 or newer on PATH
- Internet access during first-time dependency installation
- Enough free disk space for the Python environment, Node dependencies, local database, uploaded assets and generated media

The current setup does not install Python or Node.js for you. Install these prerequisites first and enable their PATH options.

## First-time setup

1. Download or clone the repository.
2. Check out the implementation/bootstrap-001 branch.
3. Open the repository folder in File Explorer.
4. Double-click scripts/setup-windows.bat.
5. Wait for dependency installation, frontend production build and database migrations to complete.

The setup script creates a local .venv folder, installs requirements from requirements.txt, creates a local .env file with a random 256-bit credential-encryption key if one does not already exist, runs npm install and npm run build in frontend/, creates the data directory and applies Alembic migrations through the current head. The application loads .env before initializing the database and AI Gateway. Keep this file private and include it in secure backups; losing it can make previously encrypted provider credentials unrecoverable.

## Daily launch

1. Double-click scripts/start-studio-windows.bat.
2. The launcher checks that setup completed and that frontend/dist/index.html exists.
3. It applies any pending database migrations.
4. It starts the FastAPI service on 127.0.0.1:8000 and waits for the service health response.
5. It opens the studio in the default browser.

Keep the backend console window open. To stop the studio, focus that console and press Ctrl+C. Do not terminate the process while a file upload or other write operation is in progress.

## Local data and recovery

- Database: data/masoud_studio.db (default SQLite URL, relative to the repository working directory).
- Uploaded files: local storage directory configured by the storage subsystem.
- Virtual environment and frontend build: .venv/ and frontend/dist/.
- Local data, storage, backups, logs and environment files are excluded from Git.

Before moving the repository or reinstalling Windows, stop the studio and make a consistent backup of the database and the complete storage directory together. A supported in-app backup/restore and automated restore verification are not implemented yet. Do not copy only the database if uploaded assets are important.

## Network and privacy

- The service binds to 127.0.0.1 and is intended for use on the same computer.
- Do not change the bind address to 0.0.0.0 or expose the service through router port forwarding.
- Authentication and multi-user authorization are not implemented.
- Provider API credentials are not included. AI generation requires the user to configure a provider and pricing deliberately.
- The default setup does not make paid AI requests.

## Troubleshooting

- If Python is not found, install Python 3.11+ and enable Add Python to PATH, then open a new terminal.
- If Node is not found, install Node.js 20+ and reopen the terminal.
- If setup fails during npm install or package installation, read the first reported error, restore network access and rerun setup after correcting the prerequisite.
- If port 8000 is already in use, close the existing Masoud AI Studio backend window before launching another copy. Do not terminate an unknown process just to free the port.
- If the launcher reports a missing frontend build, run setup again and confirm npm run build completes.
- If database migration fails, preserve the data directory before attempting manual recovery and share the full sanitized error text.

## Current installation boundary

The one-click launcher is a browser-based local installation workflow. It is not yet a signed .msi/.exe desktop installer and does not bundle Python or Node.js. Native Tauri packaging, a self-contained backend runtime, Windows DPAPI credential storage, signed updates, backup/restore tooling and Windows acceptance verification are still required before calling the product a finished native desktop release.
