"""Review-first AI prompt generation for scene-linked storyboard shots."""
import asyncio
import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import update
from sqlalchemy.orm import Session, sessionmaker

from .ai_gateway import generate_chat_completion
from .gateway_schemas import ChatCompletionRequest
from .models import Project, Story, StoryScene, StoryboardShot, StudioTask
from .storyboard_schemas import StoryboardPromptTaskCreate, StoryboardPromptApply
from .task_manager import create_task


def create_storyboard_prompt_task(db: Session, story_id: str, shot_id: str,
                                  payload: StoryboardPromptTaskCreate, idempotency_key: str) -> dict:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail={"code": "story_not_found"})
    project = db.get(Project, story.project_id)
    if project is None or project.status != "active" or story.status in {"archived", "locked"}:
        raise HTTPException(status_code=409, detail={"code": "story_not_active"})
    shot = db.get(StoryboardShot, shot_id)
    if shot is None or shot.story_id != story_id:
        raise HTTPException(status_code=404, detail={"code": "storyboard_shot_not_found"})
    scene = db.get(StoryScene, shot.scene_id)
    if scene is None or scene.story_id != story_id:
        raise HTTPException(status_code=409, detail={"code": "storyboard_scene_scope_invalid"})
    snapshot = {
        "story_id": story.id, "story_title": story.title, "genre": story.genre,
        "creative_intent": story.creative_intent, "shot_id": shot.id,
        "shot_version": shot.version, "scene_id": scene.id, "scene_title": scene.title,
        "scene_body": scene.body, "scene_summary": scene.summary,
        "shot": {"title": shot.title, "description": shot.description,
                 "shot_size": shot.shot_size, "camera_angle": shot.camera_angle,
                 "camera_movement": shot.camera_movement, "lens": shot.lens,
                 "composition": shot.composition, "action": shot.action,
                 "dialogue": shot.dialogue, "duration_seconds": float(shot.duration_seconds),
                 "source_excerpt": shot.source_excerpt, "continuity_notes": shot.continuity_notes,
                 "existing_prompt": shot.prompt},
    }
    return create_task(
        db, task_type="storyboard.generate_prompt",
        payload={"snapshot": snapshot, "model": payload.model, "provider_id": payload.provider_id,
                 "creative_direction": payload.creative_direction,
                 "temperature": payload.temperature, "max_tokens": payload.max_tokens},
        idempotency_key=idempotency_key, project_id=story.project_id,
        execution_mode="local", estimated_duration_seconds=30,
    )


def build_storyboard_prompt_handler(session_factory: sessionmaker):
    def handle(payload: dict) -> dict:
        task_id = (payload.get("_studio_task") or {}).get("id")
        model = payload.get("model")
        snapshot = payload.get("snapshot")
        if not isinstance(task_id, str) or not isinstance(model, str) or not isinstance(snapshot, dict):
            raise ValueError("Storyboard prompt task payload is invalid")
        shot = snapshot.get("shot") or {}
        system = (
            "You are a senior film director, cinematographer and visual prompt engineer. "
            "Create one production-ready visual generation prompt for the supplied storyboard shot. "
            "Preserve the screenplay evidence, character/action intent, camera grammar and continuity. "
            "Do not invent characters, props, locations, costumes or story events absent from the supplied context. "
            "Specify subject, environment, composition, lens/camera, lighting, visual style, action and temporal moment. "
            "Avoid contradictory camera instructions, vague adjectives, text/logos/watermarks and unsupported details. "
            "Return only the finished prompt, with no preamble or markdown."
        )
        user = (
            f"STORY CONTEXT:\n{json.dumps({k:snapshot.get(k) for k in ('story_title','genre','creative_intent','scene_title','scene_body','scene_summary')}, ensure_ascii=False)}\n\n"
            f"SHOT SPECIFICATION:\n{json.dumps(shot, ensure_ascii=False)}\n\n"
            f"ADDITIONAL CREATIVE DIRECTION:\n{payload.get('creative_direction','')}"
        )
        request = ChatCompletionRequest(
            model=model, provider_id=payload.get("provider_id"),
            messages=[{"role":"system","content":system},{"role":"user","content":user}],
            temperature=payload.get("temperature",0.5), max_tokens=payload.get("max_tokens",1600),
        )
        db = session_factory()
        try:
            try:
                response = asyncio.run(generate_chat_completion(db, request, f"storyboard-prompt:{task_id}"))
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {}
                code = detail.get("code","storyboard_prompt_provider_error")
                error = RuntimeError("AI prompt generation failed. Check the selected provider and model configuration.")
                error.error_code = code
                error.public_message = str(error)
                raise error from None
        finally:
            db.close()
        prompt = response.get("content","").strip()
        if not prompt or len(prompt) > 12000:
            raise ValueError("The AI provider returned an empty or oversized storyboard prompt.")
        return {
            "kind":"storyboard_prompt_proposal", "story_id":snapshot["story_id"],
            "shot_id":snapshot["shot_id"], "shot_version":snapshot["shot_version"],
            "model":response["model"], "prompt":prompt,
            "usage":{"prompt_tokens":response.get("prompt_tokens",0),
                     "completion_tokens":response.get("completion_tokens",0),
                     "total_tokens":response.get("total_tokens",0)},
            "review_required":True, "canonical_story_modified":False,
        }
    return handle


def apply_storyboard_prompt(db: Session, story_id: str, shot_id: str, task_id: str,
                            payload: StoryboardPromptApply) -> dict:
    task = db.get(StudioTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={"code":"task_not_found"})
    if task.task_type != "storyboard.generate_prompt":
        raise HTTPException(status_code=409, detail={"code":"task_not_storyboard_prompt"})
    if task.status != "succeeded" or not task.result_json:
        raise HTTPException(status_code=409, detail={"code":"storyboard_prompt_not_ready"})
    try:
        task_payload=json.loads(task.payload_json); result=json.loads(task.result_json)
    except (TypeError,ValueError):
        raise HTTPException(status_code=409, detail={"code":"storyboard_prompt_result_invalid"})
    snapshot=task_payload.get("snapshot") or {}
    if (task.project_id is None or snapshot.get("story_id") != story_id
        or snapshot.get("shot_id") != shot_id or result.get("kind") != "storyboard_prompt_proposal"
        or result.get("story_id") != story_id or result.get("shot_id") != shot_id
        or result.get("review_required") is not True or result.get("canonical_story_modified") is not False):
        raise HTTPException(status_code=409, detail={"code":"storyboard_prompt_scope_mismatch"})
    shot=db.get(StoryboardShot,shot_id)
    if shot is None or shot.story_id != story_id:
        raise HTTPException(status_code=404, detail={"code":"storyboard_shot_not_found"})
    if shot.version != payload.expected_version or shot.version != snapshot.get("shot_version"):
        raise HTTPException(status_code=409, detail={"code":"storyboard_shot_version_conflict","current_version":shot.version})
    prompt=result.get("prompt")
    if not isinstance(prompt,str) or not prompt.strip() or len(prompt)>12000:
        raise HTTPException(status_code=422, detail={"code":"storyboard_prompt_invalid"})
    if result.get("applied_at"):
        raise HTTPException(status_code=409, detail={"code":"storyboard_prompt_already_applied"})
    marked=dict(result);marked["applied_at"]=datetime.now(timezone.utc).isoformat()
    previous=task.result_json
    claimed=db.execute(update(StudioTask).where(StudioTask.id==task_id,StudioTask.result_json==previous)
                       .values(result_json=json.dumps(marked,ensure_ascii=False,separators=(",",":"))))
    if claimed.rowcount != 1:
        raise HTTPException(status_code=409, detail={"code":"storyboard_prompt_already_applied"})
    shot.prompt=prompt.strip()
    shot.version+=1
    shot.approved_take_id=None
    shot.updated_at=datetime.now(timezone.utc)
    db.commit();db.refresh(shot)
    return {"id":shot.id,"prompt":shot.prompt,"version":shot.version,
            "approved_take_id":shot.approved_take_id,"applied":True}
