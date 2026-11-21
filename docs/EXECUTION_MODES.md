# Execution modes and cloud offloading

## Routing policy

Masoud AI Studio exposes three per-task execution choices: `auto`, `local` and `cloud`. The persisted workspace default is configurable in Settings. Auto classifies a task as heavy when its task type is a known render/batch workload, its declared `estimated_duration_seconds` exceeds the configured threshold, or its serialized input exceeds the configured byte limit. Defaults are 8 seconds and 2 MiB.

- Light jobs route to the local worker.
- Heavy jobs route to the remote executor when it is configured and the worker is enabled.
- Auto never silently falls back to local execution for a heavy job when cloud is unavailable; it returns `cloud_executor_unavailable`.
- Explicit Local is an intentional override. Explicit Cloud requires a configured executor and enabled worker.
- Routing metadata is stored inside the existing durable task record and hidden from the user payload, so no new queue broker or database migration is needed.

## Remote executor contract

Configure these secrets in the Windows process environment or backend service environment:

- `MASOUD_STUDIO_CLOUD_EXECUTOR_URL`: HTTPS base URL of the remote executor.
- `MASOUD_STUDIO_CLOUD_EXECUTOR_TOKEN`: bearer token. Never place this in workspace preferences or logs.
- `MASOUD_STUDIO_WORKER_ENABLED=true`: required for a service deployment; the packaged Windows launcher enables it automatically when endpoint and token are present.
- Optional `MASOUD_STUDIO_CLOUD_POLL_SECONDS` (1–30, default 3).
- Optional `MASOUD_STUDIO_CLOUD_MAX_WAIT_SECONDS` (60–86400, default 21600).

The adapter sends `POST /v1/jobs` with an `Idempotency-Key` equal to the durable local task ID. Expected response: `{ "job_id": "...", "status": "queued" }`. It polls `GET /v1/jobs/{job_id}` and expects `status` (`queued`, `running`, `processing`, `succeeded`, `failed`), optional `progress_percent`, `result`, `estimated_cost_usd` and `actual_cost_usd`. The remote ID, progress and costs are saved locally while the worker lease is active. Retries reuse the same idempotency key to avoid duplicate paid jobs; the remote provider must honor that key.

Provider response bodies, prompts, credentials and raw exception details are not written to task logs. Redirects are disabled, TLS is required, response bodies are size-limited and the endpoint is configured by the machine/service administrator rather than submitted by an untrusted client.

## Durable status and client behavior

The local database remains the source of truth for job ID, status, stage, progress, cost and result. Clients can use:

- `POST /api/v1/tasks` with an `Idempotency-Key` and optional `execution_mode`.
- `POST /api/v1/production/runs` with optional `execution_mode`.
- `GET /api/v1/tasks?limit=100` for the queue.
- `GET /api/v1/tasks/{task_id}` after app restart.
- `GET /api/v1/tasks/{task_id}/events` for the event timeline.

The Windows/web Execution Center polls while visible and retains the last known state during temporary network loss. Closing the UI does not delete the task. The remote job continues while the local worker process remains available; if the process exits, its lease expires and the task is safely reclaimed. Re-submission uses the same idempotency key.

## Current handler boundary

The queue and routing layer are ready for module-owned task handlers, but the only built-in local handler at this point is the system health check. Creative production task handlers are still being integrated incrementally. A local task with no registered handler remains safely queued; cloud mode can dispatch any task type through the configured remote executor.

## Android companion integration

There is not yet a native Android source module in this repository. The API is platform-neutral; the companion app should use AndroidX WorkManager as a thin persistent sync/polling client, not as a second authoritative queue. Persist the Studio task ID in WorkManager input data, require network connectivity, use unique work per Studio task ID, poll the task endpoint with bounded exponential backoff, and store only the latest status locally. This follows Android's recommended persistent-work model and survives process death/reboot. Heavy media computation remains on the remote executor, never on the Android UI thread.

## Reuse and license review

- Existing project code: `backend/app/task_manager.py` and `backend/app/worker.py` already implement durable SQLite/SQLAlchemy jobs, idempotency, worker leases, recovery, retries, dependencies and task events. We extended these primitives instead of introducing Redis/Celery or copying an unmaintained queue.
- [AndroidX](https://github.com/androidx/androidx) (Apache-2.0): WorkManager is the selected Android-side persistence/scheduling pattern. We do not vendor AndroidX code into the Python backend.
- [HTTPX](https://github.com/encode/httpx) (BSD-3-Clause): the existing runtime dependency is used for bounded asynchronous HTTPS requests, timeouts and explicit redirect policy. No new HTTP library is added.
- [taskq](https://github.com/ifleonlabs/taskq) (MIT): reviewed as a lightweight SQLite queue reference for durable jobs, leases and retry semantics. Its implementation is not copied because this project already has a richer SQLAlchemy queue integrated with production workflows.

This phase provides the generic executor protocol and routing layer. It does not provision a cloud account, GPU workers or a paid provider; cloud dispatch remains disabled until the administrator supplies the HTTPS endpoint and token.
