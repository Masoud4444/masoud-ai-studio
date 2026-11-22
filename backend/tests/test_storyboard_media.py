import json
from pathlib import Path

import pytest

from backend.app.storyboard_media import (
    WORKFLOW_DIR, build_workflow_graph, load_workflow_pack, _validate_image_locator,
)


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
