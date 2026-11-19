"""Deterministic Fountain screenplay export from saved Story Engine records."""
import json


def _clean(value):
    if not isinstance(value, str):
        return ""
    return value.replace("\r\n", "\n").replace("\r", "\n").strip()


def render_fountain(story: dict, scenes: list[dict]) -> str:
    title = _clean(story.get("title")) or "Untitled Story"
    lines = [f"Title: {title}"]
    logline = _clean(story.get("logline"))
    if logline:
        lines.append(f"Logline: {logline}")
    lines.extend(["", ""])
    for scene in sorted(scenes, key=lambda item: item.get("position", 0)):
        scene_title = _clean(scene.get("title"))
        slugline = _clean(scene.get("slugline"))
        if scene_title:
            lines.append(f"[[Scene {scene.get('position', '')}: {scene_title}]]")
        if slugline:
            lines.append(slugline.upper())
        summary = _clean(scene.get("summary"))
        purpose = _clean(scene.get("dramatic_purpose"))
        if summary:
            lines.append(f"[[Summary: {summary}]]")
        if purpose:
            lines.append(f"[[Dramatic purpose: {purpose}]]")
        raw_beats = scene.get("beats") or "[]"
        try:
            beats = json.loads(raw_beats) if isinstance(raw_beats, str) else raw_beats
        except (TypeError, ValueError):
            beats = []
        if isinstance(beats, list):
            for beat in beats:
                beat_text = _clean(beat)
                if beat_text:
                    lines.append(f"[[Beat: {beat_text}]]")
        body = _clean(scene.get("body"))
        if body:
            lines.append(body)
        lines.extend(["", ""])
    return "\n".join(lines).rstrip() + "\n"
