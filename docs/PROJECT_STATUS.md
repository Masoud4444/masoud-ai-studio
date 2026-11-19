# Project Status

Last updated: 2026-11-19

## Repository and branch

- Repository: `Masoud4444/masoud-ai-studio` (public source repository; studio data is designed to remain local/private).
- Active implementation branch: `implementation/bootstrap-001`.
- The implementation branch is intentionally separate from `main`; no merge has been performed.
- The Foundation 002 archive has not been inspected or imported into this implementation branch. The backend work below is a fresh implementation and must not be described as an import.
- Latest verified backend checkpoint: `70e66918dff40bb02d22e1fc38e6c1807ac7e57e` — 72 tests passed and Alembic upgraded the fresh CI SQLite database through head (migration 0011). A later frontend-only commit is undergoing a separate UI build check.
- Active branch HEAD: `d1318f1917dc3513b3690bcf66754ccce0416d44`. `main` remains untouched.

## Implemented code

### Backend foundation

- FastAPI application and versioned API router.
- SQLAlchemy 2 models and SQLite default configuration.
- Project create, list, read, update, archive, and restore endpoints.
- Optimistic project version checks and duplicate-slug conflict handling.
- Alembic migrations 0001–0006 (0006 provider priority; latest migration and local-provider code are pending CI verification); application startup defaults to migration-managed schema mode. Development-only `create_all` bootstrap requires `MASOUD_STUDIO_SCHEMA_MODE=create`.

### Storage and asset management

- Asset and ProjectAsset relational models using SHA-256 content identity.
- Streamed upload ingestion in 1 MiB chunks, configurable 100 MiB default size limit, temporary staging, SHA-256 hashing, atomic blob placement, MIME signature sniffing, and filename sanitization.
- Project-scoped asset listing and detachment.
- Detachment deliberately retains blob bytes. Garbage collection is deferred until a recovery-safe reference audit exists.

### AI Gateway

- Provider registry API: create, list, disable, enable/disable update, and configurable priority (lower number is preferred).
- OpenAI-compatible non-streaming chat completion endpoint.
- AES-256-GCM encryption for provider credentials and stored idempotent responses; per-record key versioning and version-specific environment key support.
- Provider URL validation at registration and again before outbound requests.
- Explicit local OpenAI-compatible provider mode for localhost/127.0.0.1/::1 with a required port; non-loopback private/LAN destinations remain rejected.
- HTTPS-only, port 443, rejection of embedded credentials, query strings, fragments, localhost and non-public destinations.
- DNS resolution at request time and a pinned resolver for the actual HTTPS connection; TLS hostname verification remains enabled. Redirects and environment proxies are disabled.
- Structured, sanitized provider errors; provider response body is never copied into public error details.
- Request payload limit 1 MiB; provider response limit 4 MiB; provider timeout 90 seconds.
- Idempotency key hashing, request hash conflict detection, encrypted response replay, 180-second pending leases, and stale-lease recovery.
- AI model capability registry with declared vs. model-ID-verified states. Provider `/models` probe verifies only model identifiers, not feature behavior.
- Token usage ledger; manually configured input/output USD-per-million-token pricing; cost estimate snapshot on usage rows; immutable pricing history and pricing version provenance.
- Usage summary reports unpriced requests separately. Pricing is never guessed or silently fetched.
- Provider model registry backfill migration for existing provider configurations.
- Deterministic provider selection by model availability, enabled state, priority and creation time.

### Central Task Manager

- Durable task, dependency, and append-only task-event tables added in migration 0007.
- Idempotent task creation with request-hash conflict detection.
- Priority ordering, prerequisite gating, bounded attempt budgets, lease claims, completion/failure transitions, retry scheduling, manual retry, queued/blocked cancellation, and expired-lease recovery implemented as service primitives.
- API routes: `POST /tasks`, `GET /tasks`, `GET /tasks/{task_id}`, `POST /tasks/{task_id}/cancel`, and `POST /tasks/{task_id}/retry`.
- Worker claim/complete/fail functions remain internal only. A single-process Worker Supervisor, handler allowlist, lease recovery, result-size limit, sanitized failure persistence, and graceful shutdown are implemented. It is disabled by default and starts only with `MASOUD_STUDIO_WORKER_ENABLED=true`; only `system.healthcheck` is registered out of the box.
- SQLite operation is currently single-worker only. Multi-process locking, PostgreSQL concurrency, cancellation signalling for running work, quotas, and worker supervision remain future hardening tasks.
- Migrations 0007–0011 and Task Manager, Orchestrator, Worker, and Agent Manager tests are implemented; the verified backend checkpoint passed 72 tests.

See [Task Manager contract](TASK_MANAGER.md).

## Frontend workspace

- React + TypeScript + Vite frontend added under frontend/.
- Overview/Projects screen: project list, search, create project and backend connection feedback.
- Production room: workflow/run listing, preproduction run creation, run pause/resume/cancel controls and human approval gate visibility.
- AI Agents: create draft profiles, view registry, enable/disable only when provider/model prerequisites are satisfied.
- Assets: project selection, upload, list and detach; detach retains the content-addressed blob.
- Research Vault, Characters & Worlds, Video & Audio, Compliance and Settings are visible as staged modules, not falsely presented as implemented.
- Frontend build passed on commit 588d05ce438e6d0eb97d8a404da5876262d63e7b.
- Windows setup/start scripts added: scripts/setup-windows.bat, scripts/start-backend-windows.bat, scripts/start-frontend-windows.bat.
- Vite binds to loopback and proxies to FastAPI at 127.0.0.1:8000. External Google Fonts were removed to keep the UI offline-friendly.

See [Frontend guide](FRONTEND.md).

## Production Orchestrator

- Initial code-defined workflow registry added with `creative.preproduction` v1 (research intake → story development → character/world bible → visual development → storyboard → production handoff).
- Production runs and ordered steps are persisted in `production_runs` and `production_steps`; migration 0008 added.
- Run creation writes the run, all task records, dependency edges, task events, and step mappings in one transaction.
- Idempotency protects run creation and detects key/request conflicts.
- Human approval checkpoints are represented by tasks in `waiting_approval`; approval releases the task to the Task Manager queue, while rejection cancels it.
- API routes expose workflow registry, run creation/list/detail, and task approval/rejection.
- Creative workflow handlers are not implemented; the generic opt-in Worker Supervisor exists. Database-managed workflow templates and authenticated approvals are not implemented.
- Migration 0008 and orchestrator tests are included in the verified 72-test backend checkpoint.

See [Production Orchestrator contract](PRODUCTION_ORCHESTRATOR.md).

## AI Gateway API routes

All routes are under `/api/v1`:

- `POST /ai/providers`
- `GET /ai/providers`
- `DELETE /ai/providers/{provider_id}` (disables; does not physically delete history)
- `POST /ai/providers/{provider_id}/test`
- `GET /ai/models`
- `PATCH /ai/providers/{provider_id}/models/{model_id}`
- `PUT /ai/providers/{provider_id}/models/{model_id}/pricing`
- `GET /ai/providers/{provider_id}/models/{model_id}/pricing/history`
- `POST /ai/chat/completions`
- `GET /ai/usage/summary`

See [AI Gateway implementation guide](AI_GATEWAY.md) for setup, environment configuration, API examples, and security boundaries.

## Testing and verification

- GitHub Actions backend run `44506650266` passed for commit `70e66918dff40bb02d22e1fc38e6c1807ac7e57e`.
- Result: **72 passed, 1 warning** on Python 3.11 / Ubuntu runner.
- Alembic upgrade to head completed on a fresh SQLite database through migration 0011.
- Frontend build run `44507106256` passed for commit `588d05ce438e6d0eb97d8a404da5876262d63e7b`.
- The current branch includes later docs/setup scripts; backend code is unchanged from the verified backend checkpoint. A newer backend CI run may still be pending.
- Earlier failing CI runs exposed implementation defects; those were corrected and the successful run above is the verified result.
- This is Linux CI verification only. Windows behavior, real provider interoperability, DNS/TLS behavior against external providers, load/concurrency behavior, and recovery on actual desktop storage have not yet been verified.
- The CI tests mock provider generation and provider model-list responses; they do not make billable requests to a real AI provider.
- One Starlette/httpx deprecation warning remains; it does not fail the current suite.

## Required configuration and security boundaries

- Provider API keys are encrypted using a 32-byte URL-safe-base64 key supplied out-of-band through `MASOUD_STUDIO_CREDENTIAL_KEY` or versioned variables such as `MASOUD_STUDIO_CREDENTIAL_KEY_V1`. The active version is selected by `MASOUD_STUDIO_CREDENTIAL_KEY_VERSION`.
- Never commit encryption keys or provider secrets, place them in frontend code, or send them through chat.
- A future Windows desktop release should use Windows DPAPI / OS-protected credential storage rather than relying on manually managed environment variables.
- No user authentication or authorization layer has been implemented. Keep the API bound to localhost or a trusted private environment; do not expose it to the public internet or an untrusted LAN.
- Streaming, automatic retries/fallback, circuit breakers, provider concurrency limits, provider-invoice reconciliation and runtime integration of Agent budget controls are not implemented.
- Cost estimates depend on manually entered provider pricing and token counts. They are not invoices and may omit provider-specific billing dimensions.
- The outbound adapter uses pinned DNS answers and disables redirects/proxies, but the implementation still requires an independent security review before handling sensitive production data.

## Not implemented yet

- Windows desktop shell and packaging (Tauri).
- Web/PWA hardening and Android companion client.
- Tool sandbox and process isolation; execution permission enforcement; deeper Agent runtime lifecycle and budget reconciliation.
- Remaining Production Orchestrator capabilities: database-managed workflow templates, parallel branch fan-in/fan-out, DLQ UI, and recovery dashboard. Run-level pause/resume/cancel is implemented.
- Research Vault, multimodal intake, provenance and evidence graph.
- Story Engine, Character Bible, World Bible, continuity and universe/series management.
- Visual Style Engine, Character/Cinematography/Visual Continuity pipeline.
- Image, Video, Audio, Subtitle and non-destructive editing studios.
- Human Value, Creative Identity, Originality, YouTube Compliance and Creator Growth intelligence modules.
- Full approval workflow with review artifacts/comments, authenticated reviewer identity, export/publishing, analytics, backups and restore verification.
- Full security hardening, authentication, authorization, audit policy, rate limiting and Windows keychain integration.

## Next implementation sequence

1. Add integration tests for the outbound HTTP transport, DNS pinning, response sanitization, credential-key rotation, and concurrent idempotency.
2. Complete AI Gateway operational controls: provider priority/routing, safe failure policy, budget controls, concurrency limits, circuit breaker, and optional streaming.
3. Add Windows DPAPI-backed secret custody and Windows CI / packaging verification.
4. Verify migrations 0007–0011 and Task Manager/Orchestrator/Worker/Agent Manager tests; add hard execution timeouts/process isolation and multi-worker-safe claims before enabling creative handlers.
5. Add a versioned workflow registry, hard worker timeout/process isolation, and operator recovery tooling.
6. Implement task handlers and proceed with Research/Intake, Story, Character/Universe, Visual, Video, Audio, QA/Compliance, Export, Analytics, and companion clients.

## Status vocabulary

- **Designed:** requirements and contracts have been specified.
- **Implemented:** application code exists.
- **Tested:** tests were actually executed and results recorded.
- **Verified:** behavior was checked against acceptance criteria.
- **Released:** a versioned build or release artifact exists.

Never infer one status from another.


### Worker Supervisor foundation (new)
- Added a single-process sequential worker loop with a registered-handler allowlist; tasks without a registered handler are not claimed.
- Each claim, completion, failure, and lease-recovery operation uses a short-lived database session.
- Handler exceptions are persisted as generic sanitized errors; exception messages are never copied into task records.
- Results are JSON-serialized and bounded by a configurable in-process limit (default 4 MiB).
- Worker starts only when `MASOUD_STUDIO_WORKER_ENABLED=true`; default is disabled. Graceful shutdown waits for the current synchronous handler to finish.
- Only `system.healthcheck` is built in. Creative workflow task types intentionally remain queued until their actual modules register handlers.
- Known limits: synchronous handlers cannot be forcibly interrupted; per-handler hard timeouts, process isolation, multi-worker SQLite coordination, and operator telemetry remain future work.


## Frontend foundation (2026-11-19)\n\n- Added a React + TypeScript + Vite frontend under `frontend/`.\n- Implemented a responsive dark studio shell with workspace navigation, overview dashboard, API health feedback, project search, project listing, and project creation through the existing Projects API.\n- Vite development proxy targets the local FastAPI service at `127.0.0.1:8000`.\n- This is the first usable UI slice, not a completed studio interface. Research, production, assets, agents, compliance, media tools, and desktop packaging remain incremental work.\n- Frontend build has not yet been verified in CI.\n\n## Latest implementation checkpoint
- Production run reads are side-effect free; aggregate status is projected from task state without a database write.
- Task and production-run pagination use database-side counts.
- Added regression coverage for read-only run status and SQLite naive lease timestamps.
- Added an opt-in Worker Supervisor with a handler allowlist, lease recovery, safe result bounds, sanitized errors, and graceful shutdown. Only the non-billable `system.healthcheck` handler is registered by default.
- The worker remains disabled unless `MASOUD_STUDIO_WORKER_ENABLED=true`. Creative production task handlers are not yet registered.
- Verification status for this checkpoint: **CI pending**. Do not treat code presence as test success.


### Worker lease heartbeat update
- Added ownership-checked lease renewal; renewal is refused for expired leases, non-running tasks, or a different worker identity.
- The Worker Supervisor now renews leases periodically while synchronous handlers are executing and discards results if ownership can no longer be confirmed.
- Added a long-running handler regression test that expects at least one persisted lease-renewal event.
- Hard interruption/timeouts for synchronous handlers are still not provided; process isolation is required for that guarantee.


### Production run controls update
- Added migration 0009 to persist each task's pre-pause state.
- Added run-level pause/resume/cancel operations and API routes.
- Pause stops new claims by moving queued/approval-waiting tasks to a dedicated paused state and restores their exact state on resume.
- Active tasks are allowed to finish; the run reports `pausing` until no active tasks remain. Cancellation is rejected while any task is running.
- Added regression tests for pause/resume restoration, pending-task cancellation, and refusing to cancel active work.
- CI verification remains pending; migration and tests must pass before treating this feature as verified.


### Run-level controls checkpoint
- Run-level pause/resume/cancel endpoints are implemented and documented.
- Migration 0009 persists task pre-pause state so queued and approval-waiting tasks resume to the exact prior state.
- Active tasks are not killed: pause enters `pausing` until active work finishes; cancel is rejected while any task is running.
- Added regression tests for idle pause/resume, cancellation, cancellation rejection during active work, and pausing while a step is active.
- Added worker result validation rejecting non-finite JSON numbers and oversized outputs.
- Latest branch-head CI status: pending; no test pass is claimed.


### Agent Manager foundation update
- Added the Agent Manager registry with draft/enabled/disabled lifecycle and versioned configuration.
- Added provider/model validation at creation and activation; disabled or unregistered provider models cannot activate an agent.
- Added bounded per-run and monthly budget configuration, controlled agent permission vocabulary, explicit per-tool grants, and mandatory human approval for write/execute grants.
- Added append-only agent lifecycle/tool-grant audit events and migration 0010.
- Added an internal idempotent budget reservation ledger in migration 0011 with per-run/monthly ceilings, running/settled/released states, and conservative settlement checks.
- Added API endpoints and regression tests for lifecycle, provider/model checks, grants, duplicate slugs, and audit events.
- Important boundary: this is configuration governance only. No agent execution, tool broker, runtime authorization, or provider usage reconciliation is implemented. Budget reservation and ceiling checks exist as internal service operations but are not yet wired into execution. Do not enable billable or external tool execution until those controls exist.
- CI verification for this checkpoint is pending; no test pass is claimed.


### Agent budget ledger update
- Added migration 0011 and an internal idempotent reservation ledger.
- Reservations enforce per-run and current UTC calendar-month ceilings before execution, with idempotency hash/request hash conflict handling.
- Reservations transition through reserved, running, succeeded/failed, or released; settlement rejects actual cost above the reserved ceiling.
- Starting a reservation revalidates that the Agent and its configured Provider/Model remain enabled.
- Added regression tests for replay, idempotency conflicts, per-run/monthly ceilings, release, settlement limits, and disabling an Agent before start.
- Budget ledger is not yet wired to an Agent Runtime or AI Gateway usage reconciliation. Runtime must reserve a conservative upper bound before any provider request.
