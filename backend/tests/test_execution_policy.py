import pytest
from fastapi import HTTPException

from backend.app.execution_policy import DEFAULT_EXECUTION_PREFERENCES, resolve_execution


def test_auto_keeps_light_work_local():
    result = resolve_execution("story.outline", {"text": "short"}, None,
                               DEFAULT_EXECUTION_PREFERENCES, False)
    assert result["execution_mode"] == "local"
    assert result["cloud_recommended"] is False


def test_auto_offloads_heavy_work_when_cloud_is_configured():
    result = resolve_execution("animation.render", {"estimated_duration_seconds": 90}, "auto",
                               DEFAULT_EXECUTION_PREFERENCES, True)
    assert result["execution_mode"] == "cloud"
    assert result["cloud_recommended"] is True


def test_auto_does_not_silently_run_heavy_work_locally_without_cloud():
    with pytest.raises(HTTPException) as error:
        resolve_execution("video.render", {"estimated_duration_seconds": 90}, "auto",
                          DEFAULT_EXECUTION_PREFERENCES, False)
    assert error.value.status_code == 409
    assert error.value.detail["code"] == "cloud_executor_unavailable"


def test_manual_local_override_is_respected_for_heavy_work():
    result = resolve_execution("animation.render", {"estimated_duration_seconds": 90}, "local",
                               DEFAULT_EXECUTION_PREFERENCES, False)
    assert result["execution_mode"] == "local"
    assert result["cloud_recommended"] is True


def test_cloud_mode_requires_configured_executor():
    with pytest.raises(HTTPException) as error:
        resolve_execution("story.outline", {}, "cloud", DEFAULT_EXECUTION_PREFERENCES, False)
    assert error.value.status_code == 409


def test_payload_rejects_non_json_values():
    with pytest.raises(HTTPException) as error:
        resolve_execution("story.outline", {"bad": float("nan")}, "auto",
                          DEFAULT_EXECUTION_PREFERENCES, False)
    assert error.value.status_code == 422
