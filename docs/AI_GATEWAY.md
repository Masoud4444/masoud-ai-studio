# AI Gateway — implementation guide

This document describes the current implementation in `implementation/bootstrap-001`. It is not a claim that the service is production-ready or publicly safe to expose.

## Current API surface

All routes are under `/api/v1`.

| Method | Route | Purpose |
|---|---|---|
| POST | `/ai/providers` | Register an OpenAI-compatible provider (optional priority 1–1000; lower wins) |
| GET | `/ai/providers` | List providers (credential fields are never returned) |
| PATCH | `/ai/providers/{provider_id}` | Change provider priority or enabled state |
| DELETE | `/ai/providers/{provider_id}` | Disable a provider; history is retained |
| POST | `/ai/providers/{provider_id}/test` | Check the provider's `/models` endpoint and verify matching model IDs |
| GET | `/ai/models` | List model capability declarations and verification status |
| PATCH | `/ai/providers/{provider_id}/models/{model_id}` | Set model capability declarations |
| PUT | `/ai/providers/{provider_id}/models/{model_id}/pricing` | Set manually sourced input/output prices |
| GET | `/ai/providers/{provider_id}/models/{model_id}/pricing/history` | Read immutable pricing versions |
| POST | `/ai/chat/completions` | Send a non-streaming chat completion |
| GET | `/ai/usage/summary` | Current UTC-month usage and estimated-cost summary |

## Database setup

Install dependencies and apply migrations from the repository root:

```bash
python -m pip install -r requirements.txt
mkdir -p data
alembic upgrade head
```

Set `MASOUD_STUDIO_DATABASE_URL` before running Alembic if the database is not the default SQLite file. Managed application startup defaults to migration mode and no longer silently calls `create_all`. `MASOUD_STUDIO_SCHEMA_MODE=create` enables the development-only metadata bootstrap.

Migrations 0001–0005 are intentionally non-destructive on downgrade. The first revision adopts existing tables with `checkfirst`; later revisions add gateway lease, capability, pricing, pricing-history and registry-backfill support.

## Credential encryption

The gateway requires a 32-byte AES-256 key encoded as URL-safe Base64 when a provider API key is saved. Generate one locally:

```bash
python -c "import base64,secrets; print(base64.urlsafe_b64encode(secrets.token_bytes(32)).decode())"
```

Set it in the process environment as `MASOUD_STUDIO_CREDENTIAL_KEY`. Version-specific keys can be set as `MASOUD_STUDIO_CREDENTIAL_KEY_V1`, `MASOUD_STUDIO_CREDENTIAL_KEY_V2`, etc., and the active version is selected with `MASOUD_STUDIO_CREDENTIAL_KEY_VERSION`. Keep old version keys available until all records encrypted with them have been re-encrypted through a future rotation workflow. Never commit the key, put it in frontend code, or send it in chat.

Provider credentials and idempotent response payloads are AES-GCM encrypted in the database. API responses never include encrypted or plaintext credential fields. The key itself is not stored in SQLite. A production desktop build should move key custody to Windows DPAPI/OS credential storage.

## Register a provider

Example request body (send directly to the local API; never paste a real API key into a public issue or source file):

```json
{
  "name": "Primary Provider",
  "base_url": "https://api.example-provider.com/v1",
  "api_key": "YOUR_SECRET",
  "models": ["model-id"]
}
```

The URL validator accepts HTTPS on port 443, rejects credentials/query/fragment/local and non-public destinations, and checks DNS at registration. Immediately before each outbound call, the gateway resolves again, rejects any non-global answer, and pins the connection to the validated address while preserving TLS hostname verification. Redirects and environment proxies are disabled.

Model routing selects the first enabled provider declaring the requested model, ordered by ascending priority and then creation time. Provider priority can be changed with the provider PATCH route.\n\nThe provider connectivity test calls `GET {base_url}/models`. It verifies that declared model IDs are present in the provider's returned list. This does **not** prove that each declared capability (vision, tools, audio, etc.) works. The status `model_id_verified` is deliberately narrower than capability verification.

## Send a chat completion

The request must include a stable `Idempotency-Key` header of 8–200 characters:

```http
POST /api/v1/ai/chat/completions
Idempotency-Key: project-episode-scene-request-001
Content-Type: application/json
```

```json
{
  "model": "model-id",
  "provider_id": "provider-uuid",
  "messages": [
    {"role": "system", "content": "You are a careful writing assistant."},
    {"role": "user", "content": "Help me outline this scene."}
  ],
  "temperature": 0.4,
  "max_tokens": 1200
}
```

A repeated key with the same normalized request replays the encrypted stored response without another provider call. Reusing a key with a different request returns a conflict. Pending requests use a 180-second lease; expired leases can be recovered after a process crash. Provider generation is non-streaming in this implementation. A timeout can still be ambiguous if a remote provider completed generation but the response was lost; external providers may not honor this gateway's idempotency key.

## Model capabilities and pricing

Capabilities are owner-declared metadata and remain `declared` until a separate capability-specific test exists. A successful `/models` probe changes only matching model IDs to `model_id_verified`.

Prices are not guessed or fetched automatically. Set the provider's input and output prices in USD per million tokens using the pricing endpoint. Each update creates a new immutable pricing-history version. Usage rows store the estimated cost and pricing version that applied at generation time. If no price is configured, the request is counted as unpriced and the cost remains null; the usage summary reports this explicitly.

These figures are estimates from manually entered token prices, not provider invoices. They may omit cached tokens, reasoning tokens, image/audio billing, taxes, discounts, and other provider-specific billing rules.

## Operational and security boundaries

- Provider request timeout: 90 seconds.
- Maximum provider response body: 4 MiB.
- Maximum serialized gateway request: 1 MiB.
- Streaming is not enabled.
- Automatic retry/fallback is intentionally not enabled: blindly retrying a generation request can create duplicate charges when the remote outcome is ambiguous.
- No user authentication or authorization layer has been implemented yet. Keep the API bound to localhost/private trusted access only. Do not expose it to the public internet or an untrusted LAN.
- There is no monthly budget enforcement, provider concurrency limiter, circuit breaker, or OS keychain integration yet.
- Prompt and response content are not written to general application logs. Completed responses are stored encrypted for idempotent replay.
- Test on Windows before treating the desktop environment as verified.

## CI verification

GitHub Actions installs the dependencies, runs `alembic upgrade head` against a fresh SQLite database, then runs pytest. A passing Linux workflow is not equivalent to Windows verification or a production security audit.
