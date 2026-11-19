# Central Task Manager

Status: **Implemented; awaiting CI verification**

The Task Manager is the durable execution ledger for future Studio workflows. It is separate from the Production Orchestrator: it stores task intent and lifecycle state, while orchestration logic will later build and coordinate production graphs on top of it.

## Current capabilities

- Durable task records with project association, task type, JSON payload/result, priority, attempt budget, availability time, worker lease, and error fields.
- Idempotent task creation using a SHA-256 hash of the caller's idempotency key and a canonical request hash. Reusing a key for a different request returns `409`.
- Prerequisite dependencies. A task is claimable only after every prerequisite succeeds. A failed/cancelled/blocked prerequisite moves the dependent task to `blocked`.
- Lifecycle primitives: claim, complete, fail, bounded retry scheduling, manual retry, cancellation of queued/blocked tasks, and expired-lease recovery.
- Append-only lifecycle events for creation, claim, completion, failure/retry, cancellation, dependency blocking, and lease recovery.
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

Workers must only store sanitized error messages. Raw provider responses, prompts, credentials, and secrets must not be placed in task error fields or event details.

**Current execution boundary:** no worker process, background scheduler, or public claim/complete endpoint has been enabled yet. This is deliberate until authentication, worker identity, and local process lifecycle are implemented. Run a single worker process with SQLite; multi-worker claim coordination and production-grade locking still require verification and hardening.

## Not yet implemented

- Production Orchestrator graph definitions and dependency expansion.
- Worker process/supervisor and durable polling loop.
- Dead-letter queue UI and operator dashboard.
- Cancellation signalling for already-running work.
- Per-task resource quotas, global concurrency limits, and rate limiting.
- Authentication/authorization for worker operations.
- Multi-process SQLite coordination and PostgreSQL concurrency/load verification.
- CI verification of migration 0007 and the new lifecycle tests.
