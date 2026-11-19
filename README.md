# Masoud AI Studio

A public-code, private-by-design, local-first AI creative production studio for research, story development, visual design, image/video/audio production, editing, quality review, and publishing workflows.

## Product principles

- **Full Vision, Simplified Architecture, Incremental Implementation**
- Windows desktop is the primary platform; Android and Web/PWA are companion clients.
- Local-first and offline-first by default; cloud-ready without requiring a distributed architecture.
- Modular monolith: one backend, one primary database, one storage layer, one AI Gateway, one Agent Manager, and one Production Orchestrator.
- Human approval is required for consequential creative and publishing decisions.
- Preserve provenance, version history, continuity, privacy, recoverability, and cost visibility.
- The product is a private owner-operated studio, not a multi-tenant SaaS.

## Technology baseline

- Frontend: React, TypeScript, Vite (initial dashboard and project creation implemented)
- Backend: Python, FastAPI, SQLAlchemy 2, Pydantic, Alembic
- Initial database: SQLite
- Desktop shell: Tauri (not implemented yet)
- Companion clients: Android and Web/PWA (not implemented yet)

## Repository and branch

- Public repository: `Masoud4444/masoud-ai-studio` (source code is public; the intended studio workspace and user data remain local/private).
- Current implementation branch: `implementation/bootstrap-001`.
- This branch is intentionally separate from `main`; no merge has been performed.
- The implementation below is a fresh code path. Foundation 002 has not been imported or inspected in this branch.

## Implemented backend slices

- Project lifecycle API with optimistic version checks.
- Content-addressed storage and project asset linking.
- AI Provider registry with encrypted credentials and SSRF-aware URL validation.
- OpenAI-compatible non-streaming chat completion gateway with pinned DNS resolution, response encryption and idempotency.
- Model capability declarations and provider model-ID verification.
- Token usage ledger, manually configured model pricing, estimated cost tracking, and immutable pricing history.
- Alembic schema migration baseline and follow-up migrations.

See [Project Status](docs/PROJECT_STATUS.md), [Architecture](docs/ARCHITECTURE.md), and [AI Gateway Guide](docs/AI_GATEWAY.md).

## Development setup

```bash
python -m pip install -r requirements.txt
mkdir -p data
alembic upgrade head
uvicorn backend.app.main:app --reload
```

Set `MASOUD_STUDIO_DATABASE_URL` if using a different database. Managed application startup expects migrations to have been applied. `MASOUD_STUDIO_SCHEMA_MODE=create` enables development-only metadata bootstrap.

## Frontend development\n\n```bash\ncd frontend\nnpm install\nnpm run dev\n```\n\nThe Vite development server proxies `/api` and `/health` to the local FastAPI service at `127.0.0.1:8000`. Build with `npm run build`. The current UI slice supports project listing, search, and project creation; other studio areas are staged for incremental implementation.\n\n## Project asset endpoints

- `POST /api/v1/projects/{project_id}/assets` (multipart field: `file`)
- `GET /api/v1/projects/{project_id}/assets`
- `DELETE /api/v1/projects/{project_id}/assets/{link_id}` (detaches the project link; it does not delete shared blob bytes)

Blobs are stored locally under `data/storage/blobs/<sha256-prefix>/<sha256>` by default. Configure with `MASOUD_STUDIO_STORAGE_ROOT`; configure the upload limit with `MASOUD_STUDIO_MAX_UPLOAD_BYTES`.

## Important security boundary

The backend does not yet implement user authentication/authorization. Keep it bound to localhost or a trusted private environment. Do not expose it to the public internet. Windows deployment and recovery behavior still require verification.
