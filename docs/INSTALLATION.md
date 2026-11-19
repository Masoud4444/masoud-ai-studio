# Windows installation

Masoud AI Studio now has two Windows installation paths: a self-contained x64 installer built by GitHub Actions, and a source/developer setup for contributors.

## Self-contained Windows installer

1. Open the [Windows installer workflow](https://github.com/Masoud4444/masoud-ai-studio/actions/workflows/windows-installer.yml).
2. Select the latest successful run on branch `implementation/bootstrap-001`.
3. Download the `Masoud-AI-Studio-Windows-x64` artifact and extract the setup executable.
4. Run the installer. It installs the application for the current user; administrator rights are not required.
5. Launch Masoud AI Studio from the Start menu (or the optional desktop shortcut).

The package includes the Python backend, compiled React frontend, runtime dependencies, Alembic migrations through 0017 and a separate bounded PDF/DOCX parser helper. The Windows CI run successfully smoke-tested the packaged executable startup, database migration and DOCX parser before producing the installer. Python and Node.js do not need to be installed separately on the target PC.

At first launch, the application:
- creates its private data directory under `%LOCALAPPDATA%\\Masoud AI Studio`;
- creates a random 256-bit encryption key and protects it using Windows DPAPI for the current Windows user;
- applies pending database migrations;
- starts the backend bound only to `127.0.0.1:8000`;
- opens the studio in the default browser and adds a system-tray icon.

Use the tray icon to reopen the studio or exit the backend. Logs are written to `%LOCALAPPDATA%\\Masoud AI Studio\\logs\\studio.log`.

**Important:** The installer is not yet code-signed. Windows SmartScreen may show an unknown-publisher warning. The UI runs in the browser; a Tauri native window and signed auto-update channel are not part of this first package. The GitHub Actions artifact must be built successfully before a setup executable is available.

## User data and backup

- SQLite database: `%LOCALAPPDATA%\\Masoud AI Studio\\data\\masoud_studio.db`
- Uploaded assets: `%LOCALAPPDATA%\\Masoud AI Studio\\data\\storage`
- DPAPI-protected credential key: `%LOCALAPPDATA%\\Masoud AI Studio\\credential-key.dpapi`
- Logs: `%LOCALAPPDATA%\\Masoud AI Studio\\logs`

Uninstalling the application intentionally preserves the database, assets and credential key. Back up the entire `Masoud AI Studio` directory before moving to another Windows account or reinstalling Windows. The DPAPI-protected key is tied to the Windows user profile and cannot simply be copied to another Windows account. An in-app backup/restore and cross-device key migration workflow are not yet implemented.

## Developer/source installation

Requirements: Windows 10/11 x64, Python 3.11+, Node.js 20+.

1. Clone the repository and check out `implementation/bootstrap-001`.
2. Double-click `scripts/setup-windows.bat`.
3. Launch with `scripts/start-studio-windows.bat`.

The source setup creates a virtual environment, installs `requirements.txt`, builds the frontend and applies migrations. The source workflow stores data under the repository's local `data/` directory.

## Network and privacy

- The backend binds to loopback only. Do not expose it to the public internet or an untrusted LAN.
- Authentication and multi-user authorization are not implemented.
- No provider API credentials are bundled. AI requests require explicit provider configuration and may incur charges.
- The background worker is disabled by default; production creative task handlers are not yet registered.

## Troubleshooting

- If the installer does not start the UI, inspect `studio.log` under the local application data directory.
- If port 8000 is already occupied, close the existing Masoud AI Studio instance and try again. The launcher will not attach to an unknown process.
- If the credential key cannot be unprotected, run the app under the original Windows user account that installed it.
- Preserve the complete data directory before attempting database recovery or reinstalling the application.
\n\n### Preview artifact integrity\n\n- Actions artifact: `Masoud-AI-Studio-Windows-x64` from [successful Windows installer run](https://github.com/Masoud4444/masoud-ai-studio/actions/runs/44526720876).\n- ZIP SHA-256: `c5e5b99033c2c3074d5fe261a0b37c8839c77a07423543599446db7ab6d532c1`.\n- Setup EXE SHA-256: `6cb4f1ab87d9334ec93da47d7941e6f5d00927d607ecdb591d7ff35a2c4290e3`.\n- The installer is unsigned and is a preview build; perform normal security checks before using it with important data.\n