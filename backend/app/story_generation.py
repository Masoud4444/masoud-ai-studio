"""Review-first, worker-backed AI story outline generation."""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select, update
from .character_world import Character, Location, Relationship, WorldRule, SceneCharacter, SceneLocation
from .continuity import ContinuityFact
from .props import StoryProp
from sqlalchemy.orm import Session, sessionmaker

from .ai_gateway import generate_chat_completion
from .gateway_schemas import ChatCompletionRequest
from .models import Project, Story, StoryScene, StudioTask
from .story_schemas import StoryOutlineTaskCreate, StoryOutlineProposal, StoryOutlineApply
from .story_engine import apply_outline_proposal
from .task_manager import create_task


def _decode_json_field(value: Any) -> Any:
    """Decode JSON-backed Bible fields before embedding them in model context."""
    if not isinstance(value, str):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        # Preserve legacy free-form values rather than silently dropping canon.
        return value


def create_story_outline_task(
    db: Session, story_id: str, payload: StoryOutlineTaskCreate, idempotency_key: str
) -> dict:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail={"code": "story_not_found"})
    project = db.get(Project, story.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"code": "project_not_found"})
    if project.status != "active" or story.status in {"archived", "locked"}:
        raise HTTPException(status_code=409, detail={"code": "story_not_active"})

    scenes = db.query(StoryScene).filter(
        StoryScene.story_id == story.id
    ).order_by(StoryScene.position.asc()).all()
    # Capture the canonical story bible at task creation time. The worker receives
    # a bounded, immutable context snapshot and never queries mutable story records.
    characters = db.scalars(select(Character).where(Character.story_id == story.id).order_by(Character.name).limit(60)).all()
    locations = db.scalars(select(Location).where(Location.story_id == story.id).order_by(Location.name).limit(60)).all()
    relationships = db.scalars(select(Relationship).where(Relationship.story_id == story.id).limit(120)).all()
    world_rules = db.scalars(select(WorldRule).where(WorldRule.story_id == story.id).limit(100)).all()
    props = db.scalars(select(StoryProp).where(StoryProp.story_id == story.id).order_by(StoryProp.name).limit(100)).all()
    continuity_facts = db.scalars(
        select(ContinuityFact).where(
            ContinuityFact.story_id == story.id, ContinuityFact.active.is_(True)
        ).order_by(ContinuityFact.created_at.desc()).limit(150)
    ).all()
    character_ids = [item.id for item in characters]
    location_ids = [item.id for item in locations]
    scene_character_links = db.scalars(
        select(SceneCharacter).join(StoryScene, StoryScene.id == SceneCharacter.scene_id).where(\n            StoryScene.story_id == story.id, SceneCharacter.character_id.in_(character_ids)\n        ).limit(300)
    ).all() if character_ids else []
    scene_location_links = db.scalars(
        select(SceneLocation).join(StoryScene, StoryScene.id == SceneLocation.scene_id).where(\n            StoryScene.story_id == story.id, SceneLocation.location_id.in_(location_ids)\n        ).limit(300)
    ).all() if location_ids else []
    bible_context = {
        "characters": [{
            "id": item.id, "name": item.name, "role": item.role, "age": item.age,
            "appearance": _decode_json_field(item.appearance_json), "psychology": _decode_json_field(item.psychology_json),
            "backstory": item.backstory, "goals": item.goals, "conflict": item.conflict,
            "arc": item.arc, "voice_notes": item.voice_notes,
        } for item in characters],
        "relationships": [{
            "source_id": item.source_id, "target_id": item.target_id,
            "kind": item.kind, "description": item.description,
        } for item in relationships],
        "locations": [{
            "id": item.id, "name": item.name, "type": item.location_type,
            "description": item.description, "geography": item.geography_json,
            "culture": item.culture_json,
        } for item in locations],
        "world_rules": [{
            "category": item.category, "statement": item.statement,
            "rationale": item.rationale,
        } for item in world_rules],
        "props": [{
            "id": item.id, "name": item.name, "category": item.category,
            "description": item.description, "origin": item.origin,
            "initial_state": item.initial_state, "current_holder_id": item.current_holder_id,
            "status": item.status,
        } for item in props],
        "scene_character_links": [{
            "scene_id": item.scene_id, "character_id": item.character_id,
            "presence_type": item.presence_type, "note": item.note,
        } for item in scene_character_links],
        "scene_location_links": [{
            "scene_id": item.scene_id, "location_id": item.location_id, "note": item.note,
        } for item in scene_location_links],
        "active_continuity_facts": [{
            "scene_id": item.scene_id, "subject_type": item.subject_type,
            "subject_ref": item.subject_ref, "subject_label": item.subject_label,
            "attribute": item.attribute, "value": item.value,
            "transition_note": item.transition_note, "evidence_note": item.evidence_note,
        } for item in continuity_facts],
    }
    snapshot = {
        "story_id": story.id,
        "canonical_bible": bible_context,
        "story_version": story.version,
        "project_id": story.project_id,
        "title": story.title,
        "format": story.format,
        "genre": story.genre,
        "target_audience": story.target_audience,
        "premise": story.premise,
        "logline": story.logline,
        "synopsis": story.synopsis,
        "creative_intent": story.creative_intent,
        "existing_scenes": [
            {"position": item.position, "title": item.title, "summary": item.summary,
             "slugline": item.slugline, "dramatic_purpose": item.dramatic_purpose,
             "beats": item.beats_json}
            for item in scenes
        ],
    }
    return create_task(
        db,
        task_type="story.generate_outline",
        payload={
            "story": snapshot,
            "brief": payload.brief.strip(),
            "model": payload.model.strip(),
            "provider_id": payload.provider_id,
            "temperature": payload.temperature,
            "max_tokens": payload.max_tokens,
        },
        idempotency_key=idempotency_key,
        project_id=story.project_id,
        execution_mode="local",
        estimated_duration_seconds=45,
    )


def _build_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    story = payload.get("story") or {}
    return [
        {
            "role": "system",
            "content": (
                "You are a senior story editor and dramaturg working inside a professional creative studio. "
                "Develop a coherent, original, human-relevant story outline. Preserve the supplied premise and "
                "creative intent and canonical Bible. Treat character psychology, backstory, goals, "
                "relationships, world rules, locations, props and active continuity facts as binding constraints. "
                "Do not silently rename, contradict, merge or invent canonical characters, places, objects or rules. "
                "If the brief requires a deliberate canon change, flag it in the synopsis rather than silently "
                "rewriting the Bible. Respect existing scene-character and scene-location links. Do not invent "
                "factual claims about real people or events. Avoid clichés, unearned emotional manipulation, "
                "generic moralizing and filler. Identify meaningful audience engagement and character agency. "
                "Return valid JSON only, with keys: "
                "logline, synopsis, central_question, human_value, act_structure (array of objects with "
                "act, purpose, turning_point), and scenes (array of objects with title, slugline, summary, "
                "dramatic_purpose, beats array). Do not include markdown fences."
            ),
        },
        {
            "role": "user",
            "content": (
                "Develop an outline from this story dossier and creative brief. This is a proposal only; "
                "do not assume it is approved or modify canonical story records.\n\n"
                f"STORY DOSSIER AND CANONICAL BIBLE:\n{story!r}\n\nCREATIVE BRIEF:\n{payload.get('brief', '')}\n\n"
                "When no canonical entries exist, create new characters and locations only when useful. "
                "For each scene, use existing character/location identities where applicable and avoid "
                "continuity conflicts with the supplied active facts."
            ),
        },
    ]


def build_story_outline_handler(session_factory: sessionmaker):
    def handle(payload: dict[str, Any]) -> dict[str, Any]:
        task_meta = payload.get("_studio_task") or {}
        task_id = task_meta.get("id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("A worker task id is required")
        model = payload.get("model")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("A model identifier is required")

        request = ChatCompletionRequest(
            model=model,
            provider_id=payload.get("provider_id"),
            messages=_build_messages(payload),
            temperature=payload.get("temperature", 0.7),
            max_tokens=payload.get("max_tokens", 4000),
        )
        db = session_factory()
        try:
            try:
                response = asyncio.run(
                    generate_chat_completion(db, request, f"story-outline:{task_id}")
                )
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {}
                code = detail.get("code", "story_outline_provider_error")
                public_messages = {
                    "model_provider_not_found": "The selected AI model is not available in the configured providers.",
                    "credential_encryption_not_configured": "Configure the local credential encryption key before using AI generation.",
                    "provider_rate_limited": "The AI provider rate-limited this request. Retry later.",
                    "provider_unavailable": "The configured AI provider is temporarily unavailable.",
                    "provider_timeout": "The AI provider timed out. Retry the task.",
                }
                error = RuntimeError(public_messages.get(code, "AI outline generation failed. Check provider configuration."))
                error.error_code = code
                error.public_message = str(error)
                raise error from None
        finally:
            db.close()

        return {
            "kind": "story_outline_proposal",
            "story_id": payload["story"]["story_id"],
            "model": response["model"],
            "content": response["content"],
            "proposal": parse_story_outline_content(response["content"]),
            "usage": {
                "prompt_tokens": response.get("prompt_tokens", 0),
                "completion_tokens": response.get("completion_tokens", 0),
                "total_tokens": response.get("total_tokens", 0),
            },
            "review_required": True,
            "canonical_story_modified": False,
        }

    return handle



def parse_story_outline_content(content: str) -> dict[str, Any]:
    if not isinstance(content, str) or not content.strip():
        raise ValueError("The AI provider returned an empty story outline.")
    candidate = content.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()
    try:
        decoded = json.loads(candidate)
    except (TypeError, ValueError):
        raise ValueError("The AI response was not valid JSON. Retry generation with a JSON-capable model.") from None
    try:
        return StoryOutlineProposal.model_validate(decoded).model_dump()
    except Exception:
        raise ValueError("The AI response did not match the required story outline structure. Retry generation.") from None


def apply_story_outline_task(
    db: Session, story_id: str, task_id: str, payload: StoryOutlineApply
) -> dict:
    task = db.get(StudioTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "task_not_found"})
    if task.task_type != "story.generate_outline":
        raise HTTPException(status_code=409, detail={"code": "task_not_story_outline"})
    if task.status != "succeeded" or not task.result_json:
        raise HTTPException(status_code=409, detail={"code": "story_outline_not_ready"})
    if not task.project_id:
        raise HTTPException(status_code=409, detail={"code": "story_outline_project_missing"})
    try:
        task_payload = json.loads(task.payload_json)
        result = json.loads(task.result_json)
    except (TypeError, ValueError):
        raise HTTPException(status_code=409, detail={"code": "story_outline_result_invalid"}) from None
    if (task_payload.get("story", {}).get("story_id") != story_id
            or result.get("story_id") != story_id
            or result.get("kind") != "story_outline_proposal"
            or result.get("review_required") is not True):
        raise HTTPException(status_code=409, detail={"code": "story_outline_scope_mismatch"})
    if result.get("canonical_story_modified") is not False:
        raise HTTPException(status_code=409, detail={"code": "story_outline_result_invalid"})
    if result.get("applied_at"):
        raise HTTPException(status_code=409, detail={"code": "story_outline_already_applied"})
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail={"code": "story_not_found"})
    if story.project_id != task.project_id:
        raise HTTPException(status_code=409, detail={"code": "story_outline_project_mismatch"})
    if task_payload.get("story", {}).get("story_version") != story.version:
        raise HTTPException(status_code=409, detail={"code": "story_outline_stale"})
    try:
        validated = StoryOutlineProposal.model_validate(result.get("proposal")).model_dump()
    except Exception:
        raise HTTPException(status_code=422, detail={"code": "story_outline_proposal_invalid"}) from None
    result["applied_at"] = datetime.now(timezone.utc).isoformat()
    marked_result = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    claimed = db.execute(
        update(StudioTask)
        .where(StudioTask.id == task_id, StudioTask.result_json == task.result_json)
        .values(result_json=marked_result)
    )
    if claimed.rowcount != 1:
        raise HTTPException(status_code=409, detail={"code": "story_outline_already_applied"})
    task.result_json = marked_result
    story_result = apply_outline_proposal(db, story_id, payload.expected_version, validated, commit=False)
    db.commit()
    return story_result
