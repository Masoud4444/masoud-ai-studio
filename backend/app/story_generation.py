"""Review-first, worker-backed AI story outline generation."""
import asyncio
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session, sessionmaker

from .ai_gateway import generate_chat_completion
from .gateway_schemas import ChatCompletionRequest
from .models import Project, Story, StoryScene
from .story_schemas import StoryOutlineTaskCreate
from .task_manager import create_task


def create_story_outline_task(
    db: Session, story_id: str, payload: StoryOutlineTaskCreate, idempotency_key: str
) -> dict:
    story = db.get(Story, story_id)
    if story is None:
        raise HTTPException(status_code=404, detail={"code": "story_not_found"})
    project = db.get(Project, story.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail={"code": "project_not_found"})
    if project.status != "active" or story.status == "archived":
        raise HTTPException(status_code=409, detail={"code": "story_not_active"})

    scenes = db.query(StoryScene).filter(
        StoryScene.story_id == story.id
    ).order_by(StoryScene.position.asc()).all()
    snapshot = {
        "story_id": story.id,
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
                "creative intent; do not invent factual claims about real people or events. Avoid clichés, "
                "unearned emotional manipulation, generic moralizing and filler. Identify meaningful audience "
                "engagement and character agency where appropriate. Return valid JSON only, with keys: "
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
                f"STORY DOSSIER:\n{story!r}\n\nCREATIVE BRIEF:\n{payload.get('brief', '')}"
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
            "usage": {
                "prompt_tokens": response.get("prompt_tokens", 0),
                "completion_tokens": response.get("completion_tokens", 0),
                "total_tokens": response.get("total_tokens", 0),
            },
            "review_required": True,
            "canonical_story_modified": False,
        }

    return handle
