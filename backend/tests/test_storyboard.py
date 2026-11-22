from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from backend.app.storyboard_schemas import StoryboardShotCreate, StoryboardShotUpdate
from backend.app.storyboard_engine import _validate_evidence


def _shot_payload(**overrides):
    values = {
        "scene_id": "00000000-0000-0000-0000-000000000001",
        "title": "Doorway reveal",
        "source_excerpt": "Mira opens the door.",
    }
    values.update(overrides)
    return values


def test_storyboard_shot_requires_screenplay_evidence():
    with pytest.raises(ValidationError):
        StoryboardShotCreate.model_validate({"scene_id": "x" * 36, "title": "Unsupported shot"})


def test_storyboard_source_offsets_must_be_supplied_as_a_pair():
    with pytest.raises(ValidationError):
        StoryboardShotCreate.model_validate(_shot_payload(source_start=0))


def test_storyboard_source_range_cannot_be_reversed():
    with pytest.raises(ValidationError):
        StoryboardShotCreate.model_validate(_shot_payload(source_start=12, source_end=4))


def test_storyboard_evidence_must_match_exact_scene_text():
    payload = StoryboardShotCreate.model_validate(_shot_payload())
    scene = SimpleNamespace(body="Mira opens the door. A light flickers.", summary=None, beats_json="[]")
    _validate_evidence(scene, payload)


def test_storyboard_rejects_invented_or_untraceable_evidence():
    payload = StoryboardShotCreate.model_validate(_shot_payload(source_excerpt="Mira flies into space."))
    scene = SimpleNamespace(body="Mira opens the door.", summary=None, beats_json="[]")
    with pytest.raises(HTTPException) as exc:
        _validate_evidence(scene, payload)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "source_excerpt_not_found_in_scene"


def test_storyboard_offset_range_must_match_exact_excerpt():
    payload = StoryboardShotCreate.model_validate(_shot_payload(source_start=0, source_end=5))
    scene = SimpleNamespace(body="Mira opens the door.", summary=None, beats_json="[]")
    with pytest.raises(HTTPException) as exc:
        _validate_evidence(scene, payload)
    assert exc.value.status_code == 422
    assert exc.value.detail["code"] == "source_excerpt_does_not_match_scene_range"


def test_storyboard_shot_update_requires_optimistic_version():
    with pytest.raises(ValidationError):
        StoryboardShotUpdate.model_validate({"title": "Updated shot"})
