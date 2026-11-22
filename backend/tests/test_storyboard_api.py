import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app.database import Base, get_db
from backend.app.main import app


@pytest.fixture()
def client():
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
