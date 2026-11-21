import pytest
from fastapi import HTTPException

from backend.app import api
from backend.app.storage import resolve_task_artifact_file


def test_task_artifact_upload_requires_completed_task(monkeypatch):
    class Task:
        status = "running"
        project_id = "project-123"
    monkeypatch.setattr(api, "get_db", lambda: None)
    class DB:
        def get(self, model, key):
            return Task()
    with pytest.raises(HTTPException) as error:
        import asyncio
        asyncio.run(api.post_task_artifact("task-123", object(), DB()))
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "task_artifacts_require_succeeded_task"


def test_task_artifact_download_is_scoped_to_task_and_preview_allowlist(monkeypatch):
    from pathlib import Path
    class Asset:
        id = "asset-1"
        sha256 = "a" * 64
        size_bytes = 4
        mime_type = "image/png"
    class Link:
        id = "link-1"
        original_filename = "frame.png"
    path = Path("fake-frame.png")
    monkeypatch.setattr(api, "resolve_task_artifact_file", lambda db, task_id, artifact_id: (Asset(), Link(), path))
    response = api.get_task_artifact("task-1", "link-1", True, object())
    assert response.media_type == "image/png"
    assert response.headers["content-disposition"].startswith("inline;")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"


def test_task_artifact_preview_falls_back_to_attachment_for_unsafe_mime(monkeypatch):
    from pathlib import Path
    class Asset:
        id = "asset-1"
        sha256 = "b" * 64
        size_bytes = 4
        mime_type = "image/svg+xml"
    class Link:
        id = "link-1"
        original_filename = "vector.svg"
    monkeypatch.setattr(api, "resolve_task_artifact_file", lambda db, task_id, artifact_id: (Asset(), Link(), Path("vector.svg")))
    response = api.get_task_artifact("task-1", "link-1", True, object())
    assert response.headers["content-disposition"].startswith("attachment;")


def test_task_artifact_lookup_rejects_missing_or_unassociated_artifact(monkeypatch):
    from backend.app.storage import resolve_task_artifact_file
    from backend.app.models import StudioTask
    class DB:
        def get(self, model, key):
            return object()
        def execute(self, query):
            class Result:
                def first(self):
                    return None
            return Result()
    with pytest.raises(HTTPException) as error:
        resolve_task_artifact_file(DB(), "task-1", "foreign-link")
    assert error.value.status_code == 404
    assert error.value.detail["code"] == "task_artifact_not_found"
