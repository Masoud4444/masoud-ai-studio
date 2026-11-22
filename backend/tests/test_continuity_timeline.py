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
