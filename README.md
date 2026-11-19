# Masoud AI Studio

A private, local-first AI creative production studio for research, story development, visual design, image/video/audio production, editing, quality review, and publishing workflows.

## Product principles

- **Full Vision, Simplified Architecture, Incremental Implementation**
- Windows desktop is the primary platform; Android and Web/PWA are companion clients.
- Local-first and offline-first by default; cloud-ready without requiring a distributed architecture.
- Modular monolith: one backend, one primary database, one storage layer, one AI Gateway, one Agent Manager, and one Production Orchestrator.
- Human approval is required for consequential creative and publishing decisions.
- Preserve provenance, version history, continuity, privacy, recoverability, and cost visibility.
- The product is a private owner-operated studio, not a multi-tenant SaaS.

## Planned technology baseline

- Frontend: React, TypeScript, Tailwind CSS
- Backend: Python, FastAPI, SQLAlchemy 2, Pydantic, Alembic
- Initial database: SQLite
- Desktop shell: Tauri
- Companion clients: Android and Web/PWA

Technology choices remain subject to the architecture decisions and compatibility checks documented in this repository.

## Repository status

This repository was initially created empty. The first commit establishes project documentation and repository conventions only.

The previously produced **Foundation 002** archive is retained in the project's file library and is the intended implementation baseline. Its reported Linux test result was 8/8 tests passed; this result has not yet been independently re-run from this repository. The archive has not yet been imported into this repository, so no claim is made that its source code is present here.

**Next milestone:** safely inspect and import Foundation 002, then implement Package 003 — Projects & Storage Foundation — without overwriting or duplicating existing work.

See [Project Status](docs/PROJECT_STATUS.md) and [Architecture](docs/ARCHITECTURE.md).


## Project asset endpoints

- `POST /api/v1/projects/{project_id}/assets` (multipart field: `file`)
- `GET /api/v1/projects/{project_id}/assets`
- `DELETE /api/v1/projects/{project_id}/assets/{link_id}` (detaches the project link; it does not delete shared blob bytes)

Blobs are stored locally under `data/storage/blobs/<sha256-prefix>/<sha256>` by default. Configure with `MASOUD_STUDIO_STORAGE_ROOT`; configure the upload limit with `MASOUD_STUDIO_MAX_UPLOAD_BYTES`.
