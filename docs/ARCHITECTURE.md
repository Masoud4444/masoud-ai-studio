# Architecture Principles

## 1. Product architecture

Masoud AI Studio follows **Full Vision, Simplified Architecture, Incremental Implementation**.

The complete product vision and approved capabilities remain in scope. Complexity is reduced in the initial implementation, and modules are delivered incrementally rather than removed from the roadmap.

## 2. Initial deployment shape

Use a modular monolith with:

- one backend application
- one primary database (SQLite initially)
- one storage subsystem
- one AI Gateway
- one Agent Manager
- one Production Orchestrator
- one central Task Manager
- one unified frontend with focused workspaces

Do not introduce microservices or distributed infrastructure without a demonstrated requirement.

## 3. Module boundaries

Modules own their domain logic, schemas, persistence interfaces, and API contracts. Cross-module communication should use explicit interfaces and events rather than reaching into another module's internals.

Initial domains include:

- Studio OS and project management
- Research and source provenance
- Story and narrative development
- Characters, worlds, and continuity
- Visual style and cinematography
- Image, video, audio, subtitles, and editing
- Asset management and storage
- AI Gateway and provider capabilities
- Agents, tasks, and production orchestration
- Quality, compliance, approvals, export, and analytics

## 4. Data and storage

- SQLite is the initial database, with Alembic migrations.
- Keep important relationships relational; use JSON only for genuinely flexible metadata.
- Use content hashes for immutable blobs and deduplication.
- Separate project assets from the universal library.
- Never delete a blob while active references remain.
- Use atomic writes, validated paths, MIME inspection, quarantine, and recovery procedures.
- Keep storage behind an interface so a future object-storage backend does not require domain rewrites.

## 5. AI Gateway and secrets

- Provider credentials remain backend-only.
- Encrypt stored credentials using an appropriate platform-backed key mechanism.
- Do not log prompts, responses, API keys, or other secrets in general application logs.
- Validate provider endpoints and defend against SSRF.
- Track capability as tested, provider-declared, or unknown.
- Use idempotency and concurrency controls to prevent duplicate costly generation.

## 6. Human control and provenance

- Consequential actions require explicit human approval.
- Approvals bind to the exact content/version/hash reviewed.
- A change to approved content invalidates the affected approval.
- Agents operate with limited tool permissions and cannot grant themselves approval.
- Preserve source provenance, evidence, confidence, version history, and decision records.

## 7. Clients and security

- Windows desktop is the primary host for the first release.
- Android and Web/PWA are companion clients.
- Remote access is disabled by default and must be explicitly configured securely.
- Use RTL/LTR-aware UI for Persian and English.
- Keep local-first and offline-first behavior as the default.

## 8. Change discipline

Every implementation milestone must have:

1. a bounded scope
2. explicit acceptance criteria
3. migration and compatibility considerations
4. tests appropriate to the change
5. a reviewable commit
6. an honest status update

Do not describe designed features as implemented, or unexecuted tests as passing.
