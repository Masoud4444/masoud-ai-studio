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

Each agent has a positive per-run USD ceiling and monthly USD budget. They are configuration ceilings, not yet an enforced spend ledger. Agent execution must remain disabled at runtime until budget reservation, usage reconciliation, and concurrency-safe budget enforcement are implemented.

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
