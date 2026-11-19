from fastapi import APIRouter, Depends, File, Header, Query, UploadFile
from sqlalchemy.orm import Session
from .database import get_db
from .projects import create_project, get_project, list_projects, serialize, set_archived, update_project
from .schemas import ProjectCreate, ProjectPage, ProjectRead, ProjectUpdate
from .storage import detach_project_asset, ingest_upload, list_project_assets
from .ai_gateway import create_provider, list_providers, delete_provider, update_provider, generate_chat_completion, list_model_capabilities, update_model_capability, test_provider_connection, set_model_pricing, get_usage_summary, list_model_pricing_history
from .gateway_schemas import ProviderCreate, ProviderRead, ProviderUpdate, ChatCompletionRequest, ChatCompletionRead, ModelCapabilityUpdate, ModelPricingUpdate
from .task_manager import create_task, get_task, list_tasks, cancel_task, retry_task, approve_task, reject_task_approval
from .task_schemas import TaskCreate, TaskRead
from .orchestrator import (list_workflows, create_production_run, get_production_run, list_production_runs, pause_production_run, resume_production_run, cancel_production_run)
from .orchestrator_schemas import ProductionRunCreate
from .agent_manager import create_agent, get_agent, list_agents, update_agent, replace_agent_tools, enable_agent, disable_agent\nfrom .agent_runtime import run_agent
from .agent_schemas import AgentCreate, AgentUpdate, AgentToolsUpdate, AgentRunRequest

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
