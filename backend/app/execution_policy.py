"""Execution routing policy shared by desktop, web and future Android clients."""
import json
import os
from urllib.parse import urlsplit

from fastapi import HTTPException

HEAVY_TASK_MARKERS = (
    "animation", "video.render", "video.generate", "batch.",
    "upscale", "transcode", "composite", "audio.master", "render.sequence",
)
DEFAULT_EXECUTION_PREFERENCES = {
    "execution_mode": "auto",
    "local_max_estimated_seconds": 8,
    "local_max_payload_bytes": 2 * 1024 * 1024,
}


def cloud_executor_configured() -> bool:
    endpoint = os.getenv("MASOUD_STUDIO_CLOUD_EXECUTOR_URL", "").strip()
    token = os.getenv("MASOUD_STUDIO_CLOUD_EXECUTOR_TOKEN", "").strip()
    parsed = urlsplit(endpoint)
    return bool(token and parsed.scheme == "https" and parsed.hostname
                and not parsed.username and not parsed.password
                and not parsed.query and not parsed.fragment)


def resolve_execution(task_type: str, payload: dict, requested_mode: str | None,
                      preferences: dict, cloud_available: bool) -> dict:
    mode = requested_mode or preferences.get("execution_mode", "auto")
    if mode not in {"auto", "local", "cloud"}:
        raise HTTPException(status_code=422, detail={"code": "invalid_execution_mode"})
    try:
        encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False,
                             separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError):
        raise HTTPException(status_code=422, detail={"code": "invalid_task_payload"})
    size = len(encoded)
    estimate = payload.get("estimated_duration_seconds")
    if estimate is not None and (isinstance(estimate, bool) or
            not isinstance(estimate, (int, float)) or estimate < 0 or estimate > 604800):
        raise HTTPException(status_code=422, detail={"code": "invalid_task_duration_estimate"})
    estimate = int(estimate) if estimate is not None else None
    heavy_type = any(marker in task_type.lower() for marker in HEAVY_TASK_MARKERS)
    heavy_size = size > int(preferences.get("local_max_payload_bytes", DEFAULT_EXECUTION_PREFERENCES["local_max_payload_bytes"]))
    heavy_time = estimate is not None and estimate > int(preferences.get("local_max_estimated_seconds", 8))
    heavy = heavy_type or heavy_size or heavy_time
    if mode == "auto":
        if heavy and not cloud_available:
            raise HTTPException(status_code=409, detail={
                "code": "cloud_executor_unavailable",
                "message": "This task exceeds the local execution policy. Configure a cloud executor or explicitly choose local execution.",
                "cloud_recommended": True,
            })
        selected = "cloud" if heavy else "local"
    else:
        selected = mode
    if selected == "cloud" and not cloud_available:
        raise HTTPException(status_code=409, detail={"code": "cloud_executor_unavailable"})
    return {
        "execution_mode": selected,
        "cloud_recommended": bool(heavy),
        "estimated_duration_seconds": estimate,
        "payload_size_bytes": size,
    }
