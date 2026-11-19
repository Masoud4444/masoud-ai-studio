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

- FastAPI application, SQLAlchemy 2 models, SQLite baseline and Alembic migrations 0001–0014.
- Project create/list/read/update/archive/restore API, optimistic version checks and duplicate-slug handling.
- Content-addressed asset storage using SHA-256, streamed uploads, size limits, temporary staging, atomic placement, MIME sniffing, filename sanitization, project listing and detach.
- AI Gateway provider registry, priority selection, OpenAI-compatible non-streaming completion, encrypted credentials and idempotent response storage (AES-256-GCM), SSRF-aware URL checks, DNS pinning, TLS verification, disabled redirects/proxies, sanitized errors, usage ledger and manually configured pricing history.
- Central Task Manager: idempotent task creation, dependency gates, priority, bounded attempts, leases, retries, cancellation, expired lease recovery and append-only events.
- Worker Supervisor: handler allowlist, lease heartbeat, bounded JSON results, sanitized handler errors and graceful shutdown. Disabled by default; only `system.healthcheck` is registered out of the box.
- Production Orchestrator: code-defined `creative.preproduction` v1 workflow, persisted runs/steps, idempotent creation, approval gates, pause/resume/cancel.
- Agent Manager: draft/enabled/disabled lifecycle, versioned config, provider/model checks, permissions/tool grants, approval requirements for write/execute grants, audit events and internal budget reservation ledger. A first text-only Agent Runtime is implemented at `POST /api/v1/agents/{agent_id}/run`, with explicit `ai.generate` permission, required model pricing, conservative pre-call budget reservation and Gateway idempotency.
- Story Engine v0.1: project-linked story dossiers (format, genre, audience, premise, logline, synopsis, creative intent and lifecycle status), ordered scene outline records (slugline, summary, dramatic purpose, setting, beats and script body), optimistic version checks and immutable full-story snapshots after every mutation. Revision history is read-only.\n- Research Vault v0.2: source records, reusable project-source links, asset references, metadata-only URL records, bounded local PDF/DOCX extraction in a timed subprocess, exact evidence excerpts with page/paragraph locators, SHA-256 evidence deduplication, project claims, supporting/contradicting/contextualizing relationships, review gates, append-only provenance events and project-scoped full-text search across source metadata, evidence and claims. No migration required for search.

## Implemented frontend

- React + TypeScript + Vite responsive studio shell.
- Overview and Projects: listing, search, project creation and backend health feedback.
- Production room: create/list preproduction runs, inspect step state and approval gates, pause/resume/cancel controls.
- AI agents: create draft profiles, view registry, enable/disable where provider/model requirements permit.
- Assets: project selection, upload, list and detach. Detach does not delete the shared content-addressed blob.
- Research Vault workspace: register sources, browse project-linked sources, capture exact evidence excerpts/locators, create project claims, link evidence as support/contradiction/context, accept/reject claims only when the required evidence relation exists, and search source metadata, excerpts, locators and claims with optional project scope. Existing project assets can be attached to source records, and the API verifies the asset is linked to the selected project. HTTP-level integration tests cover source creation, evidence capture, claim acceptance and safe refusal to detach referenced sources.
- Story Engine workspace: create project stories, add/remove ordered scenes, change lifecycle status and inspect immutable revision history.\n- Characters & Worlds, Video & Audio, Compliance and Settings remain staged modules.
- Windows setup/start scripts and frontend guide are present under `scripts/` and `docs/FRONTEND.md`. The setup script checks Python 3.11+/Node.js 20+, installs dependencies, builds the frontend, then applies migrations.

## Verification evidence

- Latest backend run [44515790910](https://github.com/Masoud4444/masoud-ai-studio/actions/runs/44515790910), commit `48166b4d72792e4e261e44f5eadde42eb7bc3538`: **88 passed, 1 warning**; fresh SQLite Alembic upgrade through head succeeded through migration 0012, including Research Vault search tests.
- Latest frontend build [44515790960](https://github.com/Masoud4444/masoud-ai-studio/actions/runs/44515790960), commit `48166b4d72792e4e261e44f5eadde42eb7bc3538`: successful.
- These are Linux CI checks. Windows install/runtime, real browser workflows, provider interoperability, concurrency/load behavior and desktop packaging have not been verified.
- CI mocks provider generation/model-list responses; no billable provider calls are made by CI.
- One Starlette/httpx deprecation warning remains.

## Important security and implementation boundaries

- No authentication/authorization exists. Bind the API to localhost or a trusted private environment; do not expose it publicly.
- Never commit provider keys, encryption keys, local database files, generated assets or private project data.
- No provider API keys are configured by default. The system does not make paid calls automatically.
- Worker is disabled by default; creative workflow handlers are not registered.
- Research Vault URLs are metadata only; no remote URL fetching, crawling or browser automation is performed. Uploaded document parsing/OCR/transcription and AI-assisted extraction are not implemented.
- Agent Runtime currently performs text-only model generation; it does not execute tool grants or access files. Tool Broker, tool execution, process sandbox, hard timeouts and operator recovery for abandoned reservations are not implemented. Runtime budget reservation and settlement are integrated for text-generation calls, but provider invoice reconciliation is not implemented.
- SQLite is single-worker only until multi-process locking is verified.
- Synchronous handlers cannot be forcibly interrupted; hard process-level timeout/isolation is not implemented.
- Windows DPAPI/OS keychain, streaming, automatic retries/fallback, circuit breakers, provider concurrency controls, invoice reconciliation and independent security review remain outstanding.

## Not implemented yet

- Windows desktop shell/packaging (Tauri), Android companion and hardened Web/PWA.
- Multimodal Research Vault intake, safe document parsing, OCR/transcription, source credibility scoring, semantic search and AI-assisted evidence extraction. The manual source/evidence/claim foundation is implemented.
- Story Engine expansion: full script editor, dialogue, beat/act structures, scene reorder and richer scene editing, character/world links, Character Bible, World Bible, continuity and universe/series/season/episode management. The dossier, ordered scene outline and immutable revision foundation are implemented.
- Visual Style Engine, character model sheets, cinematography, shot planning, storyboard/animatic completion.
- Image/video/audio generation, subtitles, non-destructive editing, VFX/compositing.
- Human Value, Creative Identity, Originality, YouTube compliance and Creator Growth intelligence modules.
- Full review artifacts/comments, authenticated approvals, export/publishing, analytics, backups and restore verification.
- Full authentication, authorization, audit policy, rate limiting, process isolation and Windows credential protection.

## Next implementation sequence

1. Run the Windows setup script on the target PC; verify Python/Node versions, migrations through 0012, backend health and browser workflows. Record and fix any local runtime issues.
2. Expand Research Vault extraction with OCR/transcription behind explicit local processing controls, stronger OS-level parser sandboxing and richer provenance. Do not add background URL fetching until an SSRF-safe fetch subsystem exists.
3. Add end-to-end integration tests for project, asset, Research Vault, production and Agent screens.
4. Harden local deployment: configuration validation, safe telemetry, Windows DPAPI credential storage, backup/restore and startup/shutdown behavior.
5. Implement hard worker execution isolation and multi-worker-safe claims before registering creative handlers; then extend Agent Runtime/Tool Broker with explicit permission checks, approval enforcement, budget reconciliation and sandboxing.
6. Expand Story Engine into script/beat/dialogue editing and series hierarchy; then implement Character/World continuity, Visual/Cinematography, production media tools, QA/compliance, export and companion clients.

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

- Duplicate Runtime callers that encounter an active Gateway idempotency lease now leave the reservation running for safe retry instead of prematurely settling it as failed; a regression test covers this case.


## Research Vault search v0.2

- Added read-only `GET /api/v1/research/search` for source metadata, exact evidence excerpts/locators, and project claim statements/rationale.
- Supports optional project scope, case-insensitive matching, escaped SQL LIKE wildcards, bounded query length and independent bounded result sets/counts.
- Added regression tests for cross-entity matches, project isolation, wildcard escaping and query validation.
- Added a Research Vault search interface with grouped result cards; search does not modify provenance or trigger network/AI activity.


## Research Vault local document extraction v0.3

- Added explicit `POST /api/v1/research/sources/{source_id}/extract` for attached PDF and DOCX assets.
- Parser executes in a short-lived subprocess with a 30-second timeout; file size, PDF page count, DOCX archive expansion, chunk count and total extracted text are bounded.
- Extracted text is preserved as evidence excerpts with PDF page or DOCX paragraph-range locators and extraction metadata; evidence hash deduplication makes repeat extraction safe.
- UI exposes an Extract text action only for document sources with an attached asset.
- No OCR, scanned-PDF recognition, embedded media extraction, AI extraction or remote URL fetching.
- Parser timeout is not a full OS sandbox; memory/CPU quotas and hardened process isolation remain required before processing untrusted files at scale.


## Story Engine foundation v0.1

- Added migration 0013 with project-linked story dossiers, ordered scenes and immutable version snapshots.
- Story creation stores the initial full dossier/scene snapshot. Metadata changes and scene create/update/delete each increment the story version and append a full snapshot; revision history is read-only through the API.
- Story and scene updates require expected versions and return HTTP 409 on stale edits. Scene updates also have their own optimistic version counter.
- Added endpoints: POST/GET /api/v1/stories, GET/PATCH /api/v1/stories/{id}, POST /api/v1/stories/{id}/scenes, PATCH/DELETE /api/v1/stories/{id}/scenes/{scene_id}.
- Added a Story Engine workspace for project-scoped story creation, ordered scene outline management, lifecycle status and revision history.
- Scene script editor, scene reordering, sluglines, dramatic purpose, setting and beat lists are now implemented. Character/world links, dedicated dialogue/character cue structures, beat templates, branching drafts, AI writing and series/season/episode hierarchy remain future increments.
- No previously passed test suite was rerun during this implementation. CI may run automatically after the commit; no result is claimed here.


## Story Engine scene editing v0.2

- Added full scene editing for slugline, location, time of day, summary, dramatic purpose, ordered beat list and screenplay body.
- Added scene reordering endpoint with strict permutation validation: the request must include every scene exactly once, and it uses story-level optimistic version checks.
- Scene edits and reorder operations create a new immutable full-story revision. Each edited scene also increments its own version.
- Workspace exposes edit, save, discard, move up/down and remove actions.
- No prior successful test suites were rerun. New commits may trigger normal automatic CI; results are only reported when observed.


## Character Bible and World Bible v0.1
- Story-scoped character profiles include role, age, structured appearance/psychology, backstory, goals, conflict, character arc and voice notes.
- Character relationship records validate both endpoints against the same story and reject self-links and duplicates.
- World locations contain structured geography and culture fields; categorized world rules are stored separately.
- Scenes can reference characters with presence type and world locations. Cross-story links are rejected.
- Character and location edits use optimistic version checks. Every Bible mutation stores an append-only full snapshot; history metadata is read-only.
- API routes: GET /api/v1/stories/{story_id}/bible; POST/PATCH character and location routes; relationship/rule creation; scene character/location links.
- Automated continuity inference, prop tracking, model sheets and a dedicated visual editor remain future increments. Prior passing test suites were not rerun.


## Character & World Bible UI v0.2
- Connected the Characters & Worlds workspace to the Story Engine and Character/World Bible APIs.
- Added character and location creation, optimistic-version edits, world-rule creation, directed character relationships and scene-level character/location linking.
- Added read views for canonical profiles, relationships, scene connections and immutable Bible revision history.
- The UI is a structured editor; appearance, psychology, geography and culture remain JSON-backed structured fields pending dedicated visual model-sheet editors.
- Continuity detection and prop/object state tracking remain the next implementation increment.
- No previously passing test suite was rerun for this UI increment.


## Continuity Engine backend v0.1
- Added scene-scoped continuity facts for characters, locations and props, including attribute/value, evidence note, transition explanation, optimistic version and soft deactivation.
- Deterministic analysis detects conflicting values for the same subject/attribute within one scene, unexplained state changes between ordered scenes, and character/location facts whose entities are not linked to that scene.
- Issues have stable fingerprints, severity, occurrence counts, first/last seen timestamps and human review states (accepted, dismissed, resolved).
- Analysis never edits story text or silently changes canonical facts. Transition notes explicitly distinguish intentional changes from possible continuity gaps.
- API: GET/POST/PATCH /api/v1/stories/{story_id}/continuity/facts; POST /analyze; GET /issues; PATCH /issues/{issue_id}.
- Scope limitation: scene position is used as narrative order, not an inferred in-world timestamp. Automatic screenplay NLP, object/prop identity resolution, cross-episode timeline reasoning and visual frame comparison are future increments.
- Previously passed test suites were not rerun. No manual test result is claimed for this increment.


## Continuity Ledger UI v0.2
- Added UI for recording character, location and prop state assertions against individual scenes.
- Added transition explanations and evidence/production notes; fact records can be versioned and soft-deactivated through the API.
- Added one-click deterministic analysis and a review queue to confirm, dismiss as false positive, or mark findings resolved.
- The interface distinguishes high/medium/low severity and displays the source scenes and fact history.


## Local Windows launch increment — 2026-11-19

- Added a production-style local serving path: when frontend/dist/index.html exists, FastAPI serves the compiled React application from the same process after registering API and health routes.
- Added scripts/start-studio-windows.bat. It checks the local virtual environment and frontend build, applies pending Alembic migrations, refuses to start when port 8000 is already occupied, starts Uvicorn bound to 127.0.0.1, waits for the expected health response and opens the browser.
- Updated the Windows guide and README to describe the one-command local browser launch workflow and distinguish it from development mode.
- This increment has been committed to implementation/bootstrap-001 as 459ffff41b09e905c2fa5f7fafe613a5b638957f.
- Verification for this increment: repository files and branch head were inspected after commit. No tests or builds were rerun. The launcher has not yet been executed on a Windows machine.
- This is not yet a native desktop installer. Tauri packaging, a bundled Python runtime/backend, Windows code signing, DPAPI-backed credential protection, update delivery, backup/restore and hands-on Windows acceptance remain outstanding.


## Timeline & Event Continuity v0.1 — 2026-11-19

- Added story-scoped in-world timeline events that can optionally reference a screenplay scene.
- Added explicit directed before/after ordering constraints, duplicate-edge idempotency, same-story ownership validation and cycle rejection.
- Added deterministic topological analysis. Events without a declared path remain unordered; screenplay scene position is never treated as in-world chronology.
- API routes: GET/POST /api/v1/stories/{sid}/timeline/events, PATCH /events/{event_id}, GET/POST /relations and POST /analyze.
- Migration 0016_timeline_events follows 0015_continuity_engine.
- Backend API implementation is committed but not yet covered by a verified CI result or a Windows runtime check. Timeline UI and dedicated prop registry remain outstanding.
