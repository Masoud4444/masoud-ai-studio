# Masoud AI Studio

A public-code, private-by-design, local-first AI creative production studio for research, story development, visual design, image/video/audio production, editing, quality review and publishing workflows.

## Product principles

- **Full Vision, Simplified Architecture, Incremental Implementation**
- Windows desktop is the primary platform; Android and Web/PWA are companion clients.
- Local-first and offline-first by default; cloud-ready without requiring distributed infrastructure.
- Modular monolith: one backend, one primary database, one storage layer, one AI Gateway, one Agent Manager, one Production Orchestrator and a central Task Manager.
- Human approval for consequential creative and publishing decisions.
- Preserve provenance, version history, continuity, privacy, recoverability and cost visibility.
- Private owner-operated studio, not a multi-tenant SaaS.

## Repository

- Public source repository: Masoud4444/masoud-ai-studio.
- Active implementation branch: implementation/bootstrap-001.
- main is intentionally untouched; no merge has been performed.
- Studio data, credentials and generated assets are intended to remain local/private. Do not commit secrets or personal project data.

## Current implementation

### Backend
- FastAPI, SQLAlchemy 2, SQLite and Alembic migrations through 0020.
- Project lifecycle API with optimistic version checks.
- Content-addressed local storage and project asset linking.
- AI Provider registry, encrypted credentials, SSRF-aware URL validation and OpenAI-compatible non-streaming gateway.
- Model registry, usage ledger, manually configured pricing and cost estimates.
- Central Task Manager with dependencies, idempotency, leases, retries and append-only events.
- Production Orchestrator with preproduction workflow, approval gates and run pause/resume/cancel.
- Worker Supervisor with handler allowlist, lease heartbeat, bounded JSON results and sanitized failures; disabled by default.
- Agent Manager with lifecycle governance, tool grants and budget reservation ledger; first text-only Agent Runtime uses explicit AI-generation permission, configured pricing, conservative budget reservation and Gateway idempotency. Tool Broker, tool execution and process sandbox are not implemented.
- Research Vault with project-scoped sources, exact evidence excerpts/locators, claims, provenance, search and bounded local PDF/DOCX text extraction.
- Story Engine with story dossiers, ordered scene outlines and immutable revision history.
- Character and World Bible with relationships, locations, rules and scene links.
- Story prop registry with stable object identity and continuity references.
- Deterministic continuity facts and issue analysis with human review controls.

### Frontend
- React, TypeScript, Vite and responsive dark studio shell.
- Overview, Projects, Production, AI Agents and Assets workspaces.
- Research Vault workspace with source/evidence/claim management, search and document extraction.
- Story Engine workspace for story dossiers, scenes and revision history.
- Storyboard workspace for screenplay-linked shots, reviewed image takes and FFmpeg-based animatic rendering with OpenTimelineIO interchange.
- Characters & Worlds workspace for character/location/world data and continuity review; registered props can be created, edited and linked into continuity facts.
- Timeline workspace for in-world events, explicit chronology constraints and cycle analysis.
- Video & Audio, Compliance and some Settings capabilities remain staged; no incomplete module is represented as production-ready.

### Local Windows launch
- scripts/setup-windows.bat installs dependencies, builds the frontend and applies database migrations.
- scripts/start-studio-windows.bat starts the local FastAPI service, serves the compiled React app from the same process and opens the studio in the default browser.
- The normal local workflow uses http://127.0.0.1:8000; development mode remains available through http://127.0.0.1:5173.
- This is a one-click local browser launch workflow, not yet a signed native Windows desktop installer. Tauri packaging, code signing and native update delivery remain outstanding.

## Windows quick start

Requirements: Windows 10/11, Python 3.11+ and Node.js 20+.

1. Clone the repository and switch to implementation/bootstrap-001.
2. Run scripts\setup-windows.bat once.
3. Run scripts\start-studio-windows.bat.
4. The launcher opens http://127.0.0.1:8000.

Keep the backend console open while using the studio. See the Windows/frontend guide at docs/FRONTEND.md.

## Verification and release status

Existing automated checks were run in prior Linux CI runs for earlier increments. They are historical evidence, not a verification of the latest branch head or of Windows installation. Windows setup, local browser interaction, provider interoperability, desktop packaging and code signing still require hands-on verification. Previously passing tests are not rerun solely for repetition.

## Windows desktop installer

A self-contained Windows x64 installer is now built by GitHub Actions. The packaged launcher embeds the Python backend and compiled frontend, applies database migrations on startup, stores the database and assets under `%LOCALAPPDATA%\\Masoud AI Studio`, protects the credential-encryption key with Windows DPAPI, and provides a system-tray Exit command. The installer is currently unsigned and is a first packaging milestone, not a signed commercial release.

After the `Windows installer` workflow completes, download the `Masoud-AI-Studio-Windows-x64` artifact from [GitHub Actions](https://github.com/Masoud4444/masoud-ai-studio/actions/workflows/windows-installer.yml). See [Windows installation](docs/INSTALLATION.md).

## Development

Backend:

    python -m pip install -r requirements.txt
    alembic upgrade head
    python -m uvicorn backend.app.main:app --host 127.0.0.1 --port 8000

Frontend:

    cd frontend
    npm install
    npm run dev

Build frontend with npm run build.

## Security boundaries

- Authentication and authorization are not implemented. Keep the backend bound to localhost; never expose it to the public internet or an untrusted LAN.
- Do not commit provider API keys, encryption keys, database files, generated assets or personal data.
- No provider API keys are configured by default. No billable provider calls are made by the default setup.
- Worker is disabled by default. When explicitly enabled, only registered local creative handlers (Story outline/scenes, Storyboard prompt/image and approved-take Animatic) are claimable.
- Agent profiles start as drafts. Text-only Agent Runtime requires explicit provider/model/pricing configuration and activation; no tools are executed. Tool Broker, execution sandbox and hard runtime isolation are not complete.
- Windows credential protection via DPAPI/OS keychain, hard worker process isolation, multi-worker coordination, backup/restore verification and independent security review remain required.

## Project documentation

- Local Windows installation: docs/INSTALLATION.md
- Project status and roadmap: docs/PROJECT_STATUS.md
- Architecture: docs/ARCHITECTURE.md
- Frontend and Windows setup: docs/FRONTEND.md
- Task Manager: docs/TASK_MANAGER.md
- Production Orchestrator: docs/PRODUCTION_ORCHESTRATOR.md
- AI Gateway: docs/AI_GATEWAY.md
- Agent Manager: docs/AGENT_MANAGER.md
- Research Vault: docs/RESEARCH_VAULT.md


## Local ComfyUI storyboard image generation (optional)

Storyboard image generation is an optional local adapter. It reuses the central Task Manager, Worker Supervisor, project-scoped content-addressed Asset storage, and the existing human-reviewed Storyboard Take lifecycle. No second queue or asset database is introduced.

1. Install and start ComfyUI separately on the same machine, bound to loopback (default `http://127.0.0.1:8188`).
2. Place a compatible checkpoint in ComfyUI's model directory.
3. Configure these environment values for the backend process:
   - `MASOUD_STUDIO_WORKER_ENABLED=true`
   - `MASOUD_STUDIO_COMFYUI_URL=http://127.0.0.1:8188`
   - `MASOUD_STUDIO_COMFYUI_CHECKPOINT=your-checkpoint-filename.safetensors`
4. Restart the backend. The runtime diagnostics endpoint should report the worker as running and list `storyboard.generate_image` among registered handlers.
5. In Storyboard, create or generate a shot prompt, then choose **Generate image take**. The generated image is stored in the project's asset library as a new unapproved take.

The first adapter version intentionally accepts loopback ComfyUI only. It pins DNS resolution to loopback, disables proxy inheritance and redirects, bounds polling and output size, validates returned image bytes and output locators, and never accepts an arbitrary provider URL or workflow graph from the browser. The versioned workflow pack uses ComfyUI core nodes and requires a compatible checkpoint. Video generation, remote engines, live previews, and custom-node workflow packs remain separate future adapters.


## Approved-take Animatic renderer (optional local engine)

The Animatic renderer reuses the Storyboard, Task Manager, Worker Supervisor and project Asset Library. It renders a silent MP4 from the approved image take for every shot, in scene/shot order, preserving shot durations and supported dissolve/fade/wipe transitions. It also saves an OpenTimelineIO (.otio) interchange document as a second project asset and attaches both outputs to the task.

1. Install FFmpeg on the same machine and make ffmpeg available on PATH, or set MASOUD_STUDIO_FFMPEG_PATH to its executable.
2. Set MASOUD_STUDIO_WORKER_ENABLED=true for the backend process and restart it.
3. Approve one image take for every storyboard shot in the story.
4. In Storyboard, choose the output resolution and select **Build approved animatic**.
5. Refresh the task to see the MP4 preview/download and the .otio timeline export.

The renderer rejects missing, unapproved, stale, cross-project or non-image takes. v1 is picture-only and silent; audio, voice, music, captions and full nonlinear editing are separate planned stages. Output is bounded to 100 MB and 30 minutes, uses a fixed FFmpeg argument list without a shell, and stores both deliverables in the content-addressed project asset store.
