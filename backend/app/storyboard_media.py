"""ComfyUI image-generation adapter for Storyboard; uses the shared Task Manager and Asset store."""
import asyncio
import copy
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlsplit

import aiohttp
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from .ai_gateway import validate_provider_url, _resolve_provider_addresses, _PinnedResolver
from .models import Project, Story, StoryScene, StoryboardShot, StoryboardTake
from .storage import ingest_generated_bytes
from .task_manager import create_task, update_task_execution
from .storyboard_schemas import StoryboardImageTaskCreate

WORKFLOW_DIR = Path(__file__).resolve().parents[1] / "workflows" / "comfyui"
MAX_OUTPUT_BYTES = 30 * 1024 * 1024
MAX_POLL_SECONDS = 600


def load_workflow_pack(workflow_id: str) -> dict:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", workflow_id):
        raise ValueError("Invalid workflow identifier")
    path = WORKFLOW_DIR / f"{workflow_id}.json"
    try:
        pack = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ValueError("The selected ComfyUI workflow pack is not installed") from None
    if not isinstance(pack, dict) or pack.get("schema_version") != 1:
        raise ValueError("Unsupported ComfyUI workflow pack")
    graph = pack.get("workflow")
    mapping = pack.get("mapping")
    if not isinstance(graph, dict) or not isinstance(mapping, dict):
        raise ValueError("Invalid ComfyUI workflow pack")
    for key in ("checkpoint", "positive_prompt", "negative_prompt", "width", "height", "steps", "cfg", "seed"):
        entry = mapping.get(key)
        if not isinstance(entry, list) or len(entry) != 3 or not all(isinstance(v, str) for v in entry):
            raise ValueError("Invalid ComfyUI workflow input mapping")
        node_id, section, field = entry
        if node_id not in graph or not isinstance(graph[node_id], dict):
            raise ValueError("Workflow mapping references a missing node")
        inputs = graph[node_id].get(section)
        if not isinstance(inputs, dict) or field not in inputs:
            raise ValueError("Workflow mapping references a missing input")
    return pack


def build_workflow_graph(pack: dict, *, checkpoint: str, prompt: str, negative_prompt: str,
                         width: int, height: int, steps: int, cfg: float, seed: int) -> dict:
    graph = copy.deepcopy(pack["workflow"])
    values = {"checkpoint": checkpoint, "positive_prompt": prompt, "negative_prompt": negative_prompt,
              "width": width, "height": height, "steps": steps, "cfg": cfg, "seed": seed}
    for name, value in values.items():
        node_id, section, field = pack["mapping"][name]
        graph[node_id][section][field] = value
    return graph


def _validate_image_locator(item: dict) -> tuple[str, str, str]:
    if not isinstance(item, dict):
        raise ValueError("ComfyUI returned an invalid image reference")
    filename = item.get("filename")
    subfolder = item.get("subfolder", "")
    folder_type = item.get("type", "output")
    if (not isinstance(filename, str) or not filename or len(filename) > 255
        or Path(filename).name != filename or "/" in filename or "\\" in filename
        or not isinstance(subfolder, str) or len(subfolder) > 240
        or Path(subfolder).is_absolute() or ".." in Path(subfolder).parts
        or folder_type != "output"):
        raise ValueError("ComfyUI returned an unsafe image reference")
    return filename, subfolder, folder_type


class ComfyUIClient:
    def __init__(self, base_url: str | None = None):
        configured = base_url or os.getenv("MASOUD_STUDIO_COMFYUI_URL", "http://127.0.0.1:8188")
        self.base_url = validate_provider_url(configured, allow_local=True)
        parsed = urlsplit(self.base_url)
        self.host = parsed.hostname
        self.port = parsed.port
        self.path = parsed.path.rstrip("/")

    async def generate(self, graph: dict, remote_job_id: str | None = None, progress=None) -> tuple[bytes, str, str]:
        pinned = await _resolve_provider_addresses(self.host, self.port, allow_local=True)
        resolver = _PinnedResolver(pinned)
        connector = aiohttp.TCPConnector(resolver=resolver, use_dns_cache=False)
        timeout = aiohttp.ClientTimeout(total=MAX_POLL_SECONDS + 30, connect=10, sock_read=45)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False) as session:
            if remote_job_id:
                prompt_id = remote_job_id
            else:
                prompt_id = str(uuid4())
                payload = {"prompt": graph, "client_id": str(uuid4()), "prompt_id": prompt_id}
                async with session.post(self.base_url + "/prompt", json=payload, allow_redirects=False) as response:
                    if response.status != 200:
                        raise RuntimeError("ComfyUI rejected the generation workflow")
                    queued = await response.json(content_type=None)
                prompt_id = queued.get("prompt_id") if isinstance(queued, dict) else None
                if not isinstance(prompt_id, str) or not prompt_id or len(prompt_id) > 100:
                    raise RuntimeError("ComfyUI did not return a valid job identifier")
                if progress:
                    progress(prompt_id, "queued", 5)
            deadline = time.monotonic() + MAX_POLL_SECONDS
            last_percent = -1
            while time.monotonic() < deadline:
                async with session.get(self.base_url + f"/history/{prompt_id}", allow_redirects=False) as response:
                    if response.status not in (200, 404):
                        raise RuntimeError("ComfyUI history request failed")
                    history = await response.json(content_type=None) if response.status == 200 else {}
                record = history.get(prompt_id) if isinstance(history, dict) else None
                if isinstance(record, dict):
                    status = record.get("status") or {}
                    if status.get("status_str") == "error":
                        raise RuntimeError("ComfyUI workflow execution failed")
                    outputs = record.get("outputs") or {}
                    candidates = []
                    if isinstance(outputs, dict):
                        for node_output in outputs.values():
                            if isinstance(node_output, dict) and isinstance(node_output.get("images"), list):
                                candidates.extend(node_output["images"])
                    if candidates:
                        filename, subfolder, folder_type = _validate_image_locator(candidates[0])
                        async with session.get(
                            self.base_url + "/view",
                            params={"filename": filename, "subfolder": subfolder, "type": folder_type},
                            allow_redirects=False,
                        ) as image_response:
                            if image_response.status != 200:
                                raise RuntimeError("ComfyUI generated image could not be retrieved")
                            data = await image_response.content.read(MAX_OUTPUT_BYTES + 1)
                        if not data or len(data) > MAX_OUTPUT_BYTES:
                            raise RuntimeError("ComfyUI image output exceeded the configured limit")
                        from .storage import detect_mime
                        if detect_mime(data[:32]) not in {"image/png", "image/jpeg", "image/webp"}:
                            raise RuntimeError("ComfyUI returned an unsupported image format")
                        return data, filename, prompt_id
                if progress:
                    percent = min(90, 10 + int((MAX_POLL_SECONDS - max(0, deadline - time.monotonic())) / MAX_POLL_SECONDS * 80))
                    if percent != last_percent:
                        progress(prompt_id, "generating", percent)
                        last_percent = percent
                await asyncio.sleep(1.0)
        raise TimeoutError("ComfyUI generation timed out")


def create_storyboard_image_task(db: Session, story_id: str, shot_id: str,
                                 payload: StoryboardImageTaskCreate, idempotency_key: str) -> dict:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(404, detail={"code": "story_not_found"})
    project = db.get(Project, story.project_id)
    if project is None or project.status != "active" or story.status in {"archived", "locked"}:
        raise HTTPException(409, detail={"code": "story_not_active"})
    shot = db.get(StoryboardShot, shot_id)
    if shot is None or shot.story_id != story_id:
        raise HTTPException(404, detail={"code": "storyboard_shot_not_found"})
    scene = db.get(StoryScene, shot.scene_id)
    if scene is None or scene.story_id != story_id:
        raise HTTPException(409, detail={"code": "storyboard_scene_scope_invalid"})
    prompt = (shot.prompt or "").strip()
    if not prompt:
        raise HTTPException(409, detail={"code": "storyboard_prompt_required"})
    try:
        pack = load_workflow_pack(payload.workflow_id)
    except ValueError as exc:
        raise HTTPException(422, detail={"code": "workflow_pack_invalid", "message": str(exc)}) from None
    snapshot = {
        "story_id": story_id, "project_id": story.project_id, "shot_id": shot.id,
        "shot_version": shot.version, "scene_id": scene.id, "workflow_id": payload.workflow_id,
        "workflow_version": pack.get("version", "1.0.0"), "prompt": prompt,
        "negative_prompt": payload.negative_prompt, "width": payload.width, "height": payload.height,
        "steps": payload.steps, "cfg": payload.cfg, "seed": payload.seed,
        "shot_title": shot.title, "source_excerpt": shot.source_excerpt,
    }
    return create_task(
        db, task_type="storyboard.generate_image", payload={"snapshot": snapshot},
        idempotency_key=idempotency_key, project_id=story.project_id,
        execution_mode="local", estimated_duration_seconds=180,
        max_attempts=2,
    )


def build_storyboard_image_handler(session_factory: sessionmaker):
    def handle(payload: dict) -> dict:
        meta = payload.get("_studio_task") or {}
        task_id, worker_id = meta.get("id"), meta.get("worker_id")
        snapshot = payload.get("snapshot") or {}
        if not isinstance(task_id, str) or not isinstance(worker_id, str) or not isinstance(snapshot, dict):
            raise ValueError("Storyboard image task metadata is invalid")
        checkpoint = os.getenv("MASOUD_STUDIO_COMFYUI_CHECKPOINT", "").strip()
        if not checkpoint or len(checkpoint) > 240 or "/" in checkpoint or "\\" in checkpoint:
            raise RuntimeError("Configure a valid ComfyUI checkpoint filename before image generation")
        pack = load_workflow_pack(snapshot.get("workflow_id", ""))
        seed = snapshot.get("seed")
        if seed is None:
            seed = int.from_bytes(os.urandom(8), "big")
        graph = build_workflow_graph(
            pack, checkpoint=checkpoint, prompt=snapshot["prompt"],
            negative_prompt=snapshot.get("negative_prompt", ""), width=snapshot["width"],
            height=snapshot["height"], steps=snapshot["steps"], cfg=snapshot["cfg"], seed=seed,
        )
        def progress(remote_id, stage, percent):
            db = session_factory()
            try:
                update_task_execution(db, task_id, worker_id, remote_job_id=remote_id,
                                      progress_stage=stage, progress_percent=percent)
            finally:
                db.close()
        remote_id = meta.get("remote_job_id")
        data, filename, remote_id = asyncio.run(ComfyUIClient().generate(graph, remote_id, progress))
        db = session_factory()
        try:
            shot = db.get(StoryboardShot, snapshot["shot_id"])
            story = db.get(Story, snapshot["story_id"])
            if shot is None or story is None or shot.story_id != story.id or story.project_id != snapshot["project_id"]:
                raise RuntimeError("Storyboard shot scope changed during generation")
            if shot.version != snapshot["shot_version"]:
                raise RuntimeError("Storyboard shot changed during image generation; review and retry")
            asset, _link = ingest_generated_bytes(
                db, snapshot["project_id"], filename, data
            )
            next_number = (db.scalar(select(func.max(StoryboardTake.take_number)).where(
                StoryboardTake.shot_id == shot.id
            )) or 0) + 1
            take = StoryboardTake(
                shot_id=shot.id, take_number=next_number, asset_id=asset.id,
                asset_sha256=asset.sha256, status="generated", engine_key="comfyui",
                engine_job_id=remote_id, prompt_snapshot=snapshot["prompt"],
                generation_metadata_json=json.dumps({
                    "workflow_id": snapshot["workflow_id"], "workflow_version": snapshot["workflow_version"],
                    "width": snapshot["width"], "height": snapshot["height"], "steps": snapshot["steps"],
                    "cfg": snapshot["cfg"], "seed": seed, "mime_type": asset.mime_type,
                }, ensure_ascii=False, separators=(",", ":")),
                created_at=datetime.now(timezone.utc),
            )
            db.add(take)
            db.commit()
            db.refresh(take)
            return {
                "kind": "storyboard_image_take", "story_id": story.id, "shot_id": shot.id,
                "take_id": take.id, "take_number": take.take_number, "asset_id": asset.id,
                "asset_sha256": asset.sha256, "mime_type": asset.mime_type,
                "engine": "comfyui", "engine_job_id": remote_id,
                "review_required": True, "approved": False,
            }
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    return handle
