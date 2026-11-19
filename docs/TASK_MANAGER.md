# Central Task Manager

Status: **Implemented; awaiting CI verification**

The Task Manager is the durable execution ledger for future Studio workflows. It is separate from the Production Orchestrator: it stores task intent and lifecycle state, while orchestration logic will later build and coordinate production graphs on top of it.

## Current capabilities

- Durable task records with project association, task type, JSON payload/result, priority, attempt budget, availability time, worker lease, and error fields.
- Idempotent task creation using a SHA-256 hash of the caller's idempotency key and a canonical request hash. Reusing a key for a different request returns `409`.
- Prerequisite dependencies. A task is claimable only after every prerequisite succeeds. A failed/cancelled/blocked/paused prerequisite moves the dependent task to `blocked`.
- Lifecycle primitives: claim, complete, fail, bounded retry scheduling, manual retry, cancellation of queued/blocked tasks, and expired-lease recovery.
- Append-only lifecycle events for creation, claim, completion, failure/retry, cancellation, dependency blocking, lease recovery, and lease renewal.
- Priority ordering: lower numeric value is preferred; creation time breaks ties.

## API

All routes are under `/api/v1`:

- `POST /tasks` — create; requires `Idempotency-Key` header (8–200 characters).
- `GET /tasks` — list with `limit`, `offset`, optional `status` and `project_id`.
- `GET /tasks/{task_id}` — inspect task and prerequisites.
- `POST /tasks/{task_id}/cancel` — cancel a queued or blocked task.
- `POST /tasks/{task_id}/retry` — manually retry a failed/blocked task if its attempt budget remains.

Example create request:

```http
POST /api/v1/tasks
Idempotency-Key: research-intake-2026-001
Content-Type: application/json

{
  "task_type": "research.collect",
  "project_id": null,
  "priority": 50,
  "max_attempts": 3,
  "depends_on": [],
  "payload": {"query": "Visual storytelling references", "language": "en"}
}
```

## Worker contract

The internal service functions in `backend/app/task_manager.py` are the worker contract:

- `claim_task(db, worker_id, lease_seconds=120)`
- `complete_task(db, task_id, worker_id, result)`
- `fail_task(db, task_id, worker_id, error_code, error_message, retry_delay_seconds=30)`
- `recover_expired_leases(db)`
- `renew_task_lease(db, task_id, worker_id, lease_seconds=120)`

Workers must only store sanitized error messages. Raw provider responses, prompts, credentials, and secrets must not be placed in task error fields or event details.

**Worker supervisor foundation:** `backend/app/worker.py` now provides a sequential, single-process supervisor, a validated handler registry, per-operation database sessions, lease recovery, handler-type allowlisting, active lease heartbeats/renewal, bounded result serialization, graceful stop signalling, and sanitized failure persistence. The API lifespan starts it only when `MASOUD_STUDIO_WORKER_ENABLED=true`; the default is disabled. The only built-in handler is the non-billable `system.healthcheck` smoke-test handler. Creative workflow task types remain queued until their owning modules register real handlers.

No public claim/complete endpoints exist. Keep the API and opt-in worker on localhost or a trusted private environment; the API still has no authentication/authorization. Run a single worker process with SQLite; multi-worker claim coordination and production-grade locking still require verification and hardening.

## Not yet implemented

- Windows service/desktop process management, hard execution timeouts/process isolation, worker health telemetry, and multi-worker-safe claim coordination.
- Dead-letter queue UI and operator dashboard.
- Cancellation signalling for already-running work.
- Per-task resource quotas, global concurrency limits, and rate limiting.
- Authentication/authorization for worker operations.
- Multi-process SQLite coordination and PostgreSQL concurrency/load verification.
- CI verification of migrations 0007–0008 and the Task Manager, Orchestrator, and Worker tests.


**Run pause integration:** production runs can pause queued and approval-waiting tasks. Each task stores its prior state in `paused_from_status` (migration 0009), and resume restores it. Paused tasks are not claimable. A run with active work enters `pausing`; active work is not forcibly interrupted. Run cancellation is rejected while any task is running.
