from fastapi import APIRouter, Depends, File, Header, Query, UploadFile, HTTPException
from sqlalchemy.orm import Session
from .database import get_db, engine
from .storage import STORAGE_ROOT
from .backup import BackupError, create_backup, verify_backup
from .projects import create_project, get_project, list_projects, serialize, set_archived, update_project
from .schemas import ProjectCreate, ProjectPage, ProjectRead, ProjectUpdate
from .storage import detach_project_asset, ingest_upload, list_project_assets
from .ai_gateway import create_provider, list_providers, delete_provider, update_provider, generate_chat_completion, list_model_capabilities, update_model_capability, test_provider_connection, set_model_pricing, get_usage_summary, list_model_pricing_history
from .gateway_schemas import ProviderCreate, ProviderRead, ProviderUpdate, ChatCompletionRequest, ChatCompletionRead, ModelCapabilityUpdate, ModelPricingUpdate
from .task_manager import create_task, get_task, list_tasks, cancel_task, retry_task, approve_task, reject_task_approval
from .task_schemas import TaskCreate, TaskRead
from .orchestrator import (list_workflows, create_production_run, get_production_run, list_production_runs, pause_production_run, resume_production_run, cancel_production_run)
from .orchestrator_schemas import ProductionRunCreate
from .agent_manager import create_agent, get_agent, list_agents, update_agent, replace_agent_tools, enable_agent, disable_agent
from .agent_runtime import run_agent
from .agent_schemas import AgentCreate, AgentUpdate, AgentToolsUpdate, AgentRunRequest
from .research_search import search_research
from .document_ingestion import extract_document
from .research_vault import (
    create_source, get_source, list_sources, link_source_to_project,
    detach_source_from_project, create_evidence, list_evidence,
    create_claim, list_claims, get_claim, link_evidence_to_claim, update_claim,
)
from .story_engine import create_story, list_stories, get_story, update_story, create_scene, update_scene, delete_scene, reorder_scenes
from .story_schemas import StoryCreate, StoryUpdate, StorySceneCreate, StorySceneUpdate, StorySceneReorder
from .research_schemas import (
    ResearchSourceCreate, ResearchEvidenceCreate, ResearchClaimCreate,
    ResearchClaimEvidenceCreate, ResearchClaimUpdate,
)

router = APIRouter(prefix="/api/v1", tags=["studio"])

@router.post("/projects", response_model=ProjectRead, status_code=201)
def post_project(payload: ProjectCreate, db: Session = Depends(get_db)):
    return serialize(create_project(db, payload))

@router.get("/projects", response_model=ProjectPage)
def get_projects(limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0),
                 include_archived: bool = False, db: Session = Depends(get_db)):
    items, total = list_projects(db, limit, offset, include_archived)
    return {"items": [serialize(item) for item in items], "total": total, "limit": limit, "offset": offset}

@router.get("/projects/{project_id}", response_model=ProjectRead)
def get_project_route(project_id: str, db: Session = Depends(get_db)):
    return serialize(get_project(db, project_id))

@router.patch("/projects/{project_id}", response_model=ProjectRead)
def patch_project(project_id: str, payload: ProjectUpdate, db: Session = Depends(get_db)):
    return serialize(update_project(db, project_id, payload))

@router.post("/projects/{project_id}/archive", response_model=ProjectRead)
def archive_project(project_id: str, db: Session = Depends(get_db)):
    return serialize(set_archived(db, project_id, True))

@router.post("/projects/{project_id}/restore", response_model=ProjectRead)
def restore_project(project_id: str, db: Session = Depends(get_db)):
    return serialize(set_archived(db, project_id, False))

@router.post("/projects/{project_id}/assets", status_code=201)
async def upload_project_asset(project_id: str, file: UploadFile = File(...), db: Session = Depends(get_db)):
    asset, link = await ingest_upload(db, project_id, file)
    return {"id": link.id, "asset_id": asset.id, "sha256": asset.sha256,
            "size_bytes": asset.size_bytes, "mime_type": asset.mime_type,
            "filename": link.original_filename, "created_at": link.created_at}

@router.get("/projects/{project_id}/assets")
def get_project_assets(project_id: str, db: Session = Depends(get_db)):
    return list_project_assets(db, project_id)

@router.delete("/projects/{project_id}/assets/{link_id}", status_code=204)
def delete_project_asset(project_id: str, link_id: str, db: Session = Depends(get_db)):
    detach_project_asset(db, project_id, link_id)


@router.post("/ai/providers", response_model=ProviderRead, status_code=201)
def post_ai_provider(payload: ProviderCreate, db: Session = Depends(get_db)):
    return create_provider(db, payload)


@router.get("/ai/providers", response_model=list[ProviderRead])
def get_ai_providers(db: Session = Depends(get_db)):
    return list_providers(db)


@router.delete("/ai/providers/{provider_id}", status_code=204)
def remove_ai_provider(provider_id: str, db: Session = Depends(get_db)):
    delete_provider(db, provider_id)


@router.post("/ai/chat/completions", response_model=ChatCompletionRead)
async def post_ai_chat_completion(
    payload: ChatCompletionRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=200),
    db: Session = Depends(get_db),
):
    return await generate_chat_completion(db, payload, idempotency_key)


@router.get("/ai/models")
def get_ai_models(db: Session = Depends(get_db)):
    return list_model_capabilities(db)


@router.patch("/ai/providers/{provider_id}/models/{model_id}")
def patch_ai_model_capability(
    provider_id: str,
    model_id: str,
    payload: ModelCapabilityUpdate,
    db: Session = Depends(get_db),
):
    return update_model_capability(db, provider_id, model_id, payload)


@router.post("/ai/providers/{provider_id}/test")
async def post_ai_provider_test(provider_id: str, db: Session = Depends(get_db)):
    return await test_provider_connection(db, provider_id)


@router.put("/ai/providers/{provider_id}/models/{model_id}/pricing")
def put_ai_model_pricing(
    provider_id: str,
    model_id: str,
    payload: ModelPricingUpdate,
    db: Session = Depends(get_db),
):
    return set_model_pricing(db, provider_id, model_id, payload)


@router.get("/ai/usage/summary")
def get_ai_usage_summary(db: Session = Depends(get_db)):
    return get_usage_summary(db)


@router.get("/ai/providers/{provider_id}/models/{model_id}/pricing/history")
def get_ai_model_pricing_history(provider_id: str, model_id: str, db: Session = Depends(get_db)):
    return list_model_pricing_history(db, provider_id, model_id)


@router.patch("/ai/providers/{provider_id}", response_model=ProviderRead)
def patch_ai_provider(provider_id: str, payload: ProviderUpdate, db: Session = Depends(get_db)):
    return update_provider(db, provider_id, payload)


@router.post("/tasks", status_code=201)
def post_task(
    payload: TaskCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=200),
    db: Session = Depends(get_db),
):
    return create_task(
        db, task_type=payload.task_type, payload=payload.payload,
        idempotency_key=idempotency_key, project_id=payload.project_id,
        priority=payload.priority, dependencies=payload.depends_on,
        max_attempts=payload.max_attempts,
    )


@router.get("/tasks")
def get_tasks(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, min_length=1, max_length=24),
    project_id: str | None = Query(None, min_length=36, max_length=36),
    db: Session = Depends(get_db),
):
    return list_tasks(db, limit=limit, offset=offset, status=status, project_id=project_id)


@router.get("/tasks/{task_id}")
def get_task_route(task_id: str, db: Session = Depends(get_db)):
    return get_task(db, task_id)


@router.post("/tasks/{task_id}/cancel")
def post_task_cancel(task_id: str, db: Session = Depends(get_db)):
    return cancel_task(db, task_id)


@router.post("/tasks/{task_id}/retry")
def post_task_retry(task_id: str, db: Session = Depends(get_db)):
    return retry_task(db, task_id)


@router.post("/tasks/{task_id}/approve")
def post_task_approval(task_id: str, db: Session = Depends(get_db)):
    return approve_task(db, task_id)


@router.post("/tasks/{task_id}/reject")
def post_task_rejection(task_id: str, reason: str = Query("Human approval rejected", max_length=500),
                        db: Session = Depends(get_db)):
    return reject_task_approval(db, task_id, reason)


@router.get("/production/workflows")
def get_production_workflows():
    return list_workflows()


@router.post("/production/runs", status_code=201)
def post_production_run(
    payload: ProductionRunCreate,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=200),
    db: Session = Depends(get_db),
):
    return create_production_run(
        db, workflow_key=payload.workflow_key, inputs=payload.inputs,
        idempotency_key=idempotency_key, project_id=payload.project_id,
    )


@router.get("/production/runs")
def get_production_runs(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    project_id: str | None = Query(None, min_length=36, max_length=36),
    db: Session = Depends(get_db),
):
    return list_production_runs(db, limit=limit, offset=offset, project_id=project_id)


@router.get("/production/runs/{run_id}")
def get_production_run_route(run_id: str, db: Session = Depends(get_db)):
    return get_production_run(db, run_id)



@router.post("/production/runs/{run_id}/pause")
def post_production_run_pause(run_id: str, db: Session = Depends(get_db)):
    return pause_production_run(db, run_id)


@router.post("/production/runs/{run_id}/resume")
def post_production_run_resume(run_id: str, db: Session = Depends(get_db)):
    return resume_production_run(db, run_id)


@router.post("/production/runs/{run_id}/cancel")
def post_production_run_cancel(run_id: str, db: Session = Depends(get_db)):
    return cancel_production_run(db, run_id)




# Read-only local system diagnostics. Never returns credential material or provider secrets.
def _directory_usage(root):
    from pathlib import Path
    total = files = 0
    if not root.exists():
        return {"bytes": 0, "files": 0}
    if root.is_symlink():
        raise HTTPException(409, detail={"code": "unsafe_storage_root"})
    for current, directories, filenames in __import__("os").walk(root, followlinks=False):
        base = Path(current)
        directories[:] = [name for name in directories if not (base / name).is_symlink()]
        for name in filenames:
            item = base / name
            if item.is_symlink():
                continue
            try:
                if item.is_file():
                    total += item.stat().st_size
                    files += 1
            except OSError:
                continue
    return {"bytes": total, "files": files}


@router.get("/settings/system")
def get_system_settings():
    import os
    import shutil
    from pathlib import Path
    database_name = engine.url.database
    if not database_name or database_name == ":memory:":
        database_path = None
        data_root = Path.cwd() / "data"
    else:
        database_path = Path(database_name).expanduser().resolve()
        data_root = database_path.parent
    storage_root = Path(STORAGE_ROOT).expanduser().resolve()
    backup_root = (data_root / "backups").resolve()
    try:
        disk = shutil.disk_usage(data_root if data_root.exists() else data_root.parent)
        disk_info = {"total_bytes": disk.total, "used_bytes": disk.used, "free_bytes": disk.free}
    except OSError:
        disk_info = {"total_bytes": None, "used_bytes": None, "free_bytes": None}
    database_bytes = 0
    if database_path is not None:
        for suffix in ("", "-wal", "-shm"):
            candidate = Path(str(database_path) + suffix)
            try:
                if candidate.is_file() and not candidate.is_symlink():
                    database_bytes += candidate.stat().st_size
            except OSError:
                pass
    key_file = data_root / "credential-key.dpapi"
    return {
        "app_data_root": str(data_root),
        "database_path": str(database_path) if database_path else None,
        "database_bytes": database_bytes,
        "storage_path": str(storage_root),
        "storage": _directory_usage(storage_root),
        "backup_path": str(backup_root),
        "backup_count": sum(1 for item in backup_root.glob("masoud-studio-*.zip") if item.is_file() and not item.is_symlink()) if backup_root.exists() else 0,
        "disk": disk_info,
        "max_upload_bytes": int(os.getenv("MASOUD_STUDIO_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024))),
        "desktop_mode": os.getenv("MASOUD_STUDIO_DESKTOP_MODE", "").lower() == "true",
        "credential_key_present": key_file.is_file() and not key_file.is_symlink(),
        "network_policy": "loopback-only in packaged desktop mode; no authentication for local process access",
    }



def _settings_file():
    from pathlib import Path
    database_name = engine.url.database
    if not database_name or database_name == ":memory:":
        raise HTTPException(409, detail={"code": "settings_require_file_database"})
    return Path(database_name).expanduser().resolve().parent / "studio-settings.json"


def _read_preferences():
    import json
    path = _settings_file()
    defaults = {"backup_retention_count": 20}
    if not path.exists():
        return defaults
    if path.is_symlink() or path.stat().st_size > 16384:
        raise HTTPException(409, detail={"code": "settings_file_unsafe"})
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        count = raw.get("backup_retention_count", 20)
        if isinstance(count, bool) or not isinstance(count, int) or not 3 <= count <= 100:
            raise ValueError("Invalid backup retention setting")
        return {"backup_retention_count": count}
    except (OSError, ValueError, TypeError):
        raise HTTPException(409, detail={"code": "settings_file_invalid"})


@router.get("/settings/preferences")
def get_settings_preferences():
    return _read_preferences()


@router.put("/settings/preferences")
def put_settings_preferences(payload: dict):
    import json
    import os
    if set(payload) != {"backup_retention_count"}:
        raise HTTPException(422, detail={"code": "unsupported_settings_fields"})
    count = payload.get("backup_retention_count")
    if isinstance(count, bool) or not isinstance(count, int) or not 3 <= count <= 100:
        raise HTTPException(422, detail={"code": "invalid_backup_retention", "minimum": 3, "maximum": 100})
    path = _settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    try:
        with temp.open("w", encoding="utf-8") as stream:
            json.dump({"backup_retention_count": count}, stream, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    return {"backup_retention_count": count}


# Local backup management. Restore is deliberately offline-only.
def _backup_locations():
    database_name = engine.url.database
    if not database_name or database_name == ":memory:":
        raise HTTPException(409, detail={"code": "backup_requires_file_database"})
    database_path = __import__("pathlib").Path(database_name).expanduser().resolve()
    backup_dir = database_path.parent / "backups"
    return database_path, backup_dir


@router.post("/backups", status_code=201)
def post_backup():
    database_path, backup_dir = _backup_locations()
    try:
        result = create_backup(database_path, STORAGE_ROOT, backup_dir)
        # Only prune older archives after the newly-created archive passes full verification.
        verification = verify_backup(__import__("pathlib").Path(result["path"]))
        if not verification.get("valid"):
            raise BackupError("New backup did not pass integrity verification.")
        retention = _read_preferences()["backup_retention_count"]
        archives = sorted(
            (item for item in backup_dir.glob("masoud-studio-*.zip")
             if item.is_file() and not item.is_symlink()),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
        for obsolete in archives[retention:]:
            obsolete.unlink()
        result["retained_backups"] = min(len(archives), retention)
        return result
    except BackupError as exc:
        raise HTTPException(409, detail={"code": "backup_failed", "message": str(exc)})


@router.get("/backups")
def get_backups():
    _database_path, backup_dir = _backup_locations()
    if not backup_dir.exists():
        return []
    return [
        {"id": item.name, "size_bytes": item.stat().st_size, "modified_at": item.stat().st_mtime}
        for item in sorted(backup_dir.glob("masoud-studio-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)
        if item.is_file() and not item.is_symlink()
    ]


@router.post("/backups/{backup_id}/verify")
def post_backup_verify(backup_id: str):
    from pathlib import Path
    if not backup_id.startswith("masoud-studio-") or not backup_id.endswith(".zip") or Path(backup_id).name != backup_id:
        raise HTTPException(400, detail={"code": "invalid_backup_id"})
    _database_path, backup_dir = _backup_locations()
    target = (backup_dir / backup_id).resolve()
    if target.parent != backup_dir.resolve() or not target.is_file():
        raise HTTPException(404, detail={"code": "backup_not_found"})
    try:
        return verify_backup(target)
    except BackupError as exc:
        raise HTTPException(422, detail={"code": "backup_invalid", "message": str(exc)})


# Research Vault: manually curated source provenance, evidence and project claims.

@router.get("/research/search")
def get_research_search(
    q: str = Query(..., min_length=2, max_length=200),
    project_id: str | None = Query(None, min_length=36, max_length=36),
    limit: int = Query(25, ge=1, le=100),
    db: Session = Depends(get_db),
):
    return search_research(db, q, project_id=project_id, limit=limit)

@router.post("/research/sources/{source_id}/extract")
def post_research_document_extract(source_id: str, db: Session = Depends(get_db)):
    return extract_document(db, source_id)


@router.post("/research/sources", status_code=201)
def post_research_source(payload: ResearchSourceCreate, db: Session = Depends(get_db)):
    return create_source(db, payload)


@router.get("/research/sources")
def get_research_sources(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    project_id: str | None = Query(None, min_length=36, max_length=36),
    db: Session = Depends(get_db),
):
    return list_sources(db, limit=limit, offset=offset, project_id=project_id)


@router.get("/research/sources/{source_id}")
def get_research_source(source_id: str, db: Session = Depends(get_db)):
    return get_source(db, source_id)


@router.post("/research/sources/{source_id}/projects/{project_id}")
def post_research_source_project(
    source_id: str, project_id: str,
    notes: str | None = Query(None, max_length=5000),
    db: Session = Depends(get_db),
):
    return link_source_to_project(db, source_id, project_id, notes)


@router.delete("/research/sources/{source_id}/projects/{project_id}", status_code=204)
def delete_research_source_project(source_id: str, project_id: str, db: Session = Depends(get_db)):
    detach_source_from_project(db, source_id, project_id)


@router.post("/research/sources/{source_id}/evidence", status_code=201)
def post_research_evidence(
    source_id: str, payload: ResearchEvidenceCreate, db: Session = Depends(get_db)
):
    return create_evidence(db, source_id, payload)


@router.get("/research/sources/{source_id}/evidence")
def get_research_evidence(
    source_id: str,
    limit: int = Query(100, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return list_evidence(db, source_id, limit=limit, offset=offset)


@router.post("/research/claims", status_code=201)
def post_research_claim(payload: ResearchClaimCreate, db: Session = Depends(get_db)):
    return create_claim(db, payload)


@router.get("/research/claims")
def get_research_claims(
    project_id: str = Query(..., min_length=36, max_length=36),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    return list_claims(db, project_id, limit=limit, offset=offset)


@router.get("/research/claims/{claim_id}")
def get_research_claim(claim_id: str, db: Session = Depends(get_db)):
    return get_claim(db, claim_id)


@router.patch("/research/claims/{claim_id}")
def patch_research_claim(
    claim_id: str, payload: ResearchClaimUpdate, db: Session = Depends(get_db)
):
    return update_claim(db, claim_id, payload)


@router.post("/research/claims/{claim_id}/evidence/{evidence_id}")
def post_research_claim_evidence(
    claim_id: str, evidence_id: str,
    payload: ResearchClaimEvidenceCreate,
    db: Session = Depends(get_db),
):
    return link_evidence_to_claim(db, claim_id, evidence_id, payload.relationship, payload.note)


@router.post("/agents", status_code=201)
def post_agent(payload: AgentCreate, db: Session = Depends(get_db)):
    return create_agent(db, payload)


@router.get("/agents")
def get_agents(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    status: str | None = Query(None, pattern="^(draft|enabled|disabled)$"),
    db: Session = Depends(get_db),
):
    return list_agents(db, limit=limit, offset=offset, status=status)


@router.get("/agents/{agent_id}")
def get_agent_route(agent_id: str, db: Session = Depends(get_db)):
    return get_agent(db, agent_id)


@router.patch("/agents/{agent_id}")
def patch_agent(agent_id: str, payload: AgentUpdate, db: Session = Depends(get_db)):
    return update_agent(db, agent_id, payload)


@router.put("/agents/{agent_id}/tools")
def put_agent_tools(agent_id: str, payload: AgentToolsUpdate, db: Session = Depends(get_db)):
    return replace_agent_tools(db, agent_id, payload)


@router.post("/agents/{agent_id}/enable")
def post_agent_enable(agent_id: str, db: Session = Depends(get_db)):
    return enable_agent(db, agent_id)


@router.post("/agents/{agent_id}/disable")
def post_agent_disable(agent_id: str, db: Session = Depends(get_db)):
    return disable_agent(db, agent_id)


@router.post("/agents/{agent_id}/run")
async def post_agent_run(
    agent_id: str,
    payload: AgentRunRequest,
    idempotency_key: str = Header(..., alias="Idempotency-Key", min_length=8, max_length=180),
    db: Session = Depends(get_db),
):
    return await run_agent(db, agent_id, payload.message, idempotency_key)


# Story Engine: versioned story dossiers and ordered scene development.
@router.post("/stories", status_code=201)
def post_story(payload: StoryCreate, db: Session = Depends(get_db)):
    return create_story(db, payload)

@router.get("/stories")
def get_stories(project_id: str | None = Query(None, min_length=36, max_length=36), limit: int = Query(50, ge=1, le=200), offset: int = Query(0, ge=0), db: Session = Depends(get_db)):
    return list_stories(db, project_id=project_id, limit=limit, offset=offset)

@router.get("/stories/{story_id}")
def get_story_route(story_id: str, db: Session = Depends(get_db)):
    return get_story(db, story_id)

@router.patch("/stories/{story_id}")
def patch_story(story_id: str, payload: StoryUpdate, db: Session = Depends(get_db)):
    return update_story(db, story_id, payload)

@router.post("/stories/{story_id}/scenes", status_code=201)
def post_story_scene(story_id: str, payload: StorySceneCreate, db: Session = Depends(get_db)):
    return create_scene(db, story_id, payload)

@router.patch("/stories/{story_id}/scenes/{scene_id}")
def patch_story_scene(story_id: str, scene_id: str, payload: StorySceneUpdate, db: Session = Depends(get_db)):
    return update_scene(db, story_id, scene_id, payload)

@router.delete("/stories/{story_id}/scenes/{scene_id}")
def delete_story_scene(story_id: str, scene_id: str, db: Session = Depends(get_db)):
    return delete_scene(db, story_id, scene_id)


@router.post("/stories/{story_id}/scenes/reorder")
def post_story_scene_reorder(story_id: str, payload: StorySceneReorder, db: Session = Depends(get_db)):
    return reorder_scenes(db, story_id, payload.expected_story_version, payload.scene_ids)
