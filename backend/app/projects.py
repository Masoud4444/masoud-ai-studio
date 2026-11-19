import json
import re
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .models import Project
from .schemas import ProjectCreate, ProjectUpdate

def make_slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug[:160] or f"project-{uuid4().hex[:10]}"

def serialize(project: Project) -> dict:
    return {
        "id": project.id, "slug": project.slug, "name": project.name,
        "description": project.description, "project_type": project.project_type,
        "status": project.status, "settings": json.loads(project.settings_json),
        "metadata": json.loads(project.metadata_json), "created_at": project.created_at,
        "updated_at": project.updated_at, "archived_at": project.archived_at,
        "version": project.version,
    }

def create_project(db: Session, payload: ProjectCreate) -> Project:
    project = Project(
        slug=make_slug(payload.slug or payload.name), name=payload.name.strip(),
        description=payload.description, project_type=payload.project_type,
        settings_json=json.dumps(payload.settings), metadata_json=json.dumps(payload.metadata),
    )
    db.add(project)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail={"code": "slug_conflict", "message": "Project slug already exists"})
    db.refresh(project)
    return project

def list_projects(db: Session, limit: int = 50, offset: int = 0, include_archived: bool = False):
    query = select(Project)
    count_query = select(func.count()).select_from(Project)
    if not include_archived:
        query = query.where(Project.status == "active")
        count_query = count_query.where(Project.status == "active")
    total = db.scalar(count_query) or 0
    items = db.scalars(query.order_by(Project.created_at.desc()).limit(limit).offset(offset)).all()
    return items, total

def get_project(db: Session, project_id: str) -> Project:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=404, detail={"code": "project_not_found"})
    return project

def update_project(db: Session, project_id: str, payload: ProjectUpdate) -> Project:
    project = get_project(db, project_id)
    if project.status != "active":
        raise HTTPException(status_code=409, detail={"code": "project_archived"})
    if project.version != payload.expected_version:
        raise HTTPException(status_code=409, detail={"code": "version_conflict", "current_version": project.version})
    for key, value in payload.model_dump(exclude={"expected_version"}, exclude_unset=True).items():
        if key == "settings":
            project.settings_json = json.dumps(value)
        elif key == "metadata":
            project.metadata_json = json.dumps(value)
        elif key == "name" and value is not None:
            project.name = value.strip()
        else:
            setattr(project, key, value)
    project.version += 1
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return project

def set_archived(db: Session, project_id: str, archived: bool) -> Project:
    project = get_project(db, project_id)
    if archived and project.status == "active":
        project.status, project.archived_at = "archived", datetime.now(timezone.utc)
    elif not archived and project.status == "archived":
        project.status, project.archived_at = "active", None
    project.version += 1
    project.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(project)
    return project
