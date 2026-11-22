import json
from pathlib import Path

import pytest

from backend.app.storyboard_schemas import StoryboardImageTaskCreate
from backend.app.storyboard_media import (
    WORKFLOW_DIR, build_workflow_graph, load_workflow_pack, _validate_image_locator,
)
from backend.app.storyboard_video import (
    _safe_video_locator, build_video_workflow_graph, load_video_workflow_pack,
)
from backend.app.storyboard_video_schemas import StoryboardVideoTaskCreate
from backend.app.media_workflow_registry import _effective_model_value, _entry
from backend.app.animatic import _filter_graph, _timeline_document



def test_versioned_comfyui_workflow_pack_maps_all_inputs():
    pack = load_workflow_pack("checkpoint-basic-v1")
    graph = build_workflow_graph(
        pack, checkpoint="studio.safetensors", prompt="wide cinematic shot",
        negative_prompt="watermark", width=1280, height=720,
        steps=30, cfg=6.5, seed=1234,
    )
    assert graph["4"]["inputs"]["ckpt_name"] == "studio.safetensors"
    assert graph["6"]["inputs"]["text"] == "wide cinematic shot"
    assert graph["7"]["inputs"]["text"] == "watermark"
    assert graph["5"]["inputs"]["width"] == 1280
    assert graph["5"]["inputs"]["height"] == 720
    assert graph["3"]["inputs"]["seed"] == 1234
    assert graph["3"]["inputs"]["steps"] == 30
    assert graph["3"]["inputs"]["cfg"] == 6.5


@pytest.mark.parametrize("locator", [
    {"filename": "../secret.png", "subfolder": "", "type": "output"},
    {"filename": "ok.png", "subfolder": "../outside", "type": "output"},
    {"filename": "ok.png", "subfolder": "", "type": "input"},
    {"filename": "folder/ok.png", "subfolder": "", "type": "output"},
])
def test_comfyui_output_locator_rejects_unsafe_paths(locator):
    with pytest.raises(ValueError):
        _validate_image_locator(locator)


def test_comfyui_output_locator_accepts_output_file():
    assert _validate_image_locator({
        "filename": "storyforge_00001_.png", "subfolder": "", "type": "output"
    }) == ("storyforge_00001_.png", "", "output")


def test_workflow_pack_is_not_mutated_by_graph_building():
    pack = load_workflow_pack("checkpoint-basic-v1")
    original = json.dumps(pack["workflow"], sort_keys=True)
    build_workflow_graph(
        pack, checkpoint="studio.safetensors", prompt="frame",
        negative_prompt="", width=1024, height=1024, steps=24, cfg=7, seed=9,
    )
    assert json.dumps(pack["workflow"], sort_keys=True) == original


@pytest.mark.parametrize("width,height", [(256, 256), (1280, 720), (2048, 1024)])
def test_storyboard_image_dimensions_accept_multiples_of_eight(width, height):
    task = StoryboardImageTaskCreate(width=width, height=height)
    assert task.width == width
    assert task.height == height


@pytest.mark.parametrize("field,value", [("width", 1025), ("height", 721)])
def test_storyboard_image_dimensions_reject_non_multiples_of_eight(field, value):
    with pytest.raises(ValueError, match="divisible by 8"):
        StoryboardImageTaskCreate(**{field: value})



def test_versioned_wan_video_workflow_maps_prompt_image_and_timing(monkeypatch):
    for key in (
        "MASOUD_STUDIO_COMFYUI_VIDEO_UNET",
        "MASOUD_STUDIO_COMFYUI_VIDEO_CLIP",
        "MASOUD_STUDIO_COMFYUI_VIDEO_VAE",
        "MASOUD_STUDIO_COMFYUI_VIDEO_CLIP_VISION",
    ):
        monkeypatch.delenv(key, raising=False)
    pack = load_video_workflow_pack("wan2.1-i2v-basic-v1")
    original = json.dumps(pack["workflow"], sort_keys=True)
    graph = build_video_workflow_graph(
        pack, prompt="A slow cinematic camera push-in",
        negative_prompt="jitter, watermark", start_image="storyforge-start.png",
        frames=49, fps=24, seed=987,
    )
    assert graph["6"]["inputs"]["text"] == "A slow cinematic camera push-in"
    assert graph["7"]["inputs"]["text"] == "jitter, watermark"
    assert graph["52"]["inputs"]["image"] == "storyforge-start.png"
    assert graph["50"]["inputs"]["length"] == 49
    assert graph["55"]["inputs"]["fps"] == 24
    assert graph["3"]["inputs"]["seed"] == 987
    assert json.dumps(pack["workflow"], sort_keys=True) == original


@pytest.mark.parametrize("frames", [17, 21, 29, 37, 53, 69])
def test_wan_video_schema_rejects_unlisted_frame_counts(frames):
    with pytest.raises(ValueError, match="33, 49 or 73"):
        StoryboardVideoTaskCreate(frames=frames)


@pytest.mark.parametrize("locator", [
    {"filename": "../outside.mp4", "subfolder": "", "type": "output"},
    {"filename": "ok.mp4", "subfolder": "../outside", "type": "output"},
    {"filename": "ok.png", "subfolder": "", "type": "output"},
    {"filename": "ok.mp4", "subfolder": "", "type": "temp"},
])
def test_comfyui_video_locator_rejects_unsafe_outputs(locator):
    with pytest.raises(ValueError):
        _safe_video_locator(locator)


def test_comfyui_video_locator_accepts_mp4_output():
    assert _safe_video_locator({
        "filename": "storyforge_00001_.mp4", "subfolder": "storyforge", "type": "output"
    }) == ("storyforge_00001_.mp4", "storyforge", "output")


def test_animatic_filter_graph_mixes_still_video_and_transition_clips():
    shots = [
        {"asset_mime_type": "image/png", "duration_seconds": 4.0, "transition": "dissolve"},
        {"asset_mime_type": "video/mp4", "duration_seconds": 5.0, "transition": "cut"},
        {"asset_mime_type": "image/webp", "duration_seconds": 2.0, "transition": None},
    ]
    graph, output_label, duration = _filter_graph(shots, 24, 1280, 720)
    assert "trim=duration=4.000" in graph
    assert "trim=duration=5.000" in graph
    assert "xfade=transition=fade" in graph
    assert "concat=n=2:v=1:a=0" in graph
    assert output_label == "mix2"
    assert duration == pytest.approx(10.25)


def test_animatic_timeline_exports_otio_clip_transition_and_provenance():
    snapshot = {
        "project_id": "project-1", "story_id": "story-1", "story_title": "Test story",
        "resolution": "1280x720",
        "shots": [
            {"shot_id": "shot-1", "take_id": "take-1", "asset_id": "asset-1",
             "asset_sha256": "a" * 64, "scene_id": "scene-1", "scene_title": "Scene 1",
             "position": 1, "title": "Opening", "duration_seconds": 4.0,
             "transition": "dissolve", "continuity_notes": ""},
            {"shot_id": "shot-2", "take_id": "take-2", "asset_id": "asset-2",
             "asset_sha256": "b" * 64, "scene_id": "scene-1", "scene_title": "Scene 1",
             "position": 2, "title": "Close-up", "duration_seconds": 3.0,
             "transition": "cut", "continuity_notes": "Keep prop in left hand"},
        ],
    }
    document = json.loads(_timeline_document(snapshot, "video-asset", 24))
    track = document["tracks"]["children"][0]
    assert document["OTIO_SCHEMA"] == "Timeline.1"
    assert [child["OTIO_SCHEMA"] for child in track["children"]] == [
        "Clip.2", "Transition.1", "Clip.2"
    ]
    assert track["children"][0]["metadata"]["storyforge"]["take_id"] == "take-1"
    assert track["children"][0]["media_reference"]["target_url"].startswith("file://")
    assert document["metadata"]["storyforge"]["rendered_video_asset_id"] == "video-asset"



def test_media_workflow_preflight_uses_effective_image_checkpoint(monkeypatch):
    pack = load_workflow_pack("checkpoint-basic-v1")
    monkeypatch.setenv("MASOUD_STUDIO_COMFYUI_CHECKPOINT", "installed-model.safetensors")
    assert _effective_model_value(
        "text_to_image", "CheckpointLoaderSimple", "ckpt_name",
        pack["workflow"]["4"]["inputs"]["ckpt_name"],
    ) == "installed-model.safetensors"


def test_image_preflight_requires_the_checkpoint_used_by_worker(monkeypatch):
    monkeypatch.delenv("MASOUD_STUDIO_COMFYUI_CHECKPOINT", raising=False)
    assert _effective_model_value(
        "text_to_image", "CheckpointLoaderSimple", "ckpt_name", "placeholder.safetensors"
    ) is None


@pytest.mark.parametrize(("class_type", "field", "setting", "default"), [
    ("UNETLoader", "unet_name", "MASOUD_STUDIO_COMFYUI_VIDEO_UNET", "default-unet.safetensors"),
    ("CLIPLoader", "clip_name", "MASOUD_STUDIO_COMFYUI_VIDEO_CLIP", "default-clip.safetensors"),
    ("VAELoader", "vae_name", "MASOUD_STUDIO_COMFYUI_VIDEO_VAE", "default-vae.safetensors"),
    ("CLIPVisionLoader", "clip_name", "MASOUD_STUDIO_COMFYUI_VIDEO_CLIP_VISION", "default-vision.safetensors"),
])
def test_video_preflight_uses_same_model_overrides_as_worker(monkeypatch, class_type, field, setting, default):
    monkeypatch.setenv(setting, "configured-model.safetensors")
    assert _effective_model_value("image_to_video", class_type, field, default) == "configured-model.safetensors"


def test_video_preflight_falls_back_to_versioned_pack_model_defaults(monkeypatch):
    monkeypatch.delenv("MASOUD_STUDIO_COMFYUI_VIDEO_UNET", raising=False)
    assert _effective_model_value(
        "image_to_video", "UNETLoader", "unet_name", "wan-default.safetensors"
    ) == "wan-default.safetensors"


def test_media_workflow_entry_includes_clip_vision_model():
    pack = load_video_workflow_pack("wan2.1-i2v-basic-v1")
    entry = _entry(pack, "wan2.1-i2v-basic-v1", "image_to_video")
    assert "clip_vision_h.safetensors" in entry["required_models"]
