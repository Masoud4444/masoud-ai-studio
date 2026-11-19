# Project Status

Last updated: 2026-11-19

## Repository and branch

- Repository: `Masoud4444/masoud-ai-studio` (private).
- Active implementation branch: `implementation/bootstrap-001`.
- The implementation branch is intentionally separate from `main`; no merge has been performed.
- The Foundation 002 archive has not been inspected or imported into this implementation branch. The backend work below is a fresh implementation and must not be described as an import.
- Last fully verified implementation commit: `cf24526ff43c85ba6bcde6fcc8a9757dc20b485d`.
- Later documentation-only commits update the README and AI Gateway guide; their CI is tracked separately.

## Implemented code

### Backend foundation

- FastAPI application and versioned API router.
- SQLAlchemy 2 models and SQLite default configuration.
- Project create, list, read, update, archive, and restore endpoints.
- Optimistic project version checks and duplicate-slug conflict handling.
- Alembic migrations 0001–0005; application startup defaults to migration-managed schema mode. Development-only `create_all` bootstrap requires `MASOUD_STUDIO_SCHEMA_MODE=create`.

### Storage and asset management

- Asset and ProjectAsset relational models using SHA-256 content identity.
- Streamed upload ingestion in 1 MiB chunks, configurable 100 MiB default size limit, temporary staging, SHA-256 hashing, atomic blob placement, MIME signature sniffing, and filename sanitization.
- Project-scoped asset listing and detachment.
- Detachment deliberately retains blob bytes. Garbage collection is deferred until a recovery-safe reference audit exists.

### AI Gateway

- Provider registry API: create, list, disable.
- OpenAI-compatible non-streaming chat completion endpoint.
- AES-256-GCM encryption for provider credentials and stored idempotent responses; per-record key versioning and version-specific environment key support.
- Provider URL validation at registration and again before outbound requests.
- HTTPS-only, port 443, rejection of embedded credentials, query strings, fragments, localhost and non-public destinations.
- DNS resolution at request time and a pinned resolver for the actual HTTPS connection; TLS hostname verification remains enabled. Redirects and environment proxies are disabled.
- Structured, sanitized provider errors; provider response body is never copied into public error details.
- Request payload limit 1 MiB; provider response limit 4 MiB; provider timeout 90 seconds.
- Idempotency key hashing, request hash conflict detection, encrypted response replay, 180-second pending leases, and stale-lease recovery.
- AI model capability registry with declared vs. model-ID-verified states. Provider `/models` probe verifies only model identifiers, not feature behavior.
- Token usage ledger; manually configured input/output USD-per-million-token pricing; cost estimate snapshot on usage rows; immutable pricing history and pricing version provenance.
- Usage summary reports unpriced requests separately. Pricing is never guessed or silently fetched.
- Provider model registry backfill migration for existing provider configurations.

### AI Gateway API routes

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

- GitHub Actions workflow run `44445452582` completed successfully for commit `cf24526ff43c85ba6bcde6fcc8a9757dc20b485d`.
- Result: **21 passed, 1 warning** on Python 3.11 / Ubuntu runner.
- The same CI run successfully executed Alembic upgrades through revisions 0001–0005 on a fresh SQLite database.
- Earlier failing CI runs exposed implementation defects; those were corrected and the successful run above is the verified result.
- This is Linux CI verification only. Windows behavior, real provider interoperability, DNS/TLS behavior against external providers, load/concurrency behavior, and recovery on actual desktop storage have not yet been verified.
- The CI tests mock provider generation and provider model-list responses; they do not make billable requests to a real AI provider.
- One Starlette/httpx deprecation warning remains; it does not fail the current suite.

## Required configuration and security boundaries

- Provider API keys are encrypted using a 32-byte URL-safe-base64 key supplied out-of-band through `MASOUD_STUDIO_CREDENTIAL_KEY` or versioned variables such as `MASOUD_STUDIO_CREDENTIAL_KEY_V1`. The active version is selected by `MASOUD_STUDIO_CREDENTIAL_KEY_VERSION`.
- Never commit encryption keys or provider secrets, place them in frontend code, or send them through chat.
- A future Windows desktop release should use Windows DPAPI / OS-protected credential storage rather than relying on manually managed environment variables.
- No user authentication or authorization layer has been implemented. Keep the API bound to localhost or a trusted private environment; do not expose it to the public internet or an untrusted LAN.
- Streaming, automatic retries/fallback, circuit breakers, provider concurrency limits, monthly budget enforcement, and provider-invoice reconciliation are not implemented.
- Cost estimates depend on manually entered provider pricing and token counts. They are not invoices and may omit provider-specific billing dimensions.
- The outbound adapter uses pinned DNS answers and disables redirects/proxies, but the implementation still requires an independent security review before handling sensitive production data.

## Not implemented yet

- Windows desktop UI and packaging (Tauri).
- React/TypeScript frontend and Web/PWA.
- Android companion client.
- Agent Manager, agent permissions, tool sandbox and agent execution lifecycle.
- Production Orchestrator and central Task Manager / queue / DLQ / recovery.
- Research Vault, multimodal intake, provenance and evidence graph.
- Story Engine, Character Bible, World Bible, continuity and universe/series management.
- Visual Style Engine, Character/Cinematography/Visual Continuity pipeline.
- Image, Video, Audio, Subtitle and non-destructive editing studios.
- Human Value, Creative Identity, Originality, YouTube Compliance and Creator Growth intelligence modules.
- Approval workflow, export/publishing, analytics, backups and restore verification.
- Full security hardening, authentication, authorization, audit policy, rate limiting and Windows keychain integration.

## Next implementation sequence

1. Add integration tests for the outbound HTTP transport, DNS pinning, response sanitization, credential-key rotation, and concurrent idempotency.
2. Complete AI Gateway operational controls: provider priority/routing, safe failure policy, budget controls, concurrency limits, circuit breaker, and optional streaming.
3. Add Windows DPAPI-backed secret custody and Windows CI / packaging verification.
4. Implement the central Task Manager and Production Orchestrator foundations before agent and studio workflows.
5. Continue with Research/Intake, Studio OS, Story, Character/Universe, Visual, Video, Audio, QA/Compliance, Export, Analytics, and companion clients.

## Status vocabulary

- **Designed:** requirements and contracts have been specified.
- **Implemented:** application code exists.
- **Tested:** tests were actually executed and results recorded.
- **Verified:** behavior was checked against acceptance criteria.
- **Released:** a versioned build or release artifact exists.

Never infer one status from another.
