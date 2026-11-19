# Package 003 — Projects & Storage Foundation

Status: **Designed; implementation blocked pending verified Foundation 002 source import**  
Date: 2026-11-19

## 1. Goal

Deliver the first persistent project lifecycle and safe local asset-storage foundation on top of the existing application baseline. This package must not replace, fork, or silently recreate Foundation 002.

## 2. Scope

### Included
- Project create, read, update, archive, restore, and list.
- Project metadata, lifecycle state, timestamps, and optimistic concurrency.
- Project settings and extensible metadata with schema validation.
- Storage abstraction with a local filesystem implementation.
- Content-addressed immutable blobs using SHA-256.
- Asset records and explicit project-to-asset relationships.
- Safe file ingestion, metadata extraction, MIME verification, and quarantine path.
- Atomic writes and cleanup/recovery behavior.
- API contracts, database migrations, unit/integration tests.
- Documentation of local data layout and backup/restore expectations.

### Excluded from this package
- AI Gateway/provider integrations.
- Universal Library UI and cross-project promotion workflows.
- Cloud/object storage implementation.
- Semantic indexing and vector database.
- Multi-user permissions and SaaS tenancy.
- Video transcoding, thumbnail generation, and media editing pipelines (later packages).
- Automatic deletion of user files without reference checks.

## 3. Domain model

Use relational tables for durable relationships. JSON is reserved for validated, non-relational extension metadata.

### Project
- id: UUID string, primary key
- slug: unique normalized identifier
- name: required, 1–160 characters
- description: nullable, bounded length
- project_type: controlled string with extensible registry
- status: active | archived
- settings_json: validated settings document
- metadata_json: validated extension metadata
- created_at, updated_at: UTC timestamps
- archived_at: nullable UTC timestamp
- version: integer for optimistic concurrency

Constraints:
- slug unique, stable unless explicitly renamed.
- archived projects are read-only by default; restore is explicit.
- updates must check the expected version to avoid lost writes.

### Asset
- id: UUID string, primary key
- sha256: lowercase 64-character digest
- storage_key: opaque key derived from digest, never a user-supplied path
- original_filename: sanitized display name only
- detected_mime_type: server-detected MIME
- declared_mime_type: nullable client declaration
- size_bytes: non-negative integer
- status: pending | ready | quarantined | missing
- created_at: UTC timestamp
- metadata_json: validated technical metadata

Constraints:
- sha256 + storage_key identify immutable content.
- deduplicate blobs by verified content hash.
- never trust client filename, extension, MIME type, or path.

### ProjectAsset
- project_id: FK Project
- asset_id: FK Asset
- role: source | reference | generated | export | other
- display_name: nullable project-specific label
- metadata_json: validated relationship metadata
- created_at: UTC timestamp
- unique(project_id, asset_id, role) unless a later requirement explicitly permits duplicates.

The relationship record is the ownership/use reference. A blob must not be deleted while any active ProjectAsset or other registered reference points to it.

### StorageOperation (if needed by Foundation 002 queue model)
- id: UUID
- operation_key: unique idempotency key
- operation_type: ingest | verify | delete_candidate | recover
- status: pending | running | succeeded | failed
- attempts, created_at, updated_at
- sanitized_error_code only; never store secrets or file contents in logs.

Prefer reuse of an existing task/job model from Foundation 002 rather than creating a competing queue.

## 4. Storage layout

Keep all paths under a configured application data root. Never accept absolute paths or traversal segments from API input.

Suggested layout:
- database/
- storage/blobs/sha256/ab/cd/<full-sha256>
- storage/staging/
- storage/quarantine/
- projects/ (non-authoritative project exports only)
- previews/
- thumbnails/
- proxies/
- temporary/
- backups/
- logs/

The database is authoritative for metadata and relationships. Blob filenames are derived from content hashes, not original filenames.

## 5. Ingestion flow

1. Accept an upload into a generated staging filename.
2. Enforce configured size limits and stream to disk; do not buffer unbounded uploads in memory.
3. Compute SHA-256 while streaming.
4. Detect MIME from content and compare with allowed policy; do not trust extension or client header.
5. Reject unsupported or suspicious content, or place it in quarantine for review.
6. Flush and atomically move the staged file to its content-addressed destination.
7. In a database transaction, insert/reuse Asset and create ProjectAsset relationship.
8. On failure, preserve recoverable staging state or safely remove only unreferenced temporary data.
9. Make the operation idempotent so retries do not create duplicate blobs or relationships.

Atomicity across filesystem and SQLite is not assumed. Use a recoverable staged workflow and reconciliation on startup.

## 6. Safe deletion and recovery

- Deleting a ProjectAsset relationship does not automatically delete the blob.
- Blob garbage collection is a separate, auditable operation.
- Before deletion, verify zero references across all registered reference tables.
- Use a grace period and dry-run report before physical deletion.
- Never follow symlinks outside the storage root.
- Startup recovery scans staging and operation records; it must not infer deletion from missing metadata.
- Backup must include SQLite plus referenced blobs, with a manifest and integrity verification.
- Restore must verify blob hashes and report missing/corrupt objects.

## 7. API contract proposal

Use the existing API prefix and conventions from Foundation 002 after import. Proposed resources:

- POST /api/v1/projects
- GET /api/v1/projects
- GET /api/v1/projects/{project_id}
- PATCH /api/v1/projects/{project_id}
- POST /api/v1/projects/{project_id}/archive
- POST /api/v1/projects/{project_id}/restore
- POST /api/v1/projects/{project_id}/assets
- GET /api/v1/projects/{project_id}/assets
- DELETE /api/v1/projects/{project_id}/assets/{asset_id} (unlink only)
- GET /api/v1/assets/{asset_id}

Use consistent structured errors, request validation, pagination, and optimistic concurrency. Exact route naming must be reconciled with the imported API conventions before implementation.

## 8. Security requirements

- Resolve and verify every storage path beneath the configured root.
- Reject path traversal, null bytes, symlink escapes, and unsafe filenames.
- Enforce upload size, extension allowlist where appropriate, content-based MIME checks, and upload timeouts.
- Quarantine suspicious or unrecognized files.
- Do not expose raw filesystem paths in API responses.
- Do not log file contents, credentials, prompts, or private user data.
- Keep remote access disabled by default.
- Use least-privilege filesystem permissions.

## 9. Test and acceptance criteria

### Unit tests
- Project validation, slug uniqueness, lifecycle transitions, version conflict.
- SHA-256 correctness and deterministic storage key.
- Filename sanitization and MIME mismatch handling.
- Path traversal and symlink escape rejection.
- Reference counting and safe deletion eligibility.

### Integration tests
- Create/list/read/update/archive/restore projects.
- Upload, deduplicate, link, unlink, and retrieve assets.
- Interrupted upload and retry/idempotency.
- Database failure after blob write and recovery reconciliation.
- Quarantine flow and missing/corrupt blob detection.
- Backup and restore with integrity checks.

### Acceptance
1. Existing Foundation 002 tests remain passing.
2. Existing API and database behavior are not regressed.
3. Project CRUD and lifecycle persist across restart.
4. Identical content is stored once and can be linked safely.
5. No user-supplied path can escape the storage root.
6. Unlinking does not destroy a still-referenced blob.
7. Recovery handles interrupted operations without silent data loss.
8. Migrations upgrade an existing database and support a documented rollback strategy where feasible.
9. All tests are executed and results recorded; no inferred pass status.
10. Windows path and file-lock behavior is tested before Windows support is declared verified.

## 10. Implementation sequence

A. Import and inspect Foundation 002; record exact commit/tag and run its tests.  
B. Reconcile package dependencies, naming, settings, error format, migrations, and task queue with the baseline.  
C. Add Project model + migration + repository/service + API + tests.  
D. Add storage interface + local backend + path security tests.  
E. Add Asset and ProjectAsset models + ingestion + dedup + recovery tests.  
F. Add backup/restore integrity tests and documentation.  
G. Run full suite and create a reviewable milestone commit.

Do not begin steps C–F against guessed package paths or duplicate models before step B is complete.
