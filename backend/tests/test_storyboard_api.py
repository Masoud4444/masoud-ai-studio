import json
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.main import app
from backend.app.models import StudioTask, StoryboardShot
from backend.app import storage


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "STORAGE_ROOT", tmp_path / "storage")
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    testing_session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(bind=engine)

    def override_get_db():
        db = testing_session()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        test_client.testing_session = testing_session
        yield test_client
    app.dependency_overrides.clear()
    Base.metadata.drop_all(bind=engine)
    engine.dispose()


def _story_with_scene(client, project_name="Storyboard test"):
    project_response = client.post("/api/v1/projects", json={"name": project_name})
    assert project_response.status_code == 201
    project = project_response.json()
    story_response = client.post("/api/v1/stories", json={"project_id": project["id"], "title": "The Signal"})
    assert story_response.status_code == 201
    story = story_response.json()
    scene_response = client.post(
        f"/api/v1/stories/{story['id']}/scenes",
        json={"title": "The doorway", "body": "Mira opens the door. A light flickers."},
    )
    assert scene_response.status_code == 201
    return project, story, scene_response.json()["scene"]


def _shot_payload(scene_id, title, excerpt="Mira opens the door."):
    return {"scene_id": scene_id, "title": title, "source_excerpt": excerpt, "shot_size": "ms"}


def test_storyboard_shot_lifecycle_is_scene_scoped_and_versioned(client):
    _, story, scene = _story_with_scene(client)
    base = f"/api/v1/stories/{story['id']}"
    first = client.post(f"{base}/storyboard/shots", json=_shot_payload(scene["id"], "Doorway master"))
    second = client.post(f"{base}/storyboard/shots", json=_shot_payload(scene["id"], "Reaction close-up", "A light flickers."))
    assert first.status_code == 201
    assert second.status_code == 201
    assert first.json()["position"] == 1
    assert second.json()["position"] == 2
    assert first.json()["source_excerpt"] == "Mira opens the door."

    listed = client.get(f"{base}/scenes/{scene['id']}/storyboard")
    assert listed.status_code == 200
    assert [item["title"] for item in listed.json()["items"]] == ["Doorway master", "Reaction close-up"]

    updated = client.patch(
        f"{base}/storyboard/shots/{first.json()['id']}",
        json={"expected_version": 1, "camera_movement": "dolly_in", "lens": "35mm"},
    )
    assert updated.status_code == 200
    assert updated.json()["version"] == 2
    assert updated.json()["camera_movement"] == "dolly_in"
    conflict = client.patch(
        f"{base}/storyboard/shots/{first.json()['id']}",
        json={"expected_version": 1, "title": "Stale edit"},
    )
    assert conflict.status_code == 409


def test_storyboard_rejects_scene_from_another_story(client):
    _, story, _ = _story_with_scene(client, "First project")
    _, _, foreign_scene = _story_with_scene(client, "Second project")
    response = client.post(
        f"/api/v1/stories/{story['id']}/storyboard/shots",
        json=_shot_payload(foreign_scene["id"], "Cross-story shot"),
    )
    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "story_scene_not_found"


def test_storyboard_rejects_excerpt_not_present_in_canonical_scene(client):
    _, story, scene = _story_with_scene(client)
    response = client.post(
        f"/api/v1/stories/{story['id']}/storyboard/shots",
        json=_shot_payload(scene["id"], "Invented beat", "Mira suddenly flies away."),
    )
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "source_excerpt_not_found_in_scene"


def test_storyboard_take_must_reference_project_asset_and_be_reviewed(client):
    project, story, scene = _story_with_scene(client, "Take lifecycle")
    shot = client.post(
        f"/api/v1/stories/{story['id']}/storyboard/shots",
        json=_shot_payload(scene["id"], "Doorway master"),
    ).json()
    uploaded = client.post(
        f"/api/v1/projects/{project['id']}/assets",
        files={"file": ("frame.png", b"\x89PNG\r\n\x1a\nframe-bytes", "image/png")},
    )
    assert uploaded.status_code == 201
    asset_id = uploaded.json()["asset_id"]

    take_url = f"/api/v1/stories/{story['id']}/storyboard/shots/{shot['id']}/takes"
    created = client.post(take_url, json={"asset_id": asset_id, "engine_key": "manual"})
    assert created.status_code == 201
    take = created.json()["takes"][0]
    assert take["status"] == "generated"

    take_review_url = f"{take_url}/{take['id']}"
    premature_approval = client.patch(take_review_url, json={"status": "approved"})
    assert premature_approval.status_code == 409

    selected = client.patch(take_review_url, json={"status": "selected", "review_note": "Best framing"})
    assert selected.status_code == 200
    approved = client.patch(take_review_url, json={"status": "approved"})
    assert approved.status_code == 200
    assert approved.json()["approved_take_id"] == take["id"]
    assert approved.json()["takes"][0]["status"] == "approved"



def test_storyboard_ai_prompt_task_is_review_first_and_applies_to_current_shot(client):
    project, story, scene = _story_with_scene(client, "AI storyboard prompt")
    base = f"/api/v1/stories/{story['id']}"
    shot = client.post(
        f"{base}/storyboard/shots",
        json=_shot_payload(scene["id"], "Mira opens the door"),
    ).json()
    queued = client.post(
        f"{base}/storyboard/shots/{shot['id']}/prompt-tasks",
        headers={"Idempotency-Key": "storyboard-prompt-0001"},
        json={"model": "test-model", "creative_direction": "Naturalistic, restrained lighting."},
    )
    assert queued.status_code == 201
    task = queued.json()
    assert task["task_type"] == "storyboard.generate_prompt"
    assert task["status"] == "queued"
    assert task["payload"]["snapshot"]["shot_version"] == 1
    assert task["payload"]["snapshot"]["shot"]["source_excerpt"] == "Mira opens the door."
    with client.testing_session() as db:
        row = db.get(StudioTask, task["id"])
        row.status = "succeeded"
        row.result_json = json.dumps({
            "kind": "storyboard_prompt_proposal",
            "story_id": story["id"],
            "shot_id": shot["id"],
            "shot_version": 1,
            "model": "test-model",
            "prompt": "A restrained cinematic medium shot of Mira opening the doorway, natural window light.",
            "usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            "review_required": True,
            "canonical_story_modified": False,
        })
        db.commit()
    applied = client.post(
        f"{base}/storyboard/shots/{shot['id']}/prompt-tasks/{task['id']}/apply",
        json={"expected_version": 1},
    )
    assert applied.status_code == 200
    assert applied.json()["applied"] is True
    assert applied.json()["version"] == 2
    assert "cinematic medium shot" in applied.json()["prompt"]
    with client.testing_session() as db:
        saved = db.get(StoryboardShot, shot["id"])
        assert saved.prompt == applied.json()["prompt"]
        assert saved.approved_take_id is None


def test_storyboard_ai_prompt_apply_rejects_stale_shot_version(client):
    _, story, scene = _story_with_scene(client, "Stale AI storyboard prompt")
    base = f"/api/v1/stories/{story['id']}"
    shot = client.post(f"{base}/storyboard/shots", json=_shot_payload(scene["id"], "Doorway")).json()
    queued = client.post(
        f"{base}/storyboard/shots/{shot['id']}/prompt-tasks",
        headers={"Idempotency-Key": "storyboard-prompt-0002"},
        json={"model": "test-model"},
    ).json()
    with client.testing_session() as db:
        row = db.get(StudioTask, queued["id"])
        row.status = "succeeded"
        row.result_json = json.dumps({
            "kind": "storyboard_prompt_proposal", "story_id": story["id"],
            "shot_id": shot["id"], "shot_version": 1, "model": "test-model",
            "prompt": "A cinematic doorway shot.", "review_required": True,
            "canonical_story_modified": False,
        })
        db.get(StoryboardShot, shot["id"]).version = 2
        db.commit()
    response = client.post(
        f"{base}/storyboard/shots/{shot['id']}/prompt-tasks/{queued['id']}/apply",
        json={"expected_version": 2},
    )
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "storyboard_shot_version_conflict"
