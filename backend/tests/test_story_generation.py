import asyncio

from backend.app import story_generation


class DummySession:
    def close(self):
        pass


def test_outline_messages_require_structured_review_first_output():
    messages = story_generation._build_messages({
        "story": {"story_id": "story-1", "title": "The Signal", "format": "short_film"},
        "brief": "A quiet science-fiction drama about responsibility.",
    })
    assert messages[0]["role"] == "system"
    assert "Return valid JSON only" in messages[0]["content"]
    assert "do not modify canonical story records" in messages[0]["content"].lower() or "proposal only" in messages[1]["content"]
    assert "The Signal" in messages[1]["content"]


def test_outline_handler_calls_gateway_idempotently_and_returns_review_only(monkeypatch):
    calls = {}

    async def fake_generate(db, request, idempotency_key):
        calls["model"] = request.model
        calls["key"] = idempotency_key
        calls["messages"] = request.messages
        return {
            "model": request.model, "content": '{"logline":"A signal changes everything.","scenes":[]}',
            "prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30,
        }

    monkeypatch.setattr(story_generation, "generate_chat_completion", fake_generate)
    handler = story_generation.build_story_outline_handler(lambda: DummySession())
    result = handler({
        "story": {"story_id": "story-1", "title": "The Signal"},
        "brief": "Make it emotionally grounded.",
        "model": "test-model",
        "provider_id": None,
        "temperature": 0.7,
        "max_tokens": 1000,
        "_studio_task": {"id": "task-123"},
    })

    assert calls["model"] == "test-model"
    assert calls["key"] == "story-outline:task-123"
    assert result["kind"] == "story_outline_proposal"
    assert result["review_required"] is True
    assert result["canonical_story_modified"] is False
    assert result["usage"]["total_tokens"] == 30
    assert result["content"].startswith('{"logline"')


def test_outline_handler_rejects_missing_worker_task_id():
    handler = story_generation.build_story_outline_handler(lambda: DummySession())
    try:
        handler({"story": {"story_id": "story-1"}, "model": "test-model"})
    except ValueError as exc:
        assert "task id" in str(exc)
    else:
        raise AssertionError("Expected missing task id to be rejected")
