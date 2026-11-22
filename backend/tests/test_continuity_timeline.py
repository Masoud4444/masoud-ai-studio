from types import SimpleNamespace

from backend.app.continuity import _timeline_cycle_details


def test_timeline_cycle_details_returns_scene_and_relation_evidence():
    events = [
        SimpleNamespace(id="event-a", scene_id="scene-a", title="Arrival", active=True),
        SimpleNamespace(id="event-b", scene_id="scene-b", title="Departure", active=True),
        SimpleNamespace(id="event-c", scene_id="scene-c", title="Aftermath", active=True),
    ]
    relations = [
        SimpleNamespace(before_event_id="event-a", after_event_id="event-b"),
        SimpleNamespace(before_event_id="event-b", after_event_id="event-a"),
        SimpleNamespace(before_event_id="event-b", after_event_id="event-c"),
    ]

    details = _timeline_cycle_details(events, relations)

    assert details is not None
    assert details["event_ids"] == ["event-a", "event-b"]
    assert details["scene_ids"] == ["scene-a", "scene-b"]
    assert len(details["relations"]) == 2


def test_timeline_cycle_details_ignores_inactive_or_disconnected_events():
    events = [
        SimpleNamespace(id="event-a", scene_id="scene-a", title="A", active=True),
        SimpleNamespace(id="event-b", scene_id="scene-b", title="B", active=True),
        SimpleNamespace(id="event-c", scene_id="scene-c", title="C", active=False),
    ]
    relations = [
        SimpleNamespace(before_event_id="event-a", after_event_id="event-b"),
        SimpleNamespace(before_event_id="event-b", after_event_id="event-c"),
    ]

    assert _timeline_cycle_details(events, relations) is None


def test_timeline_cycle_details_excludes_events_downstream_of_cycle():
    events = [
        SimpleNamespace(id="event-a", scene_id="scene-a", title="A", active=True),
        SimpleNamespace(id="event-b", scene_id="scene-b", title="B", active=True),
        SimpleNamespace(id="event-c", scene_id="scene-c", title="C", active=True),
        SimpleNamespace(id="event-d", scene_id="scene-d", title="D", active=True),
    ]
    relations = [
        SimpleNamespace(before_event_id="event-a", after_event_id="event-b"),
        SimpleNamespace(before_event_id="event-b", after_event_id="event-a"),
        SimpleNamespace(before_event_id="event-b", after_event_id="event-c"),
        SimpleNamespace(before_event_id="event-c", after_event_id="event-d"),
    ]

    details = _timeline_cycle_details(events, relations)

    assert details is not None
    assert details["event_ids"] == ["event-a", "event-b"]
    assert details["scene_ids"] == ["scene-a", "scene-b"]
    assert len(details["relations"]) == 2


def test_prop_fact_uses_canonical_registry_name():
    from backend.app.continuity import _prop_subject_label

    class FakeDB:
        def get(self, model, item_id):
            return SimpleNamespace(id=item_id, story_id="story-1", name="The Silver Key")

    assert _prop_subject_label(FakeDB(), "story-1", "prop-1", "untrusted label") == "The Silver Key"


def test_prop_fact_rejects_reference_from_another_story():
    import pytest
    from fastapi import HTTPException
    from backend.app.continuity import _prop_subject_label

    class FakeDB:
        def get(self, model, item_id):
            return SimpleNamespace(id=item_id, story_id="story-2", name="Foreign prop")

    with pytest.raises(HTTPException) as error:
        _prop_subject_label(FakeDB(), "story-1", "prop-2", "Foreign prop")

    assert error.value.status_code == 404
    assert error.value.detail["code"] == "story_prop_not_found"


def test_timeline_cycle_details_excludes_bridges_between_distinct_cycles():
    events = [
        SimpleNamespace(id=event_id, scene_id=f"scene-{event_id}", title=event_id, active=True)
        for event_id in ("a", "b", "c", "d")
    ]
    relations = [
        SimpleNamespace(before_event_id="a", after_event_id="b"),
        SimpleNamespace(before_event_id="b", after_event_id="a"),
        SimpleNamespace(before_event_id="b", after_event_id="c"),
        SimpleNamespace(before_event_id="c", after_event_id="d"),
        SimpleNamespace(before_event_id="d", after_event_id="c"),
    ]

    details = _timeline_cycle_details(events, relations)

    assert details is not None
    assert details["event_ids"] == ["a", "b", "c", "d"]
    assert details["relations"] == [
        {"before_event_id": "a", "after_event_id": "b"},
        {"before_event_id": "b", "after_event_id": "a"},
        {"before_event_id": "c", "after_event_id": "d"},
        {"before_event_id": "d", "after_event_id": "c"},
    ]


def test_timeline_cycle_details_handles_timelines_beyond_recursion_limit():
    event_ids = [f"event-{index:04d}" for index in range(1300)]
    events = [
        SimpleNamespace(id=event_id, scene_id=None, title=event_id, active=True)
        for event_id in event_ids
    ]
    relations = [
        SimpleNamespace(before_event_id=event_ids[index], after_event_id=event_ids[index + 1])
        for index in range(len(event_ids) - 1)
    ]
    relations.append(
        SimpleNamespace(before_event_id=event_ids[-1], after_event_id=event_ids[-2])
    )

    details = _timeline_cycle_details(events, relations)

    assert details is not None
    assert details["event_ids"] == event_ids[1:]
    assert len(details["relations"]) == len(event_ids) - 1
