"""Review-first, worker-backed AI story outline generation."""
import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import HTTPException
from sqlalchemy import func, select, update
from .character_world import Character, Location, Relationship, WorldRule, SceneCharacter, SceneLocation
from .continuity import ContinuityFact
from .props import StoryProp
from sqlalchemy.orm import Session, sessionmaker

from .ai_gateway import generate_chat_completion
from .gateway_schemas import ChatCompletionRequest
from .models import Project, Story, StoryScene, StudioTask
from .story_schemas import (StoryOutlineTaskCreate, StoryOutlineProposal, StoryOutlineApply,
    StorySceneGenerationTaskCreate, StorySceneGenerationProposal, StorySceneGenerationApply)
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
    # Scene links are scoped through StoryScene to prevent cross-story context leakage.
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
        select(SceneCharacter).join(StoryScene, StoryScene.id == SceneCharacter.scene_id).where(
            StoryScene.story_id == story.id, SceneCharacter.character_id.in_(character_ids)
        ).limit(300)
    ).all() if character_ids else []
    scene_location_links = db.scalars(
        select(SceneLocation).join(StoryScene, StoryScene.id == SceneLocation.scene_id).where(
            StoryScene.story_id == story.id, SceneLocation.location_id.in_(location_ids)
        ).limit(300)
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
            "description": item.description, "geography": _decode_json_field(item.geography_json),
            "culture": _decode_json_field(item.culture_json),
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



def create_story_scene_generation_task(
    db: Session, story_id: str, payload: StorySceneGenerationTaskCreate, idempotency_key: str
) -> dict:
    """Queue a bounded scene-generation proposal against an immutable story snapshot."""
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail={"code": "story_not_found"})
    project = db.get(Project, story.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"code": "project_not_found"})
    if project.status != "active" or story.status in {"archived", "locked"}:
        raise HTTPException(status_code=409, detail={"code": "story_not_active"})
    if story.version < 1:
        raise HTTPException(status_code=409, detail={"code": "story_version_invalid"})

    characters = db.scalars(
        select(Character).where(Character.story_id == story.id).order_by(Character.name).limit(60)
    ).all()
    locations = db.scalars(
        select(Location).where(Location.story_id == story.id).order_by(Location.name).limit(60)
    ).all()
    rules = db.scalars(select(WorldRule).where(WorldRule.story_id == story.id).limit(100)).all()
    facts = db.scalars(select(ContinuityFact).where(
        ContinuityFact.story_id == story.id, ContinuityFact.active.is_(True)
    ).order_by(ContinuityFact.created_at.desc()).limit(150)).all()
    scenes = db.scalars(select(StoryScene).where(
        StoryScene.story_id == story.id
    ).order_by(StoryScene.position.asc()).limit(500)).all()

    snapshot = {
        "story_id": story.id, "project_id": story.project_id, "story_version": story.version,
        "title": story.title, "format": story.format, "genre": story.genre,
        "target_audience": story.target_audience, "premise": story.premise,
        "logline": story.logline, "synopsis": story.synopsis,
        "creative_intent": story.creative_intent, "central_question": story.central_question,
        "human_value": story.human_value, "act_structure": _decode_json_field(story.act_structure_json),
        "canonical_bible": {
            "characters": [{"id": x.id, "name": x.name, "role": x.role, "goals": x.goals,
                "conflict": x.conflict, "arc": x.arc, "appearance": _decode_json_field(x.appearance_json),
                "psychology": _decode_json_field(x.psychology_json)} for x in characters],
            "locations": [{"id": x.id, "name": x.name, "type": x.location_type,
                "description": x.description, "geography": _decode_json_field(x.geography_json),
                "culture": _decode_json_field(x.culture_json)} for x in locations],
            "world_rules": [{"category": x.category, "statement": x.statement} for x in rules],
            "active_continuity_facts": [{"scene_id": x.scene_id, "subject_type": x.subject_type,
                "subject_ref": x.subject_ref, "subject_label": x.subject_label,
                "attribute": x.attribute, "value": x.value, "transition_note": x.transition_note}
                for x in facts],
        },
        "existing_scenes": [{"position": x.position, "title": x.title, "slugline": x.slugline,
            "summary": x.summary, "beats": _decode_json_field(x.beats_json)} for x in scenes],
    }
    return create_task(
        db, task_type="story.generate_scenes",
        payload={"story": snapshot, "brief": payload.brief.strip(), "scene_count": payload.scene_count,
            "model": payload.model.strip(), "provider_id": payload.provider_id,
            "temperature": payload.temperature, "max_tokens": payload.max_tokens},
        idempotency_key=idempotency_key, project_id=story.project_id,
        execution_mode="local", estimated_duration_seconds=max(45, payload.scene_count * 12),
    )


def _build_scene_generation_messages(payload: dict[str, Any]) -> list[dict[str, str]]:
    story = payload.get("story") or {}
    return [
        {"role": "system", "content": (
            "You are a senior screenwriter and story editor. Generate a precise sequence of dramatic scenes "
            "that advances the supplied story rather than replacing it. Canonical characters, locations, world "
            "rules and active continuity facts are binding. Use only the supplied character and location IDs; "
            "never invent IDs. Do not silently create new canon. Each scene must have a clear dramatic purpose, "
            "specific conflict, meaningful emotional turn, playable beats and continuity-aware transitions. "
            "Preserve character agency and avoid filler, clichés, generic moralizing and unearned emotion. "
            "Return JSON only: {scenes:[{title,slugline,summary,dramatic_purpose,location_id,time_of_day,"
            "character_ids,conflict,emotional_turn,beats,continuity_notes}]}. "
            "The number of scenes must exactly match the requested count."
        )},
        {"role": "user", "content": (
            f"STORY AND CANONICAL CONTEXT:\n{json.dumps(story, ensure_ascii=False)}\n\n"
            f"REQUESTED SCENE COUNT: {payload.get('scene_count')}\n"
            f"CREATIVE BRIEF: {payload.get('brief', '')}\n"
            "Return a review-only proposal. Do not change existing story data."
        )},
    ]


def parse_story_scene_generation_content(content: str, expected_count: int) -> dict[str, Any]:
    if not isinstance(content, str) or not content.strip():
        raise ValueError("The AI provider returned an empty scene proposal.")
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
        proposal = StorySceneGenerationProposal.model_validate(decoded).model_dump()
    except Exception:
        raise ValueError("The AI response did not match the required scene proposal structure.") from None
    if len(proposal["scenes"]) != expected_count:
        raise ValueError("The AI response returned an unexpected number of scenes.")
    return proposal


def build_story_scene_generation_handler(session_factory: sessionmaker):
    def handle(payload: dict[str, Any]) -> dict[str, Any]:
        task_id = (payload.get("_studio_task") or {}).get("id")
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("A worker task id is required")
        model = payload.get("model")
        if not isinstance(model, str) or not model.strip():
            raise ValueError("A model identifier is required")
        db = session_factory()
        try:
            request = ChatCompletionRequest(
                model=model, provider_id=payload.get("provider_id"),
                messages=_build_scene_generation_messages(payload),
                temperature=payload.get("temperature", 0.7),
                max_tokens=payload.get("max_tokens", 5000),
            )
            try:
                response = asyncio.run(generate_chat_completion(db, request, f"story-scenes:{task_id}"))
            except HTTPException as exc:
                detail = exc.detail if isinstance(exc.detail, dict) else {}
                code = detail.get("code", "story_scene_provider_error")
                error = RuntimeError("AI scene generation failed. Check provider configuration or retry.")
                error.error_code = code
                error.public_message = str(error)
                raise error from None
        finally:
            db.close()
        proposal = parse_story_scene_generation_content(response["content"], int(payload["scene_count"]))
        return {
            "kind": "story_scenes_proposal", "story_id": payload["story"]["story_id"],
            "model": response["model"], "proposal": proposal, "review_required": True,
            "canonical_story_modified": False,
            "usage": {"prompt_tokens": response.get("prompt_tokens", 0),
                "completion_tokens": response.get("completion_tokens", 0),
                "total_tokens": response.get("total_tokens", 0)},
        }
    return handle


def apply_story_scene_generation_task(
    db: Session, story_id: str, task_id: str, payload: StorySceneGenerationApply
) -> dict:
    task = db.get(StudioTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail={"code": "task_not_found"})
    if task.task_type != "story.generate_scenes":
        raise HTTPException(status_code=409, detail={"code": "task_not_story_scenes"})
    if task.status != "succeeded" or not task.result_json:
        raise HTTPException(status_code=409, detail={"code": "story_scenes_not_ready"})
    try:
        task_payload, result = json.loads(task.payload_json), json.loads(task.result_json)
    except (TypeError, ValueError):
        raise HTTPException(status_code=409, detail={"code": "story_scenes_result_invalid"}) from None
    if (task_payload.get("story", {}).get("story_id") != story_id
            or result.get("story_id") != story_id
            or result.get("kind") != "story_scenes_proposal"
            or result.get("review_required") is not True
            or result.get("canonical_story_modified") is not False):
        raise HTTPException(status_code=409, detail={"code": "story_scenes_scope_mismatch"})
    if result.get("applied_at"):
        raise HTTPException(status_code=409, detail={"code": "story_scenes_already_applied"})
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail={"code": "story_not_found"})
    if story.project_id != task.project_id:
        raise HTTPException(status_code=409, detail={"code": "story_scenes_project_mismatch"})
    if task_payload.get("story", {}).get("story_version") != story.version or payload.expected_version != story.version:
        raise HTTPException(status_code=409, detail={"code": "story_scenes_stale"})
    try:
        proposal = StorySceneGenerationProposal.model_validate(result.get("proposal")).model_dump()
    except Exception:
        raise HTTPException(status_code=422, detail={"code": "story_scenes_proposal_invalid"}) from None
    existing_count = db.scalar(select(func.count()).select_from(StoryScene).where(
        StoryScene.story_id == story_id
    )) or 0
    if existing_count + len(proposal["scenes"]) > 500:
        raise HTTPException(status_code=409, detail={"code": "story_scene_limit_exceeded"})
    character_ids = {item for scene in proposal["scenes"] for item in scene["character_ids"]}
    location_ids = {scene["location_id"] for scene in proposal["scenes"] if scene["location_id"]}
    known_characters = set(db.scalars(select(Character.id).where(
        Character.story_id == story_id, Character.id.in_(character_ids)
    )).all()) if character_ids else set()
    known_locations = set(db.scalars(select(Location.id).where(
        Location.story_id == story_id, Location.id.in_(location_ids)
    )).all()) if location_ids else set()
    if known_characters != character_ids or known_locations != location_ids:
        raise HTTPException(status_code=422, detail={"code": "story_scenes_unknown_canonical_reference"})
    from .story_engine import _bump, _payload
    for offset, item in enumerate(proposal["scenes"], 1):
        beats = list(item["beats"])
        if item["emotional_turn"]:
            beats.append("Emotional turn: " + item["emotional_turn"])
        if item["conflict"]:
            beats.append("Scene conflict: " + item["conflict"])
        if item["continuity_notes"]:
            beats.append("Continuity: " + item["continuity_notes"])
        scene = StoryScene(
            story_id=story.id, position=existing_count + offset, title=item["title"].strip(),
            slugline=item.get("slugline"), summary=item["summary"],
            dramatic_purpose=item["dramatic_purpose"],
            location=(db.get(Location, item["location_id"]).name if item.get("location_id") else None),
            time_of_day=item.get("time_of_day"), beats_json=json.dumps(beats, ensure_ascii=False),
        )
        db.add(scene)
        db.flush()
        for character_id in dict.fromkeys(item["character_ids"]):
            db.add(SceneCharacter(scene_id=scene.id, character_id=character_id))
        if item.get("location_id"):
            db.add(SceneLocation(scene_id=scene.id, location_id=item["location_id"]))
    result["applied_at"] = datetime.now(timezone.utc).isoformat()
    marked = json.dumps(result, ensure_ascii=False, separators=(",", ":"))
    claimed = db.execute(update(StudioTask).where(
        StudioTask.id == task_id, StudioTask.result_json == task.result_json
    ).values(result_json=marked))
    if claimed.rowcount != 1:
        raise HTTPException(status_code=409, detail={"code": "story_scenes_already_applied"})
    task.result_json = marked
    story.status = "drafting" if story.status in {"development", "outlined"} else story.status
    _bump(db, story, f"AI scene generation proposal applied · {len(proposal['scenes'])} scenes appended")
    db.commit()
    return _payload(db, story, True)
