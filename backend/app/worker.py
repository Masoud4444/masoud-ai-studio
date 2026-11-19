"""Single-process task worker primitives.

The supervisor is opt-in and is not started by the API automatically.
Handlers receive decoded task payloads and must not log prompts, secrets, or
provider response bodies. A worker only claims task types it has registered.
"""
import asyncio
import json
import re
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import sessionmaker

from .task_manager import claim_task, complete_task, fail_task, recover_expired_leases

TaskHandler = Callable[[dict[str, Any]], dict[str, Any]]
_TASK_TYPE = re.compile(r"^[a-z][a-z0-9_.-]{0,99}$")


class TaskHandlerRegistry:
    def __init__(self) -> None:
        self._handlers: dict[str, TaskHandler] = {}

    def register(self, task_type: str, handler: TaskHandler) -> None:
        if not _TASK_TYPE.fullmatch(task_type):
            raise ValueError("Invalid task type")
        if task_type in self._handlers:
            raise ValueError("Task handler already registered")
        if not callable(handler):
            raise TypeError("Task handler must be callable")
        self._handlers[task_type] = handler

    @property
    def task_types(self) -> list[str]:
        return sorted(self._handlers)

    def get(self, task_type: str) -> TaskHandler | None:
        return self._handlers.get(task_type)


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
            task = claim_task(
                db, self.worker_id, self.lease_seconds,
                task_types=self.registry.task_types,
            )
        finally:
            db.close()
        if task is None:
            return False

        handler = self.registry.get(task["task_type"])
        if handler is None:
            # Defensive guard; claim filtering should make this unreachable.
            self._fail(task["id"], "handler_unavailable", "No handler is registered")
            return True
        try:
            payload = task.get("payload") or {}
            result = handler(payload)
            if not isinstance(result, dict):
                raise TypeError("Task handlers must return an object")
            encoded = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
            if len(encoded.encode("utf-8")) > self.max_result_bytes:
                self._fail(task["id"], "result_too_large", "Task result exceeded the configured limit")
                return True
            self._complete(task["id"], result)
        except Exception as exc:
            # Do not persist exception messages: they may contain prompts,
            # credentials, URLs, or raw provider response fragments.
            code = "handler_invalid_result" if isinstance(exc, TypeError) else "handler_error"
            self._fail(task["id"], code, "Task handler failed; inspect local diagnostic tooling")
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

