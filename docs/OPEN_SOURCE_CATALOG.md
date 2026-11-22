# Open-source Reference Catalog — StoryForge AI Studio

Last reviewed: 2026-11-22  
Scope: architecture and product research for the existing StoryForge modular monolith. This is a decision catalog, not a vendor list and not a claim that every reference is integrated.

## Adoption policy

1. Reuse a mature library or a narrow engine through an adapter when it solves a real production need.
2. Prefer protocol, file-format, and workflow compatibility over importing another application's architecture.
3. Do not fork or vendor an entire studio, introduce a second database/task queue/asset store, or replace the current UI/backend.
4. Treat repository code, dependencies, custom nodes, fonts, sample assets, and model weights as separate license and security review items.
5. Pin reviewed upstream versions/commits before any code reuse. Re-check license text and notices at the exact revision.
6. Keep all generated outputs reviewable; no external tool may silently alter canonical screenplay, Bible, continuity, or approved media.
7. Default to local/loopback integrations. Remote endpoints require explicit security review and user configuration.

## High-value production-studio references

| Project | Repository | License signal | Useful ideas | StoryForge decision |
|---|---|---|---|---|
| Drama Studio | [jeffreycayao/Drama-Studio](https://github.com/jeffreycayao/Drama-Studio) | GPL-3.0-only | Integrated AI video workstation, ComfyUI bridge, editable timeline, captions/audio/effects, preview-first agent edits and undo | Study product workflows and interaction design only. Do not copy GPL code into the current codebase without an explicit licensing decision. |
| OpenField | [wexloops/openfield](https://github.com/wexloops/openfield) | MIT for its code; model and node licenses are separate | ComfyUI workflow apps, director controls, scene-to-shot planning, start/end frame workflows, media finishing and quality checks | High-priority reference for workflow manifests, model/license registry, shot finishing and measurable media QA. Prototype through existing engine adapters; do not import its app shell. |
| OpenKatana | [rk0neki/OpenKatana](https://github.com/rk0neki/OpenKatana) | Apache-2.0 distribution; retained MIT notices and third-party notices also apply | Strict timeline contracts, revision-aware agent operations, preview/apply editing, code-driven effects, FFmpeg export | High-priority reference for timeline validation, agent action contracts and deterministic editing. Review all bundled third-party components before reuse. |
| ComfyUI-Spool | [doubletwisted/ComfyUI-Spool](https://github.com/doubletwisted/ComfyUI-Spool) | GPL-3.0 | Per-shot workflow inputs, multiple takes, side-by-side review, use-take selection, timeline assembly and OTIO export | Study the take-review UX and workflow portability. Do not import its GPL implementation into StoryForge absent a licensing decision. |
| Velorn | [VelornLabs/velorn](https://github.com/VelornLabs/velorn) | Verify exact revision and retained notices before reuse | Local AI video workstation, timeline and MCP-driven production tools | Secondary product reference; compare against Drama Studio/OpenKatana and avoid duplicate research. |
| StoryBored | [storybored-app/storybored](https://github.com/storybored-app/storybored) | MIT reported at repository level; inspect file/dependency notices | Story → scene → shot → take model, workflow packs, reviewable generation, animatic pipeline | Existing architectural reference. Reuse concepts, not its queue, database, or app shell. |
| CineMatrix | [kirklasalle/CineMatrix](https://github.com/kirklasalle/CineMatrix) | MIT reported at repository level; inspect exact files | Screenplay parsing, previsualization, character library, shot metadata | Reference for screenplay ingestion and coverage; validate implementation maturity before code reuse. |
| Panelwise | [Katlego-tech/Panelwise](https://github.com/Katlego-tech/Panelwise) | Apache-2.0 reported at repository level | Evidence-grounded entities, frame audit, rerender rationale and contracts | Adopt traceability and audit principles; vision-based auditing remains a separately gated module. |
| OpenFrame | [kazim-45/openframe](https://github.com/kazim-45/openframe) | MIT reported at repository level | Shot-size templates and panel-based camera metadata | Recreate useful templates in the existing React design system; no separate app or persistence layer. |
| Abekyo Editor | [abekyo/abekyo-editor](https://github.com/abekyo/abekyo-editor) | MIT reported at repository level | JSON-native edit contracts, deterministic validation, timeline/media validation | Reference only for timeline contracts. Do not add a second Next.js/Remotion runtime by default. |

## Foundational engines and interchange standards

| Project | Repository | License / caveat | StoryForge use |
|---|---|---|---|
| ComfyUI | [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI) | GPL-3.0; integration is by API, not copied code | Local image/video/audio generation behind versioned workflow packs and a hardened adapter. |
| OpenTimelineIO | [AcademySoftwareFoundation/OpenTimelineIO](https://github.com/AcademySoftwareFoundation/OpenTimelineIO) | Apache-2.0 | Canonical interchange boundary for clips, tracks, gaps, transitions, time ranges and metadata. Keep StoryForge's own domain model authoritative. |
| FFmpeg | [FFmpeg/FFmpeg](https://github.com/FFmpeg/FFmpeg) | LGPL by default; optional components/build configurations may be GPL | Sandboxed subprocess renderer/transcoder with argument arrays, bounded timeout/output, cancellation and explicit build provenance. |
| Blender | [blender/blender](https://github.com/blender/blender) | GPL-3.0 | Optional external 3D creation/render adapter; do not embed its code in the proprietary core. |
| Kdenlive | [KDE/kdenlive](https://github.com/KDE/kdenlive) | GPL-3.0 | Study mature editing concepts and MLT integration; no code import into the core without licensing review. |
| Whisper | [openai/whisper](https://github.com/openai/whisper) | MIT | Optional local transcription adapter; preserve timestamps, language, confidence and source provenance. |
| WhisperX | [m-bain/whisperX](https://github.com/m-bain/whisperX) | Verify exact revision/dependencies | Reference for word-level alignment and diarization; optional adapter after privacy/model review. |
| SAM 2 | [facebookresearch/sam2](https://github.com/facebookresearch/sam2) | Apache-2.0 code; model assets and downstream dependencies need separate review | Optional segmentation/masking adapter for VFX and image/video editing. |
| Real-ESRGAN | [xinntao/Real-ESRGAN](https://github.com/xinntao/Real-ESRGAN) | BSD-3-Clause code; weights have separate terms | Optional image restoration/upscaling adapter with model provenance. |

## Adoption priorities

| Priority | Capability | Reference pattern | StoryForge implementation boundary |
|---|---|---|---|
| P0 | Workflow registry and compatibility | OpenField, ComfyUI, Spool | Versioned manifest, declared inputs/outputs, model/node requirements and capability checks; no arbitrary browser-supplied graph. |
| P0 | Take review and approval | StoryBored, Spool, Drama Studio | Existing StoryboardTake lifecycle remains authoritative; compare previews and bind approval to exact asset hash/version. |
| P0 | Timeline contract and interchange | OpenTimelineIO, OpenKatana | Strictly validated JSON domain snapshot + OTIO import/export; retain current Task Manager and Asset storage. |
| P1 | Agent-assisted editing | OpenKatana, Drama Studio | Preview-first typed operations, explicit approval for writes, optimistic revision checks and undo/audit history. |
| P1 | Media QA | OpenField | Deterministic checks first: duration, frame rate, resolution, black/frozen frames, audio peaks, missing media and transition seams. Vision QA later and reviewable. |
| P1 | Captions and transcription | Whisper, WhisperX | Local-first adapter with word/segment timing, speaker labels only when supported, source media hash and human correction. |
| P2 | VFX and 3D | Blender, SAM 2, Real-ESRGAN | Optional external engines behind adapters; keep intermediate assets and provenance in the existing Asset library. |
| P2 | Audio and sound design | Drama Studio/OpenKatana product patterns + dedicated audio engines | Multi-track timeline, voice, ambience, SFX and music as separate tracks; licensing and rights metadata required. |

## Standard adoption gate for every future dependency

- **Identity:** exact repository URL, owner, reviewed commit/tag, release health and maintenance activity.
- **License:** repository license, file headers, dependencies, models/weights, custom nodes, fonts, sample media, notices and trademark constraints.
- **Security:** install scripts, network behavior, file-system access, subprocess execution, deserialization, telemetry and secret handling.
- **Fit:** adapter boundary, Windows support, offline/local behavior, Python/Node compatibility, GPU requirements and resource limits.
- **Evidence:** minimal isolated prototype, reproducible build, focused tests, failure behavior and rollback path.
- **Decision:** adopt as dependency, integrate as external engine, adapt protocol/design only, defer, or reject—with rationale recorded here.

## Current implementation status

- Storyboard shot/take foundation, ComfyUI image/video adapters, approved-take-only silent animatic renderer and OpenTimelineIO export already exist on the active implementation branch.
- This catalog does not claim that the references above have been integrated or that the current animatic is a full nonlinear editor.
- Audio tracks, captions/transcription, multi-track editing, VFX, native desktop shell, publishing and analytics remain separate future vertical slices.
- Automated verification is intentionally deferred to the dedicated test stage requested for this implementation sequence.
