"""Async HTTP adapter for a configured remote job executor."""
import asyncio
import math
import os
import re
import time
from urllib.parse import urlsplit

import httpx

from .task_manager import update_task_execution


class CloudExecutionError(RuntimeError):
    def __init__(self, error_code: str, public_message: str):
        super().__init__(public_message)
        self.error_code = error_code
        self.public_message = public_message


def _config():
    endpoint = os.getenv("MASOUD_STUDIO_CLOUD_EXECUTOR_URL", "").strip().rstrip("/")
    token = os.getenv("MASOUD_STUDIO_CLOUD_EXECUTOR_TOKEN", "").strip()
    parsed = urlsplit(endpoint)
    if (not token or parsed.scheme != "https" or not parsed.hostname or parsed.username
            or parsed.password or parsed.query or parsed.fragment):
        raise CloudExecutionError("cloud_not_configured", "Cloud execution is not configured.")
    return endpoint, token


def _cost(value):
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0 or value > 1000000000:
        return None
    return round(float(value), 8)


def _json(response):
    if len(response.content) > 8 * 1024 * 1024:
        raise CloudExecutionError("cloud_response_too_large", "Cloud response exceeded the allowed size.")
    try:
        return response.json()
    except ValueError:
        raise CloudExecutionError("cloud_invalid_response", "Cloud service returned an invalid response.")


async def execute_cloud_task(payload: dict, update_progress):
    base_url, token = _config()
    task = payload.get("_studio_task") or {}
    task_id, task_type = task.get("id", ""), task.get("task_type", "")
    if not re.fullmatch(r"[0-9a-fA-F-]{36}", task_id) or not task_type:
        raise CloudExecutionError("cloud_task_invalid", "Cloud task metadata is invalid.")
    timeout = httpx.Timeout(connect=10.0, read=30.0, write=30.0, pool=10.0)
    max_wait = min(86400, max(60, int(os.getenv("MASOUD_STUDIO_CLOUD_MAX_WAIT_SECONDS", "21600"))))
    poll_seconds = min(30, max(1, int(os.getenv("MASOUD_STUDIO_CLOUD_POLL_SECONDS", "3"))))
    clean_payload = {key: value for key, value in payload.items() if key != "_studio_task"}
    headers = {"Authorization": "Bearer " + token, "Idempotency-Key": task_id}
    update_progress(progress_stage="submitting", progress_percent=1)
    started = time.monotonic()
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, trust_env=False) as client:
        try:
            response = await client.post(base_url + "/v1/jobs", headers=headers,
                json={"client_job_id": task_id, "task_type": task_type, "payload": clean_payload})
            response.raise_for_status()
            data = _json(response)
        except CloudExecutionError:
            raise
        except httpx.HTTPError:
            raise CloudExecutionError("cloud_submit_failed", "Cloud service could not accept the job. It will be retried safely.")
        job_id = data.get("job_id") if isinstance(data, dict) else None
        if not isinstance(job_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,200}", job_id):
            raise CloudExecutionError("cloud_invalid_response", "Cloud service returned an invalid job identifier.")
        update_progress(remote_job_id=job_id, progress_stage="queued", progress_percent=5,
                        estimated_cost_usd=_cost(data.get("estimated_cost_usd")))
        while time.monotonic() - started < max_wait:
            await asyncio.sleep(poll_seconds)
            try:
                response = await client.get(base_url + "/v1/jobs/" + job_id, headers=headers)
                response.raise_for_status()
                state = _json(response)
            except CloudExecutionError:
                raise
            except httpx.HTTPError:
                raise CloudExecutionError("cloud_poll_failed", "Connection to the cloud job was interrupted. The job can be resumed safely.")
            if not isinstance(state, dict):
                raise CloudExecutionError("cloud_invalid_response", "Cloud service returned an invalid job status.")
            status = state.get("status")
            percent = state.get("progress_percent", 10 if status == "queued" else 50)
            if isinstance(percent, bool) or not isinstance(percent, int):
                percent = 10 if status == "queued" else 50
            percent = max(0, min(99, percent))
            stage = "queued" if status == "queued" else "processing"
            update_progress(remote_job_id=job_id, progress_stage=stage, progress_percent=percent,
                estimated_cost_usd=_cost(state.get("estimated_cost_usd")),
                actual_cost_usd=_cost(state.get("actual_cost_usd")))
            if status == "succeeded":
                result = state.get("result")
                if not isinstance(result, dict):
                    raise CloudExecutionError("cloud_invalid_result", "Cloud job completed without a valid result object.")
                update_progress(remote_job_id=job_id, progress_stage="ready", progress_percent=100,
                    actual_cost_usd=_cost(state.get("actual_cost_usd")))
                return {"remote_job_id": job_id, "provider": "configured_cloud_executor",
                        "result": result, "estimated_cost_usd": _cost(state.get("estimated_cost_usd")),
                        "actual_cost_usd": _cost(state.get("actual_cost_usd"))}
            if status in {"failed", "cancelled"}:
                raise CloudExecutionError("cloud_job_failed", "The remote job failed. Review the job details and retry if appropriate.")
            if status not in {"queued", "running", "processing"}:
                raise CloudExecutionError("cloud_invalid_status", "Cloud service returned an unsupported job status.")
    raise CloudExecutionError("cloud_timeout", "Cloud job exceeded the configured wait limit and will be retried safely.")


def build_cloud_task_handler(session_factory, worker_id: str):
    def handler(payload: dict) -> dict:
        task_id = (payload.get("_studio_task") or {}).get("id")
        if not task_id:
            raise CloudExecutionError("cloud_task_invalid", "Cloud task metadata is missing.")
        def update(**values):
            db = session_factory()
            try:
                update_task_execution(db, task_id, worker_id, **values)
            finally:
                db.close()
        return asyncio.run(execute_cloud_task(payload, update))
    return handler
