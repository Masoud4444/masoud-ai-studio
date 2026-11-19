# Frontend workspace

The current frontend is a React + TypeScript + Vite application designed to run locally and connect to the FastAPI backend on loopback.

## Implemented screens

- Overview and Projects: project list, search, create project, API connection status.
- Production room: list workflows and runs, create a preproduction run, pause/resume/cancel run controls, approval-gate visibility.
- AI agents: create draft agent profiles, list registry, enable/disable where provider configuration permits.
- Assets: select a project, upload an asset, list attached assets, detach an asset without deleting the underlying content-addressed blob.
- Research Vault: register source metadata, scope sources to projects, capture exact excerpts and locators, create project claims, link evidence as support/contradiction/context and review claims with evidence gates. The UI respects the backend's claim-evidence integrity rules. It can attach an existing project asset to a source; upload the file first in the Assets workspace.
- Characters & Worlds, Video & Audio, Compliance and Settings show explicit staged-module states; they are not represented as completed features.

## Development

Run npm install and npm run dev from the frontend directory.

The Vite dev server binds to 127.0.0.1:5173 and proxies /api and /health to 127.0.0.1:8000.

Build with npm run build from the frontend directory.

## Windows

1. Run scripts/setup-windows.bat once.
2. Start scripts/start-backend-windows.bat.
3. In a second terminal, start scripts/start-frontend-windows.bat.
4. Open http://127.0.0.1:5173.

The API and Vite server are bound to loopback by default. Do not expose the backend to a public network: authentication and multi-user authorization are not implemented.

## Safety notes

- Creating an Agent from the UI creates a draft only. No provider call is made.
- Agent enablement requires a configured, enabled provider and model.
- Production run creation only queues the existing preproduction tasks; creative handlers are not yet registered with the Worker Supervisor.
- Human approval gates remain enforced by the backend.
- No paid provider credentials are included in the repository.


## Research Vault scope

The first UI slice is a manual curation workspace. It does not fetch URLs, crawl sites, parse uploaded documents, run OCR/transcription or invoke AI extraction. URL records are metadata only. See RESEARCH_VAULT.md for the data contract and safety boundaries.


- Backend HTTP integration tests exercise the Research Vault endpoints used by this workspace; browser-level Windows interaction remains to be verified locally.
