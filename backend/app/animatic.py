"""Approved-take animatic renderer and OpenTimelineIO interchange exporter.

The renderer intentionally creates a silent picture-only animatic in v1.
Audio, narration, sound design and music are separate timeline tracks planned
for the next media slice.
"""
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from .models import (
    Asset, Project, ProjectAsset, Story, StoryScene, StoryboardShot, StoryboardTake,
)
from .storage import blob_path, ingest_generated_media_bytes, resolve_project_asset_file
from .task_manager import create_task, update_task_execution
from .animatic_schemas import AnimaticTaskCreate

MAX_SHOTS = 120
MAX_TOTAL_SECONDS = 1800
MAX_SOURCE_IMAGE_BYTES = 100 * 1024 * 1024
MAX_RENDER_BYTES = 100 * 1024 * 1024
RENDER_TIMEOUT_SECONDS = 1800

_TRANSITIONS = {
    "dissolve": "fade",
    "fade": "fade",
    "crossfade": "fade",
    "wipeleft": "wipeleft",
    "wiperight": "wiperight",
    "slideleft": "slideleft",
    "slideright": "slideright",
    "circleopen": "circleopen",
}


class AnimaticTaskError(RuntimeError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.error_code = code
        self.public_message = message


def _rational(value: int, rate: int) -> dict:
    return {"OTIO_SCHEMA": "RationalTime.1", "value": value, "rate": rate}


def _time_range(duration_frames: int, rate: int) -> dict:
    return {
        "OTIO_SCHEMA": "TimeRange.1",
        "start_time": _rational(0, rate),
        "duration": _rational(duration_frames, rate),
    }


def _timeline_document(snapshot: dict, video_asset_id: str, rate: int) -> bytes:
    children: list[dict] = []
    for index, shot in enumerate(snapshot["shots"]):
        frames = max(1, round(float(shot["duration_seconds"]) * rate))
        asset_id = shot["asset_id"]
        children.append({
            "OTIO_SCHEMA": "Clip.2",
            "name": shot["title"],
            "source_range": _time_range(frames, rate),
            "media_reference": {
                "OTIO_SCHEMA": "ExternalReference.1",
                "target_url": blob_path(shot["asset_sha256"]).as_uri(),
                "available_range": _time_range(frames, rate),
                "metadata": {"storyforge": {"asset_id": asset_id, "sha256": shot["asset_sha256"]}},
            },
            "metadata": {
                "storyforge": {
                    "shot_id": shot["shot_id"], "take_id": shot["take_id"],
                    "scene_id": shot["scene_id"], "scene_title": shot["scene_title"],
                    "position": shot["position"], "transition_out": shot.get("transition"),
                    "continuity_notes": shot.get("continuity_notes") or "",
                }
            },
        })
        if index < len(snapshot["shots"]) - 1:
            transition = str(shot.get("transition") or "").strip().lower().replace(" ", "")
            if transition in _TRANSITIONS:
                transition_frames = max(2, round(min(0.75, frames / rate / 4,
                    float(snapshot["shots"][index + 1]["duration_seconds"]) / 4) * rate))
                half = max(1, transition_frames // 2)
                children.append({
                    "OTIO_SCHEMA": "Transition.1",
                    "name": f"{transition} · {shot['title']}",
                    "transition_type": "SMPTE_Dissolve" if _TRANSITIONS[transition] == "fade" else "Custom",
                    "in_offset": _rational(half, rate),
                    "out_offset": _rational(transition_frames - half, rate),
                    "metadata": {"storyforge": {"ffmpeg_transition": _TRANSITIONS[transition]}},
                })
    document = {
        "OTIO_SCHEMA": "Timeline.1",
        "name": f"{snapshot['story_title']} · Animatic",
        "global_start_time": _rational(0, rate),
        "tracks": {
            "OTIO_SCHEMA": "Stack.1",
            "name": "tracks",
            "children": [{
                "OTIO_SCHEMA": "Track.1",
                "name": "Picture",
                "kind": "Video",
                "children": children,
                "metadata": {"storyforge": {"project_id": snapshot["project_id"], "story_id": snapshot["story_id"]}},
            }],
            "metadata": {},
        },
        "metadata": {
            "storyforge": {
                "format_version": 1,
                "rendered_video_asset_id": video_asset_id,
                "frame_rate": rate,
                "resolution": snapshot["resolution"],
                "approved_takes_only": True,
                "audio_included": False,
            }
        },
    }
    return json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def create_animatic_task(db: Session, story_id: str, payload: AnimaticTaskCreate,
                         idempotency_key: str) -> dict:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(404, detail={"code": "story_not_found"})
    project = db.get(Project, story.project_id)
    if project is None:
        raise HTTPException(404, detail={"code": "project_not_found"})
    if project.status != "active":
        raise HTTPException(409, detail={"code": "project_archived"})

    rows = db.execute(
        select(StoryboardShot, StoryScene)
        .join(StoryScene, StoryScene.id == StoryboardShot.scene_id)
        .where(StoryboardShot.story_id == story_id)
        .order_by(StoryScene.position, StoryboardShot.position)
    ).all()
    if not rows:
        raise HTTPException(409, detail={"code": "animatic_storyboard_empty"})

    if len(rows) > MAX_SHOTS:
        raise HTTPException(422, detail={"code": "animatic_shot_limit_exceeded", "maximum": MAX_SHOTS})

    shots: list[dict[str, Any]] = []
    total_seconds = 0.0
    for shot, scene in rows:
        take_id = shot.approved_take_id
        if not take_id:
            raise HTTPException(409, detail={
                "code": "animatic_requires_approved_take",
                "shot_id": shot.id, "shot_title": shot.title,
            })
        take = db.get(StoryboardTake, take_id)
        if take is None or take.shot_id != shot.id or take.status != "approved":
            raise HTTPException(409, detail={"code": "animatic_approved_take_invalid", "shot_id": shot.id})
        asset = db.get(Asset, take.asset_id)
        if asset is None or asset.mime_type not in {"image/png", "image/jpeg", "image/webp", "video/mp4", "video/webm"}:
            raise HTTPException(422, detail={"code": "animatic_take_media_unsupported", "shot_id": shot.id})
        linked = db.scalar(select(ProjectAsset.id).where(
            ProjectAsset.project_id == story.project_id, ProjectAsset.asset_id == asset.id
        ))
        if linked is None:
            raise HTTPException(409, detail={"code": "animatic_take_project_scope_invalid", "shot_id": shot.id})
        duration = float(shot.duration_seconds)
        if not 0.1 <= duration <= 600:
            raise HTTPException(422, detail={"code": "animatic_shot_duration_invalid", "shot_id": shot.id})
        total_seconds += duration
        shots.append({
            "shot_id": shot.id, "shot_version": shot.version, "take_id": take.id,
            "asset_id": asset.id, "asset_sha256": asset.sha256, "asset_mime_type": asset.mime_type,
            "scene_id": scene.id, "scene_title": scene.title, "scene_position": scene.position,
            "position": shot.position, "title": shot.title, "duration_seconds": duration,
            "transition": shot.transition, "continuity_notes": shot.continuity_notes,
        })
    if total_seconds > MAX_TOTAL_SECONDS:
        raise HTTPException(422, detail={"code": "animatic_duration_limit_exceeded", "maximum_seconds": MAX_TOTAL_SECONDS})

    snapshot = {
        "story_id": story.id, "story_title": story.title, "project_id": story.project_id,
        "story_version": story.version, "resolution": f"{payload.width}x{payload.height}",
        "width": payload.width, "height": payload.height, "fps": payload.fps,
        "total_seconds": round(total_seconds, 3), "shots": shots,
    }
    return create_task(
        db, task_type="storyboard.create_animatic", payload={"snapshot": snapshot},
        idempotency_key=idempotency_key, project_id=story.project_id,
        execution_mode="local", estimated_duration_seconds=max(30, round(total_seconds * 2)),
        max_attempts=1,
    )


def _load_approved_inputs(db: Session, snapshot: dict) -> list[tuple[dict, Path]]:
    story = db.get(Story, snapshot["story_id"])
    project = db.get(Project, snapshot["project_id"])
    if story is None or project is None or story.project_id != snapshot["project_id"] or project.status != "active":
        raise AnimaticTaskError("animatic_project_scope_changed", "The story or project is no longer available")
    resolved: list[tuple[dict, Path]] = []
    for item in snapshot["shots"]:
        shot = db.get(StoryboardShot, item["shot_id"])
        take = db.get(StoryboardTake, item["take_id"])
        if (shot is None or shot.story_id != story.id or shot.version != item["shot_version"]
                or shot.approved_take_id != item["take_id"] or take is None
                or take.shot_id != shot.id or take.status != "approved" or take.asset_id != item["asset_id"]):
            raise AnimaticTaskError("animatic_approval_stale", "A storyboard shot or approved take changed; review the storyboard and create a new animatic")
        asset, _link, path = resolve_project_asset_file(db, project.id, item["asset_id"])
        if asset.sha256 != item["asset_sha256"] or asset.mime_type not in {"image/png", "image/jpeg", "image/webp", "video/mp4", "video/webm"}:
            raise AnimaticTaskError("animatic_source_asset_invalid", "An approved storyboard image is no longer valid")
        if asset.size_bytes > MAX_SOURCE_IMAGE_BYTES:
            raise AnimaticTaskError("animatic_source_image_too_large", "An approved storyboard image exceeds the render size limit")
        resolved.append((item, path))
    return resolved


def _filter_graph(shots: list[dict], fps: int, width: int, height: int) -> tuple[str, str, float]:
    filters = []
    for index, shot in enumerate(shots):
        filters.append(
            f"[{index}:v]trim=duration={float(shot['duration_seconds']):.3f},setpts=PTS-STARTPTS,"
            f"scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2:color=black,"
            f"setsar=1,fps={fps},format=yuv420p,settb=AVTB[v{index}]"
        )
    current = "v0"
    current_duration = float(shots[0]["duration_seconds"])
    for index in range(1, len(shots)):
        previous = shots[index - 1]
        transition = str(previous.get("transition") or "").strip().lower().replace(" ", "")
        ff_transition = _TRANSITIONS.get(transition)
        next_label = f"v{index}"
        out_label = f"mix{index}"
        if ff_transition:
            duration = min(0.75, float(previous["duration_seconds"]) / 4,
                           float(shots[index]["duration_seconds"]) / 4)
            duration = max(2 / fps, duration)
            offset = max(0.0, current_duration - duration)
            filters.append(
                f"[{current}][{next_label}]xfade=transition={ff_transition}:"
                f"duration={duration:.6f}:offset={offset:.6f}[{out_label}]"
            )
            current_duration += float(shots[index]["duration_seconds"]) - duration
        else:
            filters.append(f"[{current}][{next_label}]concat=n=2:v=1:a=0[{out_label}]")
            current_duration += float(shots[index]["duration_seconds"])
        current = out_label
    return ";\n".join(filters), current, current_duration


def build_animatic_handler(session_factory: sessionmaker):
    def handle(payload: dict) -> dict:
        meta = payload.get("_studio_task") or {}
        task_id, worker_id = meta.get("id"), meta.get("worker_id")
        snapshot = payload.get("snapshot")
        if not isinstance(task_id, str) or not isinstance(worker_id, str) or not isinstance(snapshot, dict):
            raise AnimaticTaskError("animatic_task_invalid", "Animatic task metadata is invalid")
        ffmpeg = os.getenv("MASOUD_STUDIO_FFMPEG_PATH", "").strip() or shutil.which("ffmpeg")
        if not ffmpeg:
            raise AnimaticTaskError("ffmpeg_unavailable", "FFmpeg was not found. Install FFmpeg or configure MASOUD_STUDIO_FFMPEG_PATH")
        db = session_factory()
        try:
            update_task_execution(db, task_id, worker_id, progress_stage="validating_approved_takes", progress_percent=5)
            inputs = _load_approved_inputs(db, snapshot)
        finally:
            db.close()

        width, height, fps = snapshot["width"], snapshot["height"], snapshot["fps"]
        with tempfile.TemporaryDirectory(prefix="storyforge-animatic-") as temporary:
            workdir = Path(temporary)
            input_args: list[str] = []
            for index, (shot, source_path) in enumerate(inputs):
                staged = workdir / f"shot-{index:03d}{source_path.suffix.lower() or '.img'}"
                shutil.copyfile(source_path, staged)
                if shot["asset_mime_type"].startswith("video/"):
                input_args.extend(["-stream_loop", "-1", "-i", str(staged)])
            else:
                input_args.extend(["-loop", "1", "-framerate", str(fps), "-i", str(staged)])
            graph, output_label, output_duration = _filter_graph(snapshot["shots"], fps, width, height)
            filter_script = workdir / "filters.txt"
            filter_script.write_text(graph, encoding="utf-8")
            output_path = workdir / "animatic.mp4"
            command = [
                ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                *input_args, "-filter_complex_script", str(filter_script),
                "-map", f"[{output_label}]", "-map_metadata", "-1", "-map_chapters", "-1", "-an", "-t", f"{output_duration:.3f}",
                "-c:v", "libx264", "-preset", "medium", "-crf", "21",
                "-pix_fmt", "yuv420p", "-r", str(fps), "-movflags", "+faststart",
                "-fs", str(MAX_RENDER_BYTES), "-f", "mp4", str(output_path),
            ]
            db = session_factory()
            try:
                update_task_execution(db, task_id, worker_id, progress_stage="rendering_animatic", progress_percent=20)
            finally:
                db.close()
            try:
                completed = subprocess.run(
                    command, cwd=str(workdir), shell=False, capture_output=True,
                    text=True, timeout=RENDER_TIMEOUT_SECONDS, check=False,
                )
            except subprocess.TimeoutExpired:
                raise AnimaticTaskError("animatic_render_timeout", "Animatic rendering exceeded its time limit") from None
            if completed.returncode != 0 or not output_path.is_file():
                # Do not persist raw FFmpeg output; it can contain local paths.
                raise AnimaticTaskError("animatic_render_failed", "FFmpeg could not render this animatic; inspect the local diagnostic log")
            output_size = output_path.stat().st_size
            if output_size <= 0 or output_size > MAX_RENDER_BYTES:
                raise AnimaticTaskError("animatic_output_size_invalid", "Rendered animatic is empty or exceeds the 100 MB output limit")
            video_bytes = output_path.read_bytes()

        db = session_factory()
        try:
            update_task_execution(db, task_id, worker_id, progress_stage="storing_animatic", progress_percent=90)
            video_asset, _ = ingest_generated_media_bytes(
                db, snapshot["project_id"], f"{snapshot['story_id']}-animatic.mp4",
                video_bytes, media_type="video/mp4",
            )
            timeline_bytes = _timeline_document(snapshot, video_asset.id, fps)
            timeline_asset, _ = ingest_generated_media_bytes(
                db, snapshot["project_id"], f"{snapshot['story_id']}-animatic.otio",
                timeline_bytes, media_type="application/json",
            )
            update_task_execution(db, task_id, worker_id, progress_stage="completed", progress_percent=100)
            return {
                "video_asset_id": video_asset.id,
                "timeline_asset_id": timeline_asset.id,
                "duration_seconds": round(output_duration, 3),
                "resolution": snapshot["resolution"],
                "fps": fps,
                "shot_count": len(snapshot["shots"]),
                "approved_takes_only": True,
                "audio_included": False,
                "artifacts": [
                    {"asset_id": video_asset.id, "filename": f"{snapshot['story_id']}-animatic.mp4"},
                    {"asset_id": timeline_asset.id, "filename": f"{snapshot['story_id']}-animatic.otio"},
                ],
            }
        finally:
            db.close()
    return handle
