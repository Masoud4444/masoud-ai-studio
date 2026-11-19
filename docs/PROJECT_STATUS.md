# Project Status

Last updated: 2026-11-19

## Repository and architecture

- Repository: `Masoud4444/masoud-ai-studio` (public source code; workspace data is designed to remain local/private).
- Active branch: `implementation/bootstrap-001`.
- `main` remains untouched. No merge or release has been performed.
- Product principle: **Full Vision, Simplified Architecture, Incremental Implementation**.
- Architecture: modular monolith; one backend, primary database, storage layer, AI Gateway, Agent Manager, Production Orchestrator and central Task Manager.
- Foundation 002 archive has not been inspected or imported into this implementation branch; current code must not be described as an import.

## Implemented backend

- FastAPI application, SQLAlchemy 2 models, SQLite baseline and Alembic migrations 0001–0011.
- Project create/list/read/update/archive/restore API, optimistic version checks and duplicate-slug handling.
- Content-addressed asset storage using SHA-256, streamed uploads, size limits, temporary staging, atomic placement, MIME sniffing, filename sanitization, project listing and detach.
- AI Gateway provider registry, priority selection, OpenAI-compatible non-streaming completion, encrypted credentials and idempotent response storage (AES-256-GCM), SSRF-aware URL checks, DNS pinning, TLS verification, disabled redirects/proxies, sanitized errors, usage ledger and manually configured pricing history.
- Central Task Manager: idempotent task creation, dependency gates, priority, bounded attempts, leases, retries, cancellation, expired lease recovery and append-only events.
- Worker Supervisor: handler allowlist, lease heartbeat, bounded JSON results, sanitized handler errors and graceful shutdown. Disabled by default; only `system.healthcheck` is registered out of the box.
- Production Orchestrator: code-defined `creative.preproduction` v1 workflow, persisted runs/steps, idempotent creation, approval gates, pause/resume/cancel.
- Agent Manager: draft/enabled/disabled lifecycle, versioned config, provider/model checks, permissions/tool grants, approval requirements for write/execute grants, audit events and internal budget reservation ledger. A first text-only Agent Runtime is implemented at `POST /api/v1/agents/{agent_id}/run`, with explicit `ai.generate` permission, required model pricing, conservative pre-call budget reservation and Gateway idempotency.

## Implemented frontend

- React + TypeScript + Vite responsive studio shell.
- Overview and Projects: listing, search, project creation and backend health feedback.
- Production room: create/list preproduction runs, inspect step state and approval gates, pause/resume/cancel controls.
- AI agents: create draft profiles, view registry, enable/disable where provider/model requirements permit.
- Assets: project selection, upload, list and detach. Detach does not delete the shared content-addressed blob.
- Research Vault, Characters & Worlds, Video & Audio, Compliance and Settings appear as staged modules; they are not implemented feature-complete screens.
- Windows setup/start scripts and frontend guide are present under `scripts/` and `docs/FRONTEND.md`. The setup script checks Python 3.11+/Node.js 20+, installs dependencies, builds the frontend, then applies migrations.

## Verification evidence

- Backend run [44507323858](https://github.com/Masoud4444/masoud-ai-studio/actions/runs/44507323858), commit `e4ce157a5830cbc16194d70194c548e21af15855`: **72 passed, 1 warning**; fresh SQLite Alembic upgrade through head succeeded through migration 0011.
- Frontend build run [44507106256](https://github.com/Masoud4444/masoud-ai-studio/actions/runs/44507106256), commit `588d05ce438e6d0eb97d8a404da5876262d63e7b`: successful.
- These are Linux CI checks. Windows install/runtime, real browser workflows, provider interoperability, concurrency/load behavior and desktop packaging have not been verified.
- CI mocks provider generation/model-list responses; no billable provider calls are made by CI.
- One Starlette/httpx deprecation warning remains.

## Important security and implementation boundaries

- No authentication/authorization exists. Bind the API to localhost or a trusted private environment; do not expose it publicly.
- Never commit provider keys, encryption keys, local database files, generated assets or private project data.
- No provider API keys are configured by default. The system does not make paid calls automatically.
- Worker is disabled by default; creative workflow handlers are not registered.
- Agent Runtime currently performs text-only model generation; it does not execute tool grants or access files. Tool Broker, tool execution, process sandbox, hard timeouts and operator recovery for abandoned reservations are not implemented. Runtime budget reservation and settlement are integrated for text-generation calls, but provider invoice reconciliation is not implemented.
- SQLite is single-worker only until multi-process locking is verified.
- Synchronous handlers cannot be forcibly interrupted; hard process-level timeout/isolation is not implemented.
- Windows DPAPI/OS keychain, streaming, automatic retries/fallback, circuit breakers, provider concurrency controls, invoice reconciliation and independent security review remain outstanding.

## Not implemented yet

- Windows desktop shell/packaging (Tauri), Android companion and hardened Web/PWA.
- Research Vault, multimodal intake, provenance/evidence graph.
- Story Engine, script/scene/dialogue/versioning, Character Bible, World Bible, continuity and universe/series management.
- Visual Style Engine, character model sheets, cinematography, shot planning, storyboard/animatic completion.
- Image/video/audio generation, subtitles, non-destructive editing, VFX/compositing.
- Human Value, Creative Identity, Originality, YouTube compliance and Creator Growth intelligence modules.
- Full review artifacts/comments, authenticated approvals, export/publishing, analytics, backups and restore verification.
- Full authentication, authorization, audit policy, rate limiting, process isolation and Windows credential protection.

## Next implementation sequence

1. Run the Windows setup script on the target PC; verify Python/Node versions, migrations, backend health and frontend browser interaction. Record any errors and fix them before expanding the UI.
2. Add backend/frontend integration tests for project, asset, production and agent screens; add a current frontend build run after any frontend source changes.
3. Harden local deployment: configuration validation, safe logs/telemetry, Windows DPAPI credential storage, backup/restore and startup/shutdown behavior.
4. Implement hard worker execution isolation and multi-worker-safe claims before registering creative handlers.
5. Complete Agent Runtime and Tool Broker only after runtime permission checks, approval enforcement, budget reservation/reconciliation and sandboxing are in place.
6. Build Research Vault and evidence/provenance workflows, then Story Engine, Character/World continuity, Visual/Cinematography, production media tools, QA/compliance, export and companion clients.

## Status vocabulary

- **Designed:** requirements and contracts are specified.
- **Implemented:** application code exists.
- **Tested:** tests were executed and results recorded.
- **Verified:** behavior was checked against acceptance criteria.
- **Released:** a versioned build or release artifact exists.

Never infer one status from another.


## Agent Runtime recovery checkpoint

- Repeated start of an already-running budget reservation now returns the existing reservation, allowing a caller to recover with the same idempotency key after interruption.
- Settlement replay is accepted only for an exact match of the previously recorded final status and actual cost. Conflicting updates are rejected and do not mutate the ledger.
- Added regression tests for repeated start, repeated settlement, conflicting settlement, and avoiding duplicate start audit events.
- This does not add lease expiry, hard process termination, or automatic reconciliation for abandoned reservations.
