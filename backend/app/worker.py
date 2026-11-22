"""Single-process task worker primitives.

The supervisor is opt-in and is started by the API lifespan only when explicitly enabled.
Handlers receive decoded task payloads and must not log prompts, secrets, or
provider response bodies. A worker only claims task types it has registered.
"""
import asyncio
import json
import re
import threading
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import sessionmaker

from .task_manager import claim_task, complete_task, fail_task, recover_expired_leases, renew_task_lease

TaskHandler = Callable[[dict[str, Any]], dict[str, Any]]
_TASK_TYPE = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")


class TaskHandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, TaskHandler] = {}
        self._cloud_handler: TaskHandler | None = None

    def register(self, task_type: str, handler: TaskHandler) -> None:
        if not _TASK_TYPE.fullmatch(task_type):
            raise ValueError("Invalid task type")
        if task_type in self._handlers:
            raise ValueError("Task handler already registered")
        if not callable(handler):
            raise TypeError("Task handler must be callable")
        self._handlers[task_type] = handler

    def register_cloud_handler(self, handler: TaskHandler) -> None:
        if self._cloud_handler is not None or not callable(handler):
            raise ValueError("Invalid or duplicate cloud handler")
        self._cloud_handler = handler

    @property
    def task_types(self) -> list[str]:
        return sorted(self._handlers)

    @property
    def cloud_enabled(self) -> bool:
        return self._cloud_handler is not None

    def get(self, task_type: str, execution_mode: str = "local") -> TaskHandler | None:
        return self._cloud_handler if execution_mode == "cloud" else self._handlers.get(task_type)


class WorkerSupervisor:
    """Sequential worker loop with per-operation DB sessions and graceful stop."""

    def __init__(
        self,
        session_factory: sessionmaker,
        worker_id: str,
        registry: TaskHandlerRegistry,
        lease_seconds: int = 120,
        poll_interval_seconds: float = 1.0,
        max_result_bytes: int = 4 * 1024 * 1024,
    ) -> None:
        if not worker_id or len(worker_id) > 120:
            raise ValueError("Invalid worker id")
        if not 10 <= lease_seconds <= 3600:
            raise ValueError("Invalid lease duration")
        if not 0.05 <= poll_interval_seconds <= 60:
            raise ValueError("Invalid poll interval")
        if max_result_bytes < 1024 or max_result_bytes > 16 * 1024 * 1024:
            raise ValueError("Invalid result size limit")
        self.session_factory = session_factory
        self.worker_id = worker_id
        self.registry = registry
        self.lease_seconds = lease_seconds
        self.poll_interval_seconds = poll_interval_seconds
        self.max_result_bytes = max_result_bytes
        self._stop = asyncio.Event()

    def request_stop(self) -> None:
        self._stop.set()

    def run_once(self) -> bool:
        """Run at most one registered task. Returns False when no work is ready."""
        task = None
        db = self.session_factory()
        try:
            recover_expired_leases(db)
            task = None
            if self.registry.task_types:
                task = claim_task(db, self.worker_id, self.lease_seconds,
                                  task_types=self.registry.task_types, execution_modes=["local"])
            if task is None and self.registry.cloud_enabled:
                task = claim_task(db, self.worker_id, self.lease_seconds, execution_modes=["cloud"])
        finally:
            db.close()
        if task is None:
            return False

        handler = self.registry.get(task["task_type"], task.get("execution_mode", "local"))
        if handler is None:
            # Defensive guard; claim filtering should make this unreachable.
            self._fail(task["id"], "handler_unavailable", "No handler is registered")
            return True
        heartbeat_stop = threading.Event()
        lease_lost = threading.Event()

        def heartbeat_loop() -> None:
            interval = max(1.0, self.lease_seconds / 3)
            while not heartbeat_stop.wait(interval):
                db = self.session_factory()
                try:
                    if not renew_task_lease(db, task["id"], self.worker_id, self.lease_seconds):
                        lease_lost.set()
                        return
                except Exception:
                    # If ownership cannot be confirmed, never commit a stale result.
                    lease_lost.set()
                    return
                finally:
                    db.close()

        heartbeat = threading.Thread(
            target=heartbeat_loop, name=f"lease-heartbeat-{task['id'][:8]}", daemon=True
        )
        heartbeat.start()
        try:
            payload = task.get("payload") or {}
            handler_payload = dict(payload)
            handler_payload["_studio_task"] = {"id": task["id"], "task_type": task["task_type"],
                                                "execution_mode": task.get("execution_mode", "local"),
                                                "worker_id": self.worker_id,
                                                "remote_job_id": task.get("remote_job_id") }
            result = handler(handler_payload)
        except Exception as exc:
            heartbeat_stop.set()
            heartbeat.join()
            if not lease_lost.is_set():
                code = getattr(exc, "error_code", None) or ("handler_invalid_result" if isinstance(exc, (TypeError, ValueError)) else "handler_error")
                message = getattr(exc, "public_message", "Task handler failed; inspect local diagnostic tooling")
                self._fail(task["id"], code, message)
            return True
        finally:
            heartbeat_stop.set()
            heartbeat.join()

        if lease_lost.is_set():
            # The task may have been recovered/reclaimed. Its result is discarded.
            return True
        try:
            if not isinstance(result, dict):
                raise TypeError("Task handlers must return an object")
            encoded = json.dumps(result, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
            if len(encoded.encode("utf-8")) > self.max_result_bytes:
                self._fail(task["id"], "result_too_large", "Task result exceeded the configured limit")
                return True
            self._complete(task["id"], result)
        except Exception as exc:
            code = getattr(exc, "error_code", None) or ("handler_invalid_result" if isinstance(exc, (TypeError, ValueError)) else "handler_error")
            message = getattr(exc, "public_message", "Task handler failed; inspect local diagnostic tooling")
            self._fail(task["id"], code, message)
        return True

    def _complete(self, task_id: str, result: dict[str, Any]) -> None:
        db = self.session_factory()
        try:
            complete_task(db, task_id, self.worker_id, result)
        finally:
            db.close()

    def _fail(self, task_id: str, code: str, message: str) -> None:
        db = self.session_factory()
        try:
            fail_task(db, task_id, self.worker_id, code, message, retry_delay_seconds=30)
        finally:
            db.close()

    async def run_forever(self) -> None:
        while not self._stop.is_set():
            try:
                worked = await asyncio.to_thread(self.run_once)
            except Exception:
                # Keep the supervisor alive through transient DB/worker errors.
                worked = False
            if not worked:
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=self.poll_interval_seconds)
                except asyncio.TimeoutError:
                    pass

