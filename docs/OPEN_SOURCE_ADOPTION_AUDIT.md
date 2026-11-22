# Open-source Adoption Audit — Storyboard & Visual Production

Date: 2026-11-22

## Decision

Adopt proven workflow ideas selectively. Do not fork, vendor, replace, or restructure StoryForge AI Studio. The existing Modular Monolith remains authoritative: one FastAPI backend, one SQLite/Alembic data store, one asset-storage subsystem, one AI Gateway, one Agent Manager, one Task Manager, and the existing React/Vite application.

This audit is an integration gate, not a claim that any external engine has already been integrated. No third-party source files, runtime dependencies, model weights, or workflow graphs are copied by this change.

## Existing StoryForge foundations to preserve

- `Story` and ordered `StoryScene` are the canonical narrative records.
- Character/World Bible, Locations, Props registry, Timeline, and Continuity are already separate domain modules and must remain the source of canonical facts.
- `Asset` / `ProjectAsset` are the canonical media and project-asset references. New production records must reference these rather than introduce a parallel media store.
- Story revision snapshots and optimistic version checks must be preserved.
- Generated proposals remain review-first. AI must not silently mutate screenplay, Bible, timeline, continuity facts, or approved assets.
- Existing API routes and migrations are additive-only; no destructive migration, table rename, broad refactor, or replacement of the current app shell.

## Repositories audited

| Repository | License reported by GitHub | Useful verified design/code areas | Adoption decision |
|---|---|---|---|
| [StoryBored](https://github.com/storybored-app/storybored) | MIT | FastAPI/React structure; project → scene → shot → take; ComfyUI workflow packs; shot take/approval flow; serialized GPU job lane; animatic export; fake engine tests | Highest-priority reference. Reuse the workflow-pack/adapter boundary, take comparison and approval concepts, and animatic acceptance criteria. Do not import its database, job queue, or app shell. |
| [CineMatrix](https://github.com/kirklasalle/CineMatrix) | MIT | Screenplay parsing and previsualization; storyboard engine; character library; cinematography and animatic-oriented workflows; parser, export, path-security tests | Use as a secondary reference for screenplay ingestion, shot metadata and character reference-sheet coverage. Verify individual implementations before any code port. |
| [OpenFrame](https://github.com/kazim-45/openframe) | MIT | `ShotTemplates.jsx` visual shot-size templates; panel-oriented storyboard editing and per-panel camera metadata | Use as a UI/interaction reference. Reimplement the template catalog in StoryForge's existing visual language; do not add its application or persistence model. |
| [Panelwise](https://github.com/Katlego-tech/Panelwise) | Apache-2.0 | `CONTRACTS.md`; screenplay-grounded entity extraction; frame audit and re-render design; extensive focused tests | Adopt the strongest product principle: every planned/generated frame must retain traceable screenplay evidence and canonical entity references. Vision-based frame audit is a later, separately gated capability. |
| [Abekyo Editor](https://github.com/abekyo/abekyo-editor) | MIT | JSON-native project schema; deterministic validation endpoint; Remotion render pipeline; timeline and media validation tests | Reference for a future Animatic/Editing adapter. Do not add Next.js, Remotion, or a second editor runtime to the current app now. |
| [Open Gate](https://github.com/opengateapp/opengate) | GPL-3.0 | Production-management concepts | Design reference only. No code reuse unless a future explicit licensing review accepts GPL obligations. |

License metadata was checked at repository level. Before copying any source, inspect the exact file's license headers, dependency licenses, model/weight licenses, attribution obligations, and upstream changes. A repository-level MIT/Apache declaration is not a substitute for checking bundled assets and model artifacts.

## Findings that are safe to adopt

### 1. Storyboard data should extend the existing story graph

The eventual records should be additive and linked to the existing `Story` and `StoryScene` identifiers. A storyboard shot should not duplicate the scene's script, character profile, location, prop definition, or asset bytes.

A proposed shot record will need, at minimum:
- stable shot identity and scene ordering;
- shot size/framing, camera angle, movement, lens/focal-length note and composition intent;
- action, dialogue coverage, duration and transition intent;
- links to existing character, location and prop records;
- source text/evidence spans from the scene;
- prompt/version metadata and reference asset IDs;
- multiple generation takes with explicit selected/approved state;
- optimistic versioning and audit history.

The exact relational schema and API contract must be designed against the live models before adding a migration.

### 2. Separate a shot plan from generated media

A shot plan is structured creative intent; a take is one generated attempt; an asset is the immutable media object. Keep these concepts separate. A failed or replaced take must not overwrite an approved take or delete an asset still referenced elsewhere.

### 3. Engine integration belongs behind adapters

ComfyUI and other image/video engines must be optional adapters behind the existing AI Gateway and Task Manager. Engine-specific graph/node identifiers must live in validated workflow-pack data, not in StoryForge domain logic. An unconfigured engine must leave the rest of the studio usable.

Do not import StoryBored's single-GPU queue: StoryForge already has its own task lifecycle, leases, retries, worker supervision and execution policy. Any media-specific concurrency policy must be implemented as a capability/worker constraint within those existing mechanisms.

### 4. Human review and evidence are mandatory

Use a review-first lifecycle:
- draft shot plan;
- validate screenplay and canon references;
- generate one or more takes;
- compare and select;
- explicit approval tied to the exact take/asset hash;
- approval invalidated when the approved content changes.

Every proposed shot should point back to the scene and the exact script excerpt(s) supporting its action, cast, props and location. Unsupported model inventions must be flagged, not silently accepted.

### 5. Animatic is a downstream deterministic renderer

The animatic should consume approved/selected takes and an ordered shot list with explicit durations, transitions and audio timing. Rendering must be reproducible from a validated project document. The initial implementation should use a narrow renderer adapter; do not introduce a second application/backend or a parallel project format.

## Integration sequence

1. **Storyboard foundation (next vertical slice):** additive shot/take schema and migration; CRUD/list/reorder API scoped to an existing story scene; validation of ownership for scene, character, location, prop and asset references; focused backend tests.
2. **Storyboard workspace:** editable shot cards and shot-size templates inside the existing Story workspace; camera metadata; screenplay evidence display; no parallel project navigation or state store.
3. **Take lifecycle:** task-backed generation adapter, multiple takes, compare/select/approve, approval bound to asset hash; fake engine tests before real engine calls.
4. **Continuity and visual audit:** reuse existing Canon/Continuity records; first deterministic checks, then optional vision audit with evidence and reviewable findings.
5. **Animatic adapter:** deterministic ordered render using approved media, duration and audio metadata; validation before rendering and cancellation/progress through the existing Task Manager.
6. **Editing expansion:** only after the animatic contract is stable, evaluate Remotion/FFmpeg integration behind an adapter and reuse existing Asset storage.

Each step must be a vertical slice with API contract, migration safety, UI, focused tests and CI evidence. Do not start later phases by introducing their dependencies early.

## Explicit non-goals for this adoption

- No replacement of the current React/Vite frontend or FastAPI backend.
- No microservices, second database, second asset store, or parallel task queue.
- No automatic rewrite of screenplay or canonical Bible.
- No automatic public upload or publishing.
- No bulk copy of external repositories or model weights.
- No modification of `main`; all work stays on `implementation/bootstrap-001`.

## Current status

- Repository structure and current Story/Scene, Asset, Bible, Props, Timeline, Continuity, Task Manager and Alembic foundations inspected.
- External repository metadata, recursive source trees, key architecture/contract documents, and representative storyboard/animatic/grounding files inspected.
- This commit adds the adoption decision and integration guardrails only. No application behavior or database schema is changed.
- The first functional integration should be the additive Storyboard foundation described in step 1; it must be implemented against the current code and tested before claiming completion.
