# Masoud AI Studio

Private, local-first creative production studio. The complete approved product vision is retained; implementation is delivered incrementally as a modular monolith.

## Executable foundation 0.1

- FastAPI backend and health endpoint
- SQLite by default; configure with `MASOUD_STUDIO_DATABASE_URL`
- Project create/list/read/update/archive/restore API
- Optimistic version checks and duplicate-slug conflict handling
- Backend tests and GitHub Actions workflow

This is the first executable foundation, not the complete product. Storage ingestion, assets, AI Gateway, agents, orchestration, creative workspaces, desktop packaging, and companion clients remain to be implemented.

## Run

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```

API docs: http://127.0.0.1:8000/docs

## Test

```bash
pytest
```

## API routes

- POST /api/v1/projects
- GET /api/v1/projects
- GET /api/v1/projects/{project_id}
- PATCH /api/v1/projects/{project_id} (requires expected_version)
- POST /api/v1/projects/{project_id}/archive
- POST /api/v1/projects/{project_id}/restore
