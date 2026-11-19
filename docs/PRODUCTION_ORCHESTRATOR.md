# Production Orchestrator

Status: **Initial workflow graph implementation committed; CI verification pending**

## Purpose

The Production Orchestrator turns a production workflow definition into a durable directed acyclic task graph. The Central Task Manager remains responsible for task lifecycle and worker leases; the Orchestrator owns workflow templates, run identity, step ordering, dependency construction, and approval checkpoints.

## Current workflow registry

The first registered template is `creative.preproduction` version 1:

1. `research_intake` — `research.intake`
2. `story_development` — `story.development`, after research
3. `character_world_bible` — `story.character_world_bible`, after story, held for human approval
4. `visual_development` — `visual.development`, after character/world
5. `storyboard` — `visual.storyboard`, after visual development, held for human approval
6. `production_handoff` — `production.handoff`, after storyboard

The template is a starter production graph, not a claim that the full story, character, visual, or storyboard engines are already implemented. Those task handlers will be added by their respective modules.

## Persistence and atomicity

- `production_runs` stores workflow identity/version, project association, input snapshot, idempotency hash, and aggregate status.
- `production_steps` maps stable step keys and ordering to Task Manager task IDs.
- Creating a run, its tasks, dependencies, events, and step mappings occurs in one database transaction.
- Repeating the same idempotency key and same request replays the existing run; reusing the key for a different request returns `409`.
- Each generated task includes the run ID and step key in its payload. Raw credentials or provider responses must never be included in workflow inputs.

## API

All routes are under `/api/v1`:

- `GET /production/workflows` — list registered workflow templates.
- `POST /production/runs` — create a run; requires `Idempotency-Key`.
- `GET /production/runs` — list runs, optionally filtered by project.
- `GET /production/runs/{run_id}` — inspect aggregate state and ordered steps.
- `POST /tasks/{task_id}/approve` — release a step waiting for human approval.
- `POST /tasks/{task_id}/reject` — reject a waiting step; it is cancelled and downstream tasks will not execute.

Approval is an explicit gate: a task in `waiting_approval` is not claimable. Approving it moves it to `queued`; its prerequisite tasks must still succeed before a worker can claim it.

## Current boundaries and next hardening

- The workflow registry is currently code-defined; versioned database-managed templates are not implemented.
- A generic opt-in Worker Supervisor exists, but no creative workflow task handlers are registered yet. Only the safe `system.healthcheck` handler is built in. The worker is disabled by default and requires `MASOUD_STUDIO_WORKER_ENABLED=true`.
- The API is unauthenticated. Keep it on localhost or a trusted private network; do not expose it publicly. Approval routes must remain under the same trust boundary until authentication/authorization is added.
- Run aggregate status is a read-time projection of step task states; GET/list calls do not write or commit database changes.
- Parallel branch fan-in/fan-out templates, human review artifacts/comments, and authenticated approval identity are not implemented yet.
- Migrations 0007–0009 and Orchestrator/Worker tests are awaiting CI verification.


## Production run controls
- `POST /api/v1/production/runs/{run_id}/pause` pauses queued and approval-waiting steps. Active steps are allowed to finish; the run reports `pausing` until they finish, then `paused`. If an active step fails or its lease expires and a retry is scheduled during the pause, the retry is held in `paused` until the run resumes.
- `POST /api/v1/production/runs/{run_id}/resume` restores each paused task to its exact prior state (`queued` or `waiting_approval`).
- `POST /api/v1/production/runs/{run_id}/cancel` cancels pending, paused, approval-waiting, and blocked steps. It refuses cancellation while any step is running; it never claims to forcibly stop an active handler.
- Pause/resume/cancel transitions are appended to task events. Run control state is persisted; read endpoints remain side-effect free.
