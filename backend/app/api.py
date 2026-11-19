from fastapi import APIRouter, Depends, File, Header, Query, UploadFile
from sqlalchemy.orm import Session
from .database import get_db
from .projects import create_project, get_project, list_projects, serialize, set_archived, update_project
from .schemas import ProjectCreate, ProjectPage, ProjectRead, ProjectUpdate
from .storage import detach_project_asset, ingest_upload, list_project_assets
from .ai_gateway import create_provider, list_providers, delete_provider, generate_chat_completion
from .gateway_schemas import ProviderCreate, ProviderRead, ChatCompletionRequest, ChatCompletionRead

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
