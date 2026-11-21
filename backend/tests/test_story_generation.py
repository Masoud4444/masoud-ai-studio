import json

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
            "model": request.model, "content": json.dumps({
                "logline": "A signal changes everything.",
                "synopsis": "A technician must decide whether to answer.",
                "central_question": "Who deserves a response?",
                "human_value": "Empathy",
                "act_structure": [{"act": "One", "purpose": "Setup", "turning_point": "The signal repeats"}],
                "scenes": [{"title": "First contact", "slugline": "INT. RADIO ROOM - NIGHT",
                            "summary": "A signal arrives.", "dramatic_purpose": "Introduce the mystery.",
                            "beats": ["Listen", "Respond"]}],
            }),
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
    assert result["proposal"]["scenes"][0]["title"] == "First contact"


def test_outline_handler_rejects_missing_worker_task_id():
    handler = story_generation.build_story_outline_handler(lambda: DummySession())
    try:
        handler({"story": {"story_id": "story-1"}, "model": "test-model"})
    except ValueError as exc:
        assert "task id" in str(exc)
    else:
        raise AssertionError("Expected missing task id to be rejected")



def test_outline_parser_accepts_fenced_json_and_normalizes_fields():
    proposal = {
        "logline": "A signal changes everything.",
        "synopsis": "A technician must decide whether to answer.",
        "central_question": "Who deserves a response?",
        "human_value": "Empathy",
        "act_structure": [{"act": "One", "purpose": "Setup", "turning_point": "The signal repeats"}],
        "scenes": [{"title": "First contact", "summary": "A signal arrives.", "beats": ["Listen", "Respond"]}],
    }
    parsed = story_generation.parse_story_outline_content(" ```json\n" + json.dumps(proposal) + "\n``` ")
    assert parsed["scenes"][0]["title"] == "First contact"
    assert parsed["scenes"][0]["slugline"] is None


def test_outline_parser_rejects_invalid_or_incomplete_json():
    for content in ("not json", '{"logline":"Only a logline"}'):
        try:
            story_generation.parse_story_outline_content(content)
        except ValueError:
            pass
        else:
            raise AssertionError("Expected invalid outline content to be rejected")



def _valid_outline_proposal():
    return {
        "logline": "A signal changes everything.",
        "synopsis": "A technician must decide whether to answer.",
        "central_question": "Who deserves a response?",
        "human_value": "Empathy",
        "act_structure": [{"act": "One", "purpose": "Setup", "turning_point": "The signal repeats"}],
        "scenes": [{"title": "First contact", "summary": "A signal arrives.", "beats": ["Listen"]}],
    }


def test_outline_apply_is_scoped_versioned_and_one_time(monkeypatch):
    import json
    from types import SimpleNamespace
    from fastapi import HTTPException
    from backend.app.models import StudioTask
    from backend.app.story_schemas import StoryOutlineApply

    task = SimpleNamespace(
        id="task-1", task_type="story.generate_outline", status="succeeded", project_id="project-1",
        payload_json=json.dumps({"story": {"story_id": "story-1", "story_version": 3}}),
        result_json=json.dumps({
            "kind": "story_outline_proposal", "story_id": "story-1", "review_required": True,
            "canonical_story_modified": False, "proposal": _valid_outline_proposal(),
        }),
    )
    story = SimpleNamespace(project_id="project-1", version=3)
    class FakeDB:
        def __init__(self): self.commits = 0
        def get(self, model, _id): return task if model is StudioTask else story
        def execute(self, _statement): return SimpleNamespace(rowcount=1)
        def commit(self): self.commits += 1
    db = FakeDB()
    monkeypatch.setattr(story_generation, "apply_outline_proposal",
                        lambda *_args, **_kwargs: {"version": 4, "scene_count": 1})

    result = story_generation.apply_story_outline_task(
        db, "story-1", "task-1", StoryOutlineApply(expected_version=3)
    )
    assert result["version"] == 4
    assert db.commits == 1
    assert json.loads(task.result_json)["applied_at"]

    try:
        story_generation.apply_story_outline_task(
            db, "story-1", "task-1", StoryOutlineApply(expected_version=4)
        )
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail["code"] == "story_outline_already_applied"
    else:
        raise AssertionError("An applied outline must not be applied twice")


def test_outline_apply_rejects_stale_story_snapshot(monkeypatch):
    import json
    from types import SimpleNamespace
    from fastapi import HTTPException
    from backend.app.models import StudioTask
    from backend.app.story_schemas import StoryOutlineApply

    task = SimpleNamespace(
        task_type="story.generate_outline", status="succeeded", project_id="project-1",
        payload_json=json.dumps({"story": {"story_id": "story-1", "story_version": 2}}),
        result_json=json.dumps({
            "kind": "story_outline_proposal", "story_id": "story-1", "review_required": True,
            "canonical_story_modified": False, "proposal": _valid_outline_proposal(),
        }),
    )
    story = SimpleNamespace(project_id="project-1", version=3)
    class FakeDB:
        def get(self, model, _id): return task if model is StudioTask else story
    try:
        story_generation.apply_story_outline_task(
            FakeDB(), "story-1", "task-1", StoryOutlineApply(expected_version=3)
        )
    except HTTPException as exc:
        assert exc.status_code == 409
        assert exc.detail["code"] == "story_outline_stale"
    else:
        raise AssertionError("A proposal generated from an older story version must be rejected")


def test_apply_outline_persists_human_value_question_and_act_structure():
    from types import SimpleNamespace
    from backend.app.models import Project, StoryScene
    from backend.app.story_engine import apply_outline_proposal
    from backend.app.story_schemas import StoryOutlineProposal

    story = SimpleNamespace(
        id="story-1", project_id="project-1", version=1, status="development",
        logline="Old logline", synopsis="Old synopsis", central_question=None,
        human_value=None, act_structure_json="[]", title="The Signal",
        format="short_film", genre=None, target_audience=None, premise=None,
        creative_intent="Preserve the original creative intent",
        created_at=None, updated_at=None,
    )
    project = SimpleNamespace(status="active")
    class Rows:
        def __init__(self, rows): self.rows = rows
        def all(self): return self.rows
    class FakeDB:
        def __init__(self): self.scenes=[]; self.revisions=[]
        def get(self, model, _id): return project if model is Project else story
        def scalar(self, _query): return 0
        def scalars(self, query): return Rows(self.revisions if "story_revisions" in str(query) else self.scenes)
        def add(self, item):
            if isinstance(item, StoryScene): self.scenes.append(item)
            else: self.revisions.append(item)
        def flush(self): pass
        def commit(self): pass
        def refresh(self, _item): pass

    proposal = StoryOutlineProposal.model_validate(_valid_outline_proposal()).model_dump()
    proposal["central_question"] = "Who deserves a response?"
    proposal["human_value"] = "Empathy and responsibility"
    proposal["act_structure"] = [{
        "act": "Act One", "purpose": "Introduce the signal",
        "turning_point": "The signal reveals a human voice",
    }]
    db = FakeDB()
    result = apply_outline_proposal(db, "story-1", 1, proposal)
    assert story.central_question == "Who deserves a response?"
    assert story.human_value == "Empathy and responsibility"
    assert json.loads(story.act_structure_json)[0]["act"] == "Act One"
    assert result["central_question"] == story.central_question
    assert result["human_value"] == story.human_value
    assert result["act_structure"][0]["turning_point"] == "The signal reveals a human voice"


def test_outline_prompt_uses_canonical_bible_as_binding_context():
    messages = story_generation._build_messages({
        "story": {
            "story_id": "story-1",
            "title": "The Signal",
            "canonical_bible": {
                "characters": [{"id": "c1", "name": "Mara", "goals": "Protect the archive"}],
                "relationships": [{"source_id": "c1", "target_id": "c2", "kind": "siblings"}],
                "world_rules": [{"statement": "No signal crosses the valley after dusk"}],
                "active_continuity_facts": [{"attribute": "injury", "value": "left hand bandaged"}],
            },
        },
        "brief": "Write a tense second act.",
    })
    system = messages[0]["content"].lower()
    user = messages[1]["content"]
    assert "canonical bible" in system
    assert "binding constraints" in system
    assert "Mara" in user
    assert "left hand bandaged" in user
    assert "No signal crosses the valley after dusk" in user



def test_decode_json_backed_bible_fields_preserves_structure_and_legacy_text():
    nested = {"silhouette": "angular", "palette": ["umber", "blue"]}
    assert story_generation._decode_json_field(json.dumps(nested)) == nested
    assert story_generation._decode_json_field("legacy free-form note") == "legacy free-form note"
    assert story_generation._decode_json_field(None) is None
