# Masoud AI Studio

A public-code, private-by-design, local-first AI creative production studio for research, story development, visual design, image/video/audio production, editing, quality review, and publishing workflows.

## Product principles

- **Full Vision, Simplified Architecture, Incremental Implementation**
- Windows desktop is the primary platform; Android and Web/PWA are companion clients.
- Local-first and offline-first by default; cloud-ready without requiring distributed infrastructure.
- Modular monolith: one backend, one primary database, one storage layer, one AI Gateway, one Agent Manager, one Production Orchestrator, and a central Task Manager.
- Human approval for consequential creative and publishing decisions.
- Preserve provenance, version history, continuity, privacy, recoverability, and cost visibility.
- Private owner-operated studio, not a multi-tenant SaaS.

## Repository

- Public source repository: `Masoud4444/masoud-ai-studio`.
- Active implementation branch: `implementation/bootstrap-001`.
- `main` is intentionally untouched; no merge has been performed.
- Studio data, credentials, and generated assets are intended to remain local/private. Do not commit secrets or personal project data.

## Current implementation

### Backend
- FastAPI, SQLAlchemy 2, SQLite and Alembic migrations through 0012.
- Project lifecycle API with optimistic version checks.
- Content-addressed local storage and project asset linking.
- AI Provider registry, encrypted credentials, SSRF-aware URL validation and OpenAI-compatible non-streaming gateway.
- Model registry, usage ledger, manually configured pricing and cost estimates.
- Central Task Manager with dependencies, idempotency, leases, retries and append-only events.
- Production Orchestrator with preproduction workflow, approval gates and run pause/resume/cancel.
- Worker Supervisor with handler allowlist, lease heartbeat, bounded JSON results and sanitized failures; disabled by default.
- Agent Manager with lifecycle governance, tool grants and internal budget reservation ledger. A first text-only Agent Runtime slice is implemented with explicit AI-generation permission, configured pricing, conservative budget reservation and AI Gateway idempotency. Tool Broker, tool execution and process sandbox are not implemented.
- Research Vault v0.1: source registry, project-source links, exact evidence excerpts/locators, deduplication, project claims, support/contradiction links and provenance events.

### Frontend
- React, TypeScript, Vite and responsive dark studio shell.
- Overview and Projects: project listing, search and project creation.
- Production room: create and inspect preproduction runs; pause, resume and cancel controls.
- AI agents: create draft profiles and view/configure registry state.
- Assets: upload, list and detach project assets.
- Research Vault: register sources, capture evidence excerpts and locators, create project claims, link evidence and review claims.
- Characters & Worlds, Video & Audio, Compliance and Settings remain staged modules.

### Desktop and companion clients
- Windows setup/start scripts are provided.
- Tauri desktop packaging, Android companion and hardened PWA are not implemented yet.

## Windows quick start

Requirements: Python 3.11+ and Node.js 20+ available on PATH.

1. Clone the repository and switch to `implementation/bootstrap-001`.
2. Run `scripts\\setup-windows.bat` once.
3. Run `scripts\\start-backend-windows.bat`.
4. In a second terminal, run `scripts\\start-frontend-windows.bat`.
5. Open `http://127.0.0.1:5173`.

The backend listens on `127.0.0.1:8000`. The frontend dev server proxies `/api` and `/health` to it. See [Windows/frontend guide](docs/FRONTEND.md).

## CI verification checkpoint

- Latest backend run [44510146431](https://github.com/Masoud4444/masoud-ai-studio/actions/runs/44510146431): **83 passed, 1 warning**; Alembic upgrade to head succeeded on a fresh SQLite database through migration 0012.
- Latest frontend build run [44509841316](https://github.com/Masoud4444/masoud-ai-studio/actions/runs/44509841316): successful for the Research Vault workspace.
- CI ran on Linux. Windows installation, local browser interaction, provider interoperability and desktop packaging still require hands-on verification.

## Development

Backend:

```bash
python -m pip install -r requirements.txt
alembic upgrade head
python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000
```

Frontend, in a second terminal:

```bash
cd frontend
npm install
npm run dev
```

Build frontend with `npm run build`.

## Security boundaries

- Authentication and authorization are not implemented. Keep the backend bound to localhost; never expose it to the public internet or an untrusted LAN.
- Do not commit provider API keys, encryption keys, database files, generated assets or personal data.
- No paid provider credentials are included. No billable provider calls are made by the default setup.
- Worker is disabled by default. Creative task handlers are not registered.
- Agent profiles start as drafts. Text-only Agent Runtime is available only after explicit provider/model/pricing configuration and activation; no tools are executed. Tool Broker, execution sandbox and hard runtime isolation are not complete.
- Windows credential protection via DPAPI/OS keychain, hard worker process isolation, multi-worker coordination, backup/restore verification and independent security review remain required.

## Project documentation

- [Project status and roadmap](docs/PROJECT_STATUS.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Frontend and Windows setup](docs/FRONTEND.md)
- [Task Manager](docs/TASK_MANAGER.md)
- [Production Orchestrator](docs/PRODUCTION_ORCHESTRATOR.md)
- [AI Gateway](docs/AI_GATEWAY.md)
- [Agent Manager](docs/AGENT_MANAGER.md)
- [Research Vault](docs/RESEARCH_VAULT.md)
