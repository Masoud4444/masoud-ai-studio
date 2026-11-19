# Masoud AI Studio

A public-code, private-by-design, local-first AI creative production studio for research, story development, visual design, image/video/audio production, editing, quality review and publishing workflows.

## Product principles

- **Full Vision, Simplified Architecture, Incremental Implementation**
- Windows desktop is the primary platform; Android and Web/PWA are companion clients.
- Local-first and offline-first by default; cloud-ready without requiring distributed infrastructure.
- Modular monolith: one backend, one primary database, one storage layer, one AI Gateway, one Agent Manager, one Production Orchestrator and a central Task Manager.
- Human approval for consequential creative and publishing decisions.
- Preserve provenance, version history, continuity, privacy, recoverability and cost visibility.
- Private owner-operated studio, not a multi-tenant SaaS.

## Repository

- Public source repository: Masoud4444/masoud-ai-studio.
- Active implementation branch: implementation/bootstrap-001.
- main is intentionally untouched; no merge has been performed.
- Studio data, credentials and generated assets are intended to remain local/private. Do not commit secrets or personal project data.

## Current implementation

### Backend
- FastAPI, SQLAlchemy 2, SQLite and Alembic migrations through 0015.
- Project lifecycle API with optimistic version checks.
- Content-addressed local storage and project asset linking.
- AI Provider registry, encrypted credentials, SSRF-aware URL validation and OpenAI-compatible non-streaming gateway.
- Model registry, usage ledger, manually configured pricing and cost estimates.
- Central Task Manager with dependencies, idempotency, leases, retries and append-only events.
- Production Orchestrator with preproduction workflow, approval gates and run pause/resume/cancel.
- Worker Supervisor with handler allowlist, lease heartbeat, bounded JSON results and sanitized failures; disabled by default.
- Agent Manager with lifecycle governance, tool grants and budget reservation ledger; first text-only Agent Runtime uses explicit AI-generation permission, configured pricing, conservative budget reservation and Gateway idempotency. Tool Broker, tool execution and process sandbox are not implemented.
- Research Vault with project-scoped sources, exact evidence excerpts/locators, claims, provenance, search and bounded local PDF/DOCX text extraction.
- Story Engine with story dossiers, ordered scene outlines and immutable revision history.
- Character and World Bible with relationships, locations, rules and scene links.
- Story prop registry with stable object identity and continuity references.
- Deterministic continuity facts and issue analysis with human review controls.

### Frontend
- React, TypeScript, Vite and responsive dark studio shell.
- Overview, Projects, Production, AI Agents and Assets workspaces.
- Research Vault workspace with source/evidence/claim management, search and document extraction.
- Story Engine workspace for story dossiers, scenes and revision history.
- Characters & Worlds workspace for character/location/world data and continuity review; registered-prop UI integration is pending.
- Timeline workspace for in-world events, explicit chronology constraints and cycle analysis.
- Video & Audio, Compliance and some Settings capabilities remain staged; no incomplete module is represented as production-ready.

### Local Windows launch
- scripts/setup-windows.bat installs dependencies, builds the frontend and applies database migrations.
- scripts/start-studio-windows.bat starts the local FastAPI service, serves the compiled React app from the same process and opens the studio in the default browser.
- The normal local workflow uses http://127.0.0.1:8000; development mode remains available through http://127.0.0.1:5173.
- This is a one-click local browser launch workflow, not yet a signed native Windows desktop installer. Tauri packaging, code signing and native update delivery remain outstanding.

## Windows quick start

Requirements: Windows 10/11, Python 3.11+ and Node.js 20+.

1. Clone the repository and switch to implementation/bootstrap-001.
2. Run scripts\setup-windows.bat once.
3. Run scripts\start-studio-windows.bat.
4. The launcher opens http://127.0.0.1:8000.

Keep the backend console open while using the studio. See the Windows/frontend guide at docs/FRONTEND.md.

## Verification and release status

Existing automated checks were run in prior Linux CI runs for earlier increments. They are historical evidence, not a verification of the latest branch head or of Windows installation. Windows setup, local browser interaction, provider interoperability, desktop packaging and code signing still require hands-on verification. Previously passing tests are not rerun solely for repetition.

## Development

Backend:

    python -m pip install -r requirements.txt
    alembic upgrade head
    python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

Frontend:

    cd frontend
    npm install
    npm run dev

Build frontend with npm run build.

## Security boundaries

- Authentication and authorization are not implemented. Keep the backend bound to localhost; never expose it to the public internet or an untrusted LAN.
- Do not commit provider API keys, encryption keys, database files, generated assets or personal data.
- No provider API keys are configured by default. No billable provider calls are made by the default setup.
- Worker is disabled by default. Creative task handlers are not registered.
- Agent profiles start as drafts. Text-only Agent Runtime requires explicit provider/model/pricing configuration and activation; no tools are executed. Tool Broker, execution sandbox and hard runtime isolation are not complete.
- Windows credential protection via DPAPI/OS keychain, hard worker process isolation, multi-worker coordination, backup/restore verification and independent security review remain required.

## Project documentation

- Local Windows installation: docs/INSTALLATION.md
- Project status and roadmap: docs/PROJECT_STATUS.md
- Architecture: docs/ARCHITECTURE.md
- Frontend and Windows setup: docs/FRONTEND.md
- Task Manager: docs/TASK_MANAGER.md
- Production Orchestrator: docs/PRODUCTION_ORCHESTRATOR.md
- AI Gateway: docs/AI_GATEWAY.md
- Agent Manager: docs/AGENT_MANAGER.md
- Research Vault: docs/RESEARCH_VAULT.md
