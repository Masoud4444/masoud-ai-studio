import hashlib
import os
import re
import tempfile
from pathlib import Path
from fastapi import HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .models import Asset, Project, ProjectAsset

MAX_UPLOAD_BYTES = int(os.getenv("MASOUD_STUDIO_MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
STORAGE_ROOT = Path(os.getenv("MASOUD_STUDIO_STORAGE_ROOT", "./data/storage")).expanduser()

def safe_filename(value: str) -> str:
    name = Path(value.replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._ -]", "_", name).strip(" .")
    return (name or "upload.bin")[:255]

def detect_mime(header: bytes) -> str:
    signatures = [
        (b"\x89PNG\r\n\x1a\n", "image/png"), (b"\xff\xd8\xff", "image/jpeg"),
        (b"GIF87a", "image/gif"), (b"GIF89a", "image/gif"), (b"%PDF-", "application/pdf"),
        (b"PK\x03\x04", "application/zip"), (b"OggS", "application/ogg"),
        (b"fLaC", "audio/flac"), (b"ID3", "audio/mpeg"), (b"\x1a\x45\xdf\xa3", "video/webm"),
    ]
    for signature, mime in signatures:
        if header.startswith(signature): return mime
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP": return "image/webp"
    if header.startswith(b"RIFF") and header[8:12] == b"WAVE": return "audio/wav"
    if header[4:8] == b"ftyp": return "video/mp4"
    try:
        header.decode("utf-8")
        return "text/plain"
    except UnicodeDecodeError:
        return "application/octet-stream"

def blob_path(sha: str) -> Path:
    root = STORAGE_ROOT.resolve()
    candidate = root / "blobs" / sha[:2] / sha
    if candidate.is_symlink():
        raise HTTPException(status_code=400, detail={"code": "invalid_storage_path"})
    target = candidate.resolve()
    if root not in target.parents:
        raise HTTPException(status_code=400, detail={"code": "invalid_storage_path"})
    return target

async def ingest_upload(db: Session, project_id: str, upload: UploadFile):
    project = db.get(Project, project_id)
    if project is None: raise HTTPException(404, detail={"code": "project_not_found"})
    if project.status != "active": raise HTTPException(409, detail={"code": "project_archived"})
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix="ingest-", suffix=".part", dir=STORAGE_ROOT)
    temp = Path(temp_name)
    digest, total, prefix = hashlib.sha256(), 0, b""
    try:
        with os.fdopen(fd, "wb") as output:
            while True:
                chunk = await upload.read(1024 * 1024)
                if not chunk: break
                total += len(chunk)
                if total > MAX_UPLOAD_BYTES:
                    raise HTTPException(413, detail={"code": "upload_too_large", "max_bytes": MAX_UPLOAD_BYTES})
                prefix = (prefix + chunk)[:32]
                digest.update(chunk)
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if total == 0: raise HTTPException(400, detail={"code": "empty_upload"})
        sha, mime = digest.hexdigest(), detect_mime(prefix)
        asset = db.scalar(select(Asset).where(Asset.sha256 == sha))
        if asset is None:
            destination = blob_path(sha)
            destination.parent.mkdir(parents=True, exist_ok=True)
            if not destination.exists(): os.replace(temp, destination)
            asset = Asset(sha256=sha, size_bytes=total, mime_type=mime, storage_key=f"blobs/{sha[:2]}/{sha}")
            db.add(asset)
            db.flush()
        link = db.scalar(select(ProjectAsset).where(ProjectAsset.project_id == project_id, ProjectAsset.asset_id == asset.id))
        if link is None:
            link = ProjectAsset(project_id=project_id, asset_id=asset.id,
                                original_filename=safe_filename(upload.filename or "upload.bin"))
            db.add(link)
        db.commit()
        db.refresh(asset)
        db.refresh(link)
        return asset, link
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, detail={"code": "asset_link_conflict"})
    except Exception:
        db.rollback()
        raise
    finally:
        await upload.close()
        temp.unlink(missing_ok=True)

def list_project_assets(db: Session, project_id: str):
    if db.get(Project, project_id) is None: raise HTTPException(404, detail={"code": "project_not_found"})
    rows = db.execute(select(Asset, ProjectAsset).join(ProjectAsset, ProjectAsset.asset_id == Asset.id)
                      .where(ProjectAsset.project_id == project_id).order_by(ProjectAsset.created_at.desc())).all()
    return [{"id": link.id, "asset_id": asset.id, "sha256": asset.sha256, "size_bytes": asset.size_bytes,
             "mime_type": asset.mime_type, "filename": link.original_filename, "created_at": link.created_at}
            for asset, link in rows]

def detach_project_asset(db: Session, project_id: str, link_id: str):
    link = db.scalar(select(ProjectAsset).where(ProjectAsset.id == link_id, ProjectAsset.project_id == project_id))
    if link is None: raise HTTPException(404, detail={"code": "project_asset_not_found"})
    db.delete(link)
    db.commit()
    # Blob bytes are retained. Garbage collection must prove zero references before deletion.


def attach_task_artifact(db: Session, task_id: str, asset_id: str, filename: str):
    from .models import StudioTask, TaskArtifact
    task = db.get(StudioTask, task_id)
    if task is None:
        raise HTTPException(404, detail={"code": "task_not_found"})
    if task.status != "succeeded":
        raise HTTPException(409, detail={"code": "task_artifacts_require_succeeded_task"})
    if not task.project_id:
        raise HTTPException(409, detail={"code": "task_project_required_for_artifacts"})
    linked = db.scalar(select(ProjectAsset).where(
        ProjectAsset.project_id == task.project_id, ProjectAsset.asset_id == asset_id
    ))
    if linked is None:
        raise HTTPException(404, detail={"code": "project_asset_not_found"})
    existing = db.scalar(select(TaskArtifact).where(
        TaskArtifact.task_id == task_id, TaskArtifact.asset_id == asset_id
    ))
    if existing is not None:
        return existing
    link = TaskArtifact(task_id=task_id, asset_id=asset_id, original_filename=safe_filename(filename))
    db.add(link)
    try:
        db.commit()
        db.refresh(link)
    except IntegrityError:
        db.rollback()
        existing = db.scalar(select(TaskArtifact).where(
            TaskArtifact.task_id == task_id, TaskArtifact.asset_id == asset_id
        ))
        if existing is None:
            raise HTTPException(409, detail={"code": "task_artifact_conflict"})
        return existing
    return link


def list_task_artifacts(db: Session, task_id: str):
    from .models import StudioTask, TaskArtifact
    if db.get(StudioTask, task_id) is None:
        raise HTTPException(404, detail={"code": "task_not_found"})
    rows = db.execute(
        select(Asset, TaskArtifact).join(TaskArtifact, TaskArtifact.asset_id == Asset.id)
        .where(TaskArtifact.task_id == task_id)
        .order_by(TaskArtifact.created_at.desc())
    ).all()
    return [{
        "id": link.id, "asset_id": asset.id, "sha256": asset.sha256,
        "size_bytes": asset.size_bytes, "mime_type": asset.mime_type,
        "filename": link.original_filename, "created_at": link.created_at,
        "previewable": asset.mime_type in {
            "image/png", "image/jpeg", "image/gif", "image/webp",
            "audio/mpeg", "audio/wav", "audio/ogg", "audio/flac",
            "video/mp4", "video/webm",
        },
    } for asset, link in rows]


def resolve_task_artifact_file(db: Session, task_id: str, artifact_id: str):
    from .models import StudioTask, TaskArtifact
    if db.get(StudioTask, task_id) is None:
        raise HTTPException(404, detail={"code": "task_not_found"})
    row = db.execute(
        select(Asset, TaskArtifact).join(TaskArtifact, TaskArtifact.asset_id == Asset.id)
        .where(TaskArtifact.task_id == task_id, TaskArtifact.id == artifact_id)
    ).first()
    if row is None:
        raise HTTPException(404, detail={"code": "task_artifact_not_found"})
    asset, link = row
    path = blob_path(asset.sha256)
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404, detail={"code": "artifact_file_missing"})
    try:
        if path.stat().st_size != asset.size_bytes:
            raise HTTPException(409, detail={"code": "artifact_size_mismatch"})
    except OSError:
        raise HTTPException(404, detail={"code": "artifact_file_missing"})
    return asset, link, path
