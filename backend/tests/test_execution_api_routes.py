import pytest
from fastapi import HTTPException

from backend.app import api


def test_post_tasks_route_is_bound_to_task_creation_handler():
    matches = [
        route for route in api.router.routes
        if getattr(route, "path", None) == "/api/v1/tasks"
        and "POST" in getattr(route, "methods", set())
    ]
    assert len(matches) == 1
    assert matches[0].endpoint is api.post_task


def test_task_result_is_not_downloadable_before_success(monkeypatch):
    monkeypatch.setattr(api, "get_task", lambda db, task_id: {"id": task_id, "status": "running", "result": None})
    with pytest.raises(HTTPException) as error:
        api.get_task_result("task-123", object())
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "task_result_not_ready"


def test_succeeded_task_result_is_returned_as_no_store_attachment(monkeypatch):
    result = {"artifact_id": "asset-123", "format": "json"}
    monkeypatch.setattr(api, "get_task", lambda db, task_id: {"id": task_id, "status": "succeeded", "result": result})
    response = api.get_task_result("task-123", object())
    assert response.status_code == 200
    assert response.headers["content-disposition"] == 'attachment; filename="masoud-studio-task-task-123-result.json"'
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.body == b'{"artifact_id":"asset-123","format":"json"}'
