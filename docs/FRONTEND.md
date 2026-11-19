# Frontend workspace

The studio frontend is a React + TypeScript + Vite application. Development mode uses the Vite server and proxies API requests to FastAPI. The local installation mode serves the compiled frontend from the same FastAPI process, so the normal user workflow needs only one local service.

## Implemented screens

- Overview and Projects: project listing, search, create project and API connection status.
- Production room: list workflows and runs, create a preproduction run, pause/resume/cancel controls and approval-gate visibility.
- AI agents: create draft agent profiles, list registry, enable/disable where provider configuration permits.
- Assets: project selection, upload, list and detach without deleting the underlying content-addressed blob.
- Research Vault: source metadata, project scoping, exact excerpts and locators, claims, evidence relationships, review gates, search and bounded local PDF/DOCX text extraction.
- Story Engine: story dossiers, ordered scene outlines and immutable revision history.
- Characters & Worlds: character and location dossiers, world rules, relationships, scene links, revision history and continuity fact/issue review. The backend also has a stable prop registry; its UI integration remains pending. Dedicated Timeline workspace for in-world events, explicit before/after constraints and cycle analysis.
- Video & Audio, Compliance and Settings still contain staged areas; they are not represented as finished production tools.

## Standard Windows setup and launch

Requirements: Windows 10/11, Python 3.11 or newer, Node.js 20 or newer, and an internet connection for the initial dependency installation.

1. Clone the repository and switch to the active implementation branch.
2. Run scripts/setup-windows.bat once. It creates the Python virtual environment, installs backend dependencies, installs frontend dependencies, builds the frontend and applies all Alembic migrations.
3. Run scripts/start-studio-windows.bat.
4. The launcher starts the backend on loopback, waits for its health endpoint, and opens http://127.0.0.1:8000 in the default browser.

Keep the backend console window open while using the studio. Close that window or press Ctrl+C in it to stop the local service. The studio database and uploaded assets remain in the repository's local data/ and storage directories; these are ignored by Git.

## Development mode

For frontend development, run npm install and npm run dev from frontend/. Start the backend separately with scripts/start-backend-windows.bat. Vite binds to 127.0.0.1:5173 and proxies /api and /health to 127.0.0.1:8000.

Build the frontend with npm run build from frontend/.

## Safety notes

- API and frontend are bound to loopback by default. Do not expose the backend to a public network or untrusted LAN: authentication and multi-user authorization are not implemented.
- Creating an Agent from the UI creates a draft only. Agent generation requires explicit provider/model/pricing configuration and activation.
- Production run creation queues tasks; creative workflow handlers are not yet registered with the Worker Supervisor.
- Human approval gates remain enforced by the backend.
- No paid provider credentials are included and the default installation makes no paid provider calls.
- Local PDF/DOCX extraction is bounded and runs in a subprocess, but that subprocess is not yet a complete OS-level sandbox.
- The one-click launcher is a local browser-based install workflow, not yet a signed native Windows desktop installer. Tauri packaging, code signing, Windows credential protection and a native updater remain future installation milestones.
