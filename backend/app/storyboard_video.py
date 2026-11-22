"""ComfyUI image-to-video adapter for reviewable Storyboard video takes."""
import asyncio
import copy
import json
import os
import re
import time
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

import aiohttp
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from .ai_gateway import _PinnedResolver, _resolve_provider_addresses
from .models import Asset, Project, ProjectAsset, Story, StoryboardShot, StoryboardTake
from .storage import ingest_generated_media_bytes, resolve_project_asset_file
from .task_manager import create_task, update_task_execution
from .storyboard_media import ComfyUIClient, MAX_POLL_SECONDS
from .storyboard_video_schemas import StoryboardVideoTaskCreate

VIDEO_WORKFLOW_DIR = Path(__file__).resolve().parents[1] / "workflows" / "comfyui" / "video"
MAX_START_IMAGE_BYTES = 30 * 1024 * 1024
MAX_VIDEO_OUTPUT_BYTES = 100 * 1024 * 1024
_VIDEO_ID = re.compile(r"^[a-z0-9][a-z0-9.-]{0,78}[a-z0-9]$")


class StoryboardVideoError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.error_code = code
        self.public_message = message


def load_video_workflow_pack(workflow_id: str) -> dict:
    if not isinstance(workflow_id, str) or not _VIDEO_ID.fullmatch(workflow_id):
        raise ValueError("Invalid video workflow identifier")
    try:
        pack = json.loads((VIDEO_WORKFLOW_DIR / f"{workflow_id}.json").read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError("The selected ComfyUI video workflow pack is not installed") from None
    if not isinstance(pack, dict) or pack.get("schema_version") != 1 or pack.get("kind") != "image_to_video":
        raise ValueError("Unsupported ComfyUI video workflow pack")
    graph, mapping, outputs = pack.get("workflow"), pack.get("mapping"), pack.get("output_node_ids")
    if not isinstance(graph, dict) or not isinstance(mapping, dict) or not isinstance(outputs, list) or not outputs:
        raise ValueError("Invalid ComfyUI video workflow pack")
    for key in ("unet", "clip", "vae", "clip_vision", "positive_prompt", "negative_prompt",
                "seed", "width", "height", "frames", "fps", "start_image"):
        entry = mapping.get(key)
        if not isinstance(entry, list) or len(entry) != 3 or not all(isinstance(v, str) for v in entry):
            raise ValueError("Invalid ComfyUI video workflow mapping")
        node_id, section, field = entry
        if node_id not in graph or not isinstance(graph[node_id], dict):
            raise ValueError("Video workflow mapping references a missing node")
        inputs = graph[node_id].get(section)
        if not isinstance(inputs, dict) or field not in inputs:
            raise ValueError("Video workflow mapping references a missing input")
    if any(not isinstance(node_id, str) or node_id not in graph for node_id in outputs):
        raise ValueError("Video workflow output references a missing node")
    return pack


def _safe_model_filename(value: str, field: str) -> str:
    if not isinstance(value, str) or not value or len(value) > 255 or Path(value).name != value or "/" in value or "\\" in value:
        raise StoryboardVideoError("video_model_configuration_invalid", f"Configure a valid ComfyUI {field} model filename")
    return value


def build_video_workflow_graph(pack: dict, *, prompt: str, negative_prompt: str,
                               start_image: str, frames: int, fps: int, seed: int) -> dict:
    graph = copy.deepcopy(pack["workflow"])
    mapping = pack["mapping"]
    model_values = {
        "unet": _safe_model_filename(os.getenv("MASOUD_STUDIO_COMFYUI_VIDEO_UNET",
            graph[mapping["unet"][0]][mapping["unet"][1]][mapping["unet"][2]]), "UNET"),
        "clip": _safe_model_filename(os.getenv("MASOUD_STUDIO_COMFYUI_VIDEO_CLIP",
            graph[mapping["clip"][0]][mapping["clip"][1]][mapping["clip"][2]]), "text encoder"),
        "vae": _safe_model_filename(os.getenv("MASOUD_STUDIO_COMFYUI_VIDEO_VAE",
            graph[mapping["vae"][0]][mapping["vae"][1]][mapping["vae"][2]]), "VAE"),
        "clip_vision": _safe_model_filename(os.getenv("MASOUD_STUDIO_COMFYUI_VIDEO_CLIP_VISION",
            graph[mapping["clip_vision"][0]][mapping["clip_vision"][1]][mapping["clip_vision"][2]]), "CLIP Vision"),
    }
    values = {
        **model_values, "positive_prompt": prompt, "negative_prompt": negative_prompt,
        "start_image": start_image, "width": 832, "height": 480, "frames": frames,
        "fps": fps, "seed": seed,
    }
    for name, value in values.items():
        node_id, section, field = mapping[name]
        graph[node_id][section][field] = value
    return graph


def _safe_video_locator(item: dict) -> tuple[str, str, str]:
    if not isinstance(item, dict):
        raise ValueError("ComfyUI returned an invalid video reference")
    filename, subfolder, folder_type = item.get("filename"), item.get("subfolder", ""), item.get("type", "output")
    if (not isinstance(filename, str) or not filename or len(filename) > 255
            or Path(filename).name != filename or "/" in filename or "\\" in filename
            or Path(filename).suffix.lower() not in {".mp4", ".webm"}):
        raise ValueError("ComfyUI returned an unsafe video filename")
    if not isinstance(subfolder, str) or len(subfolder) > 240 or "\\" in subfolder:
        raise ValueError("ComfyUI returned an unsafe video subfolder")
    if subfolder and any(part in {"", ".", ".."} for part in subfolder.split("/")):
        raise ValueError("ComfyUI returned an unsafe video subfolder")
    if folder_type != "output":
        raise ValueError("ComfyUI video output must be in its output directory")
    return filename, subfolder, folder_type


class ComfyUIVideoClient(ComfyUIClient):
    async def upload_start_image(self, content: bytes, mime_type: str) -> str:
        if mime_type not in {"image/png", "image/jpeg", "image/webp"} or not content or len(content) > MAX_START_IMAGE_BYTES:
            raise StoryboardVideoError("video_start_image_invalid", "The approved start image is not supported or exceeds the size limit")
        extension = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}[mime_type]
        filename = f"storyforge-{uuid4().hex}{extension}"
        pinned = await _resolve_provider_addresses(self.host, self.port, allow_local=True)
        connector = aiohttp.TCPConnector(resolver=_PinnedResolver(pinned), use_dns_cache=False)
        timeout = aiohttp.ClientTimeout(total=30, connect=10, sock_read=20)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False) as session:
            form = aiohttp.FormData()
            form.add_field("image", content, filename=filename, content_type=mime_type)
            form.add_field("overwrite", "true")
            async with session.post(self.base_url + "/upload/image", data=form, allow_redirects=False) as response:
                if response.status != 200:
                    raise StoryboardVideoError("comfyui_image_upload_failed", "ComfyUI could not accept the approved start image")
                result = await response.json(content_type=None)
        if not isinstance(result, dict):
            raise StoryboardVideoError("comfyui_image_upload_invalid", "ComfyUI returned an invalid uploaded image reference")
        name, subfolder = result.get("name"), result.get("subfolder", "")
        invalid_subfolder = bool(subfolder) and (
            not isinstance(subfolder, str) or len(subfolder) > 240 or "\\" in subfolder
            or any(part in {"", ".", ".."} for part in subfolder.split("/"))
        )
        if (not isinstance(name, str) or not name or Path(name).name != name
                or "/" in name or "\\" in name or invalid_subfolder):
            raise StoryboardVideoError("comfyui_image_upload_invalid", "ComfyUI returned an invalid uploaded image reference")
        return f"{subfolder}/{name}" if subfolder else name

    async def generate_video(self, graph: dict, output_node_ids: list[str],
                             remote_job_id: str | None = None, progress=None) -> tuple[bytes, str, str, str]:
        pinned = await _resolve_provider_addresses(self.host, self.port, allow_local=True)
        connector = aiohttp.TCPConnector(resolver=_PinnedResolver(pinned), use_dns_cache=False)
        timeout = aiohttp.ClientTimeout(total=MAX_POLL_SECONDS + 45, connect=10, sock_read=45)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False) as session:
            if remote_job_id:
                prompt_id = remote_job_id
            else:
                prompt_id = str(uuid4())
                async with session.post(self.base_url + "/prompt",
                    json={"prompt": graph, "client_id": str(uuid4()), "prompt_id": prompt_id},
                    allow_redirects=False) as response:
                    if response.status != 200:
                        raise StoryboardVideoError("comfyui_video_submit_failed", "ComfyUI rejected the video workflow")
                    queued = await response.json(content_type=None)
                if not isinstance(queued, dict) or queued.get("error") or queued.get("node_errors"):
                    raise StoryboardVideoError("comfyui_video_workflow_invalid", "ComfyUI reported a video workflow validation error")
            if progress:
                progress(prompt_id, "video_generation_submitted", 15)
            deadline = time.monotonic() + MAX_POLL_SECONDS
            while time.monotonic() < deadline:
                async with session.get(self.base_url + f"/history/{prompt_id}", allow_redirects=False) as response:
                    if response.status not in (200, 404):
                        raise StoryboardVideoError("comfyui_video_history_failed", "ComfyUI video status could not be retrieved")
                    history = await response.json(content_type=None) if response.status == 200 else {}
                record = history.get(prompt_id) if isinstance(history, dict) else None
                if isinstance(record, dict):
                    status = record.get("status") or {}
                    if status.get("status_str") == "error":
                        raise StoryboardVideoError("comfyui_video_generation_failed", "ComfyUI could not generate the requested video")
                    outputs = record.get("outputs") or {}
                    candidates = []
                    if isinstance(outputs, dict):
                        for node_id in output_node_ids:
                            node = outputs.get(node_id)
                            if isinstance(node, dict):
                                for key in ("videos", "gifs", "images"):
                                    if isinstance(node.get(key), list):
                                        candidates.extend(node[key])
                    if candidates:
                        filename, subfolder, folder_type = _safe_video_locator(candidates[0])
                        async with session.get(self.base_url + "/view",
                            params={"filename": filename, "subfolder": subfolder, "type": folder_type},
                            allow_redirects=False) as response:
                            if response.status != 200:
                                raise StoryboardVideoError("comfyui_video_download_failed", "ComfyUI generated video could not be retrieved")
                            data = await response.content.read(MAX_VIDEO_OUTPUT_BYTES + 1)
                        if not data or len(data) > MAX_VIDEO_OUTPUT_BYTES:
                            raise StoryboardVideoError("comfyui_video_output_too_large", "ComfyUI video output exceeded the 100 MB limit")
                        from .storage import detect_mime
                        mime = detect_mime(data[:32])
                        if mime not in {"video/mp4", "video/webm"}:
                            raise StoryboardVideoError("comfyui_video_output_invalid", "ComfyUI returned an unsupported video format")
                        return data, filename, prompt_id, mime
                if progress:
                    progress(prompt_id, "video_generation_running", 65)
                await asyncio.sleep(2)
        raise StoryboardVideoError("comfyui_video_timeout", "ComfyUI video generation exceeded the time limit")


def create_storyboard_video_task(db: Session, story_id: str, shot_id: str,
                                 payload: StoryboardVideoTaskCreate, idempotency_key: str) -> dict:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(404, detail={"code": "story_not_found"})
    project = db.get(Project, story.project_id)
    if project is None:
        raise HTTPException(404, detail={"code": "project_not_found"})
    if project.status != "active":
        raise HTTPException(409, detail={"code": "project_archived"})
    shot = db.scalar(select(StoryboardShot).where(
        StoryboardShot.id == shot_id, StoryboardShot.story_id == story_id
    ))
    if shot is None:
        raise HTTPException(404, detail={"code": "storyboard_shot_not_found"})
    if not (shot.prompt or "").strip():
        raise HTTPException(409, detail={"code": "storyboard_prompt_required"})
    if not shot.approved_take_id:
        raise HTTPException(409, detail={"code": "video_generation_requires_approved_start_image"})
    take = db.get(StoryboardTake, shot.approved_take_id)
    if take is None or take.shot_id != shot.id or take.status != "approved":
        raise HTTPException(409, detail={"code": "storyboard_approved_take_invalid"})
    asset = db.get(Asset, take.asset_id)
    if asset is None or asset.mime_type not in {"image/png", "image/jpeg", "image/webp"}:
        raise HTTPException(422, detail={"code": "video_generation_requires_image_take"})
    linked = db.scalar(select(ProjectAsset.id).where(
        ProjectAsset.project_id == story.project_id, ProjectAsset.asset_id == asset.id
    ))
    if linked is None:
        raise HTTPException(409, detail={"code": "video_start_image_project_scope_invalid"})
    try:
        pack = load_video_workflow_pack(payload.workflow_id)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "video_workflow_pack_invalid", "message": str(exc)}) from None
    seed = payload.seed if payload.seed is not None else int.from_bytes(os.urandom(8), "big")
    snapshot = {
        "story_id": story.id, "project_id": story.project_id, "shot_id": shot.id,
        "shot_version": shot.version, "shot_title": shot.title, "prompt": shot.prompt,
        "negative_prompt": payload.negative_prompt, "workflow_id": payload.workflow_id,
        "workflow_version": pack.get("version", "1.0.0"), "start_take_id": take.id,
        "start_asset_id": asset.id, "start_asset_sha256": asset.sha256,
        "frames": payload.frames, "fps": payload.fps, "seed": seed,
    }
    return create_task(
        db, task_type="storyboard.generate_video", payload={"snapshot": snapshot},
        idempotency_key=idempotency_key, project_id=story.project_id,
        execution_mode="local", estimated_duration_seconds=600, max_attempts=1,
    )


def build_storyboard_video_handler(session_factory: sessionmaker):
    def handle(payload: dict) -> dict:
        meta = payload.get("_studio_task") or {}
        task_id, worker_id = meta.get("id"), meta.get("worker_id")
        snapshot = payload.get("snapshot") or {}
        if not isinstance(task_id, str) or not isinstance(worker_id, str) or not isinstance(snapshot, dict):
            raise StoryboardVideoError("video_task_invalid", "Storyboard video task metadata is invalid")
        try:
            pack = load_video_workflow_pack(snapshot.get("workflow_id", ""))
        except ValueError:
            raise StoryboardVideoError("video_workflow_pack_invalid", "The configured ComfyUI video workflow pack is unavailable") from None
        db = session_factory()
        try:
            update_task_execution(db, task_id, worker_id, progress_stage="validating_start_image", progress_percent=5)
            shot = db.get(StoryboardShot, snapshot["shot_id"])
            take = db.get(StoryboardTake, snapshot["start_take_id"])
            if (shot is None or shot.version != snapshot["shot_version"]
                    or shot.approved_take_id != snapshot["start_take_id"] or take is None
                    or take.status != "approved" or take.asset_id != snapshot["start_asset_id"]):
                raise StoryboardVideoError("video_start_approval_stale", "The approved start image changed; review the storyboard and retry")
            asset, _link, path = resolve_project_asset_file(db, snapshot["project_id"], snapshot["start_asset_id"])
            if asset.sha256 != snapshot["start_asset_sha256"] or asset.size_bytes > MAX_START_IMAGE_BYTES:
                raise StoryboardVideoError("video_start_image_invalid", "The approved start image is invalid or too large")
            image_bytes = path.read_bytes()
            mime = asset.mime_type
        finally:
            db.close()

        client = ComfyUIVideoClient()
        remote_id = meta.get("remote_job_id")
        if remote_id:
            uploaded_name = ""
            seed = snapshot["seed"]
            graph = {}
        else:
            uploaded_name = asyncio.run(client.upload_start_image(image_bytes, mime))
            seed = snapshot["seed"]
            graph = build_video_workflow_graph(
                pack, prompt=snapshot["prompt"], negative_prompt=snapshot.get("negative_prompt", ""),
                start_image=uploaded_name, frames=snapshot["frames"], fps=snapshot["fps"], seed=seed,
            )

        def progress(remote_job_id: str, stage: str, percent: int):
            db = session_factory()
            try:
                update_task_execution(db, task_id, worker_id, remote_job_id=remote_job_id,
                                      progress_stage=stage, progress_percent=percent)
            finally:
                db.close()

        video_bytes, filename, remote_id, mime = asyncio.run(
            client.generate_video(graph, pack["output_node_ids"], remote_id, progress)
        )
        db = session_factory()
        try:
            shot = db.get(StoryboardShot, snapshot["shot_id"])
            take = db.get(StoryboardTake, snapshot["start_take_id"])
            story = db.get(Story, snapshot["story_id"])
            if (shot is None or story is None or story.project_id != snapshot["project_id"]
                    or shot.version != snapshot["shot_version"] or shot.approved_take_id != snapshot["start_take_id"]
                    or take is None or take.status != "approved"):
                raise StoryboardVideoError("video_result_stale", "The shot or its approved start take changed during video generation")
            asset, _link = ingest_generated_media_bytes(
                db, snapshot["project_id"], f"{shot.id}-video-take{Path(filename).suffix.lower()}",
                video_bytes, media_type=mime,
            )
            number = (db.scalar(select(func.max(StoryboardTake.take_number)).where(
                StoryboardTake.shot_id == shot.id
            )) or 0) + 1
            new_take = StoryboardTake(
                shot_id=shot.id, take_number=number, asset_id=asset.id, asset_sha256=asset.sha256,
                status="generated", engine_key="comfyui-video", engine_job_id=remote_id,
                prompt_snapshot=snapshot["prompt"],
                generation_metadata_json=json.dumps({
                    "workflow_id": snapshot["workflow_id"], "workflow_version": snapshot["workflow_version"],
                    "frames": snapshot["frames"], "fps": snapshot["fps"], "seed": seed,
                    "mime_type": mime, "start_take_id": snapshot["start_take_id"],
                }, ensure_ascii=False, separators=(",", ":")),
            )
            db.add(new_take)
            db.commit()
            db.refresh(new_take)
            update_task_execution(db, task_id, worker_id, progress_stage="video_take_saved", progress_percent=100)
            return {
                "take_id": new_take.id, "take_number": number, "asset_id": asset.id,
                "asset_sha256": asset.sha256, "mime_type": mime, "filename": f"{shot.id}-video-take{Path(filename).suffix.lower()}",
                "frames": snapshot["frames"], "fps": snapshot["fps"], "seed": seed,
                "artifacts": [{"asset_id": asset.id, "filename": f"{shot.id}-video-take{Path(filename).suffix.lower()}"}],
            }
        finally:
            db.close()
    return handle
