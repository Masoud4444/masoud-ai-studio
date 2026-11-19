# Project Status

Last updated: 2026-11-19

## Repository and branch

- Repository: `Masoud4444/masoud-ai-studio` (private).
- Active implementation branch: `implementation/bootstrap-001`.
- The implementation branch is intentionally separate from `main`; no merge has been performed.
- The Foundation 002 archive has not been inspected or imported into this implementation branch. The backend work below is a fresh implementation and must not be described as an import.

## Implemented code

### Backend foundation
- FastAPI application and versioned API router.
- SQLAlchemy 2 models and SQLite default configuration.
- Project create, list, read, update, archive, and restore endpoints.
- Optimistic project version checks and duplicate-slug conflict handling.

### Storage and asset management
- Asset and ProjectAsset relational models using SHA-256 content identity.
- Streamed upload ingestion in 1 MiB chunks, configurable 100 MiB default size limit, temporary staging, SHA-256 hashing, atomic blob placement, MIME signature sniffing, and filename sanitization.
- Project-scoped asset listing and detachment.
- Detachment deliberately retains blob bytes. Garbage collection is deferred until a recovery-safe reference audit exists.

### AI Gateway — first implementation slice
- Provider registry model and API routes to create, list, and delete OpenAI-compatible provider configurations.
- Provider URL validation requires HTTPS, rejects embedded credentials, query strings, fragments, localhost/private/link-local/reserved destinations, and resolves DNS names to reject any non-global address.
- API credentials are encrypted with AES-256-GCM before database persistence. The encryption key is supplied out-of-band through environment configuration; plaintext credentials are never returned by provider API responses.
- Credential key version is stored with each provider record; version-specific environment keys are supported for future controlled rotation.
- Provider models are stored as declared model identifiers. Capability verification, model routing, generation adapter, outbound request enforcement, retries/fallback, idempotency, cost accounting, and structured provider health checks are not implemented yet.
- Important security boundary: URL validation currently occurs at provider registration. The outbound adapter must repeat DNS/IP validation immediately before each connection and defend against DNS rebinding before any provider request feature is enabled.

## Testing and verification

- Pytest coverage exists for project and storage behavior, and new tests cover AI Gateway credential encryption and provider URL rejection.
- GitHub Actions run `44444397076` for commit `2410ee783f2a844a55112c9591efcac92fe5aff8` completed successfully on 2026-11-19.
- Result: **14 passed, 1 warning** (Python 3.11, Ubuntu GitHub Actions runner).
- Earlier CI attempts exposed dependency-line and escaped-newline errors; these were corrected before the successful run.
- This is Linux CI verification only. Windows behavior remains unverified.
- Schema creation still uses SQLAlchemy `create_all` during app startup. Alembic migrations are required before production use.
- Windows-specific behavior has not been verified.

## Required configuration

Before creating a provider with an API key, set a 32-byte URL-safe-base64 key in `MASOUD_STUDIO_CREDENTIAL_KEY` (or a versioned variable such as `MASOUD_STUDIO_CREDENTIAL_KEY_V1`). Do not commit this key, place it in frontend code, or send it through chat. Use a dedicated secret store or OS-protected secret mechanism for deployment. If the key is missing or invalid, credential encryption fails closed.

## Not implemented yet

- Alembic migrations and schema upgrade/recovery workflow.
- AI model capability registry and provider connection test.
- Outbound model adapter with per-request SSRF/DNS-rebinding defense.
- Model routing, timeout/retry/fallback, request idempotency, cost/usage ledger, and sanitized provider error mapping.
- Agent Manager, Production Orchestrator, central Task Manager, frontend, Windows desktop packaging, Android, and Web/PWA clients.

## Next implementation sequence

1. Add Alembic migrations and replace startup-only `create_all` for managed schemas.
2. Complete AI Gateway outbound adapter, DNS/IP pinning protections, capability registry, request hashing/idempotency, retries/fallback, sanitized errors, and cost tracking.
3. Add mocked integration tests and execute the full backend suite in CI.
4. Continue with Research/Intake, Studio OS, Story, Character/Universe, Visual, Video, Audio, QA/Compliance, Export, Analytics, and companion clients.

## Status vocabulary

- **Designed:** requirements and contracts have been specified.
- **Implemented:** application code exists.
- **Tested:** tests were actually executed and results recorded.
- **Verified:** behavior was checked against acceptance criteria.
- **Released:** a versioned build or release artifact exists.

Never infer one status from another.
