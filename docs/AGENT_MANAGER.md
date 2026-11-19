# Agent Manager

## Purpose

The Agent Manager stores and governs agent configurations. It is deliberately separate from execution: this first implementation does not call an AI provider, run tools, or execute creative tasks.

## Agent lifecycle

- `draft`: initial state; configuration can be edited.
- `enabled`: configuration has passed activation checks; edits and tool-grant changes are locked until disabled.
- `disabled`: inactive configuration; can be edited and later re-enabled.

Enabling requires a non-empty system prompt, a configured enabled AI provider, and a model identifier present in that provider's registered model list. Provider credentials are never returned by Agent Manager endpoints.

## Permissions and tool grants

Agent-level permissions are a controlled allowlist:
- `research.read`
- `project.read`
- `asset.read`
- `content.create`
- `content.edit`
- `asset.create`
- `task.create`
- `ai.generate`

Tool grants are explicit and per-agent. Each grant has a tool name, `read` / `write` / `execute` permission, approval requirement, and enabled flag. Write and execute grants cannot be configured without human approval.

These are configuration and policy records only. Runtime enforcement must be performed by the future Agent Runtime/Tool Broker before any tool is invoked. No agent should be treated as authorized merely because a grant exists in the database.

## Budgets

Each agent has a positive per-run USD ceiling and monthly USD budget. The internal budget ledger now supports idempotent reservations, monthly ceiling checks, transition to running, settlement against actual cost, and release before execution. Reservation amounts must be conservative upper bounds; settlement rejects actual cost above the reserved amount. The ledger is not yet connected to an Agent Runtime or provider usage reconciliation, so it does not by itself authorize or execute a model call. The database row lock serializes reservations on databases that support row-level locking; SQLite deployments remain single-worker only.

## Audit

Agent create, update, enable, disable, and tool-grant replacement operations append records to `agent_events`. System prompts and provider secrets are not copied into audit event details.

## API

All routes are under `/api/v1`:
- `POST /agents`
- `GET /agents`
- `GET /agents/{agent_id}`
- `PATCH /agents/{agent_id}`
- `PUT /agents/{agent_id}/tools`
- `POST /agents/{agent_id}/enable`
- `POST /agents/{agent_id}/disable`

## Security boundary

The API currently has no authentication or authorization. Keep it on localhost or a trusted private network. Do not expose it publicly. Agent configuration and tool grants do not make unauthenticated endpoints safe.


## Internal budget ledger operations

The Agent Manager service exposes internal operations for runtime integration:
- `reserve_agent_budget(...)` reserves a caller-supplied conservative cost ceiling using an idempotency key and request hash.
- `start_agent_budget_reservation(...)` marks the reservation running before a provider call.
- `settle_agent_budget_reservation(...)` records actual cost and success/failure, refusing settlement above the reservation.
- `release_agent_budget_reservation(...)` releases a reservation only if execution has not started.

The ledger uses UTC calendar-month periods. Released reservations do not count against the monthly budget; active reservations count at their reserved amount; settled executions count at actual cost (or conservatively at the reservation if no actual cost is supplied). Runtime must reserve the maximum expected exposure before provider execution and settle from verified usage data.


## Agent Runtime v0.1

The first runtime slice is available at `POST /api/v1/agents/{agent_id}/run`.
It performs text-only model generation through the existing AI Gateway. It does
not execute tools, read project assets, publish content, or perform external
write operations.

Execution gates:
- Agent must be enabled and hold the explicit `ai.generate` permission.
- Provider/model must remain enabled and registered.
- Explicit model pricing is mandatory; unpriced models are rejected before execution.
- A conservative upper-bound reservation is created before the provider call.
  The estimate counts UTF-8 input bytes as an upper-bound token proxy and reserves
  the configured maximum output tokens.
- Per-run and monthly budget ceilings are enforced by the Budget Ledger.
- Gateway idempotency stores the response encrypted; replay returns the stored
  output without a second provider call.
- Ambiguous provider failures settle the reservation at its full reserved
  upper bound rather than assuming the call was free.
- No tool grants are invoked by this runtime slice.

This endpoint inherits the current API's localhost/trusted-network-only
deployment constraint because authentication and authorization are not yet
implemented. Do not expose it publicly. Provider credentials and billable
execution remain unconfigured until the owner explicitly configures them.


## Runtime recovery and idempotency hardening

- Retrying a reservation already in `running` returns the existing reservation instead of starting a second ledger execution. The caller must reuse the same idempotency key; the AI Gateway then deduplicates/replays the corresponding model request.
- Repeated settlement is accepted only when both final status and actual cost exactly match the first settlement. Conflicting settlement attempts are rejected, and audit events are not duplicated.
- This supports recovery after a caller/process interruption and concurrent duplicate submissions. It does not replace a durable runtime execution record, lease expiry policy, or operator reconciliation for genuinely abandoned reservations.


- If the Gateway reports `request_in_progress` for a duplicate caller while the original idempotent request is still within its lease, the Runtime leaves the budget reservation in `running`. It does not prematurely mark the execution failed; retrying with the same key can receive the stored Gateway result after completion.
