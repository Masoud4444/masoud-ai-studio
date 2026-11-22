"""Read-only registry for installed, versioned media workflow packs."""
from .storyboard_media import WORKFLOW_DIR, load_workflow_pack
from .storyboard_video import VIDEO_WORKFLOW_DIR, load_video_workflow_pack


def _entry(pack: dict, workflow_id: str, kind: str) -> dict:
    graph = pack.get("workflow") or {}
    model_fields = {"ckpt_name", "unet_name", "clip_name", "vae_name"}
    models, nodes = set(), set()
    for node in graph.values():
        if not isinstance(node, dict):
            continue
        if isinstance(node.get("class_type"), str):
            nodes.add(node["class_type"])
        inputs = node.get("inputs")
        if isinstance(inputs, dict):
            for key, value in inputs.items():
                if key in model_fields and isinstance(value, str) and value:
                    models.add(value)
    return {
        "workflow_id": workflow_id, "version": str(pack.get("version", "1.0.0")),
        "engine": str(pack.get("engine", "comfyui")), "kind": kind,
        "description": str(pack.get("description", ""))[:500],
        "required_nodes": sorted(nodes), "required_models": sorted(models),
    }


def list_media_workflows() -> dict:
    items = []
    for directory, loader, kind in (
        (WORKFLOW_DIR, load_workflow_pack, "text_to_image"),
        (VIDEO_WORKFLOW_DIR, load_video_workflow_pack, "image_to_video"),
    ):
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.json")):
            try:
                items.append(_entry(loader(path.stem), path.stem, kind))
            except (OSError, ValueError, TypeError, KeyError):
                continue
    return {"items": items}
