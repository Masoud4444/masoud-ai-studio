from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from .database import get_db
from .projects import create_project, get_project, list_projects, serialize, set_archived, update_project
from .schemas import ProjectCreate, ProjectPage, ProjectRead, ProjectUpdate

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
