"""Registry and live compatibility checks for installed ComfyUI workflow packs."""
import aiohttp
import asyncio
import json

from .storyboard_media import WORKFLOW_DIR, ComfyUIClient, load_workflow_pack
from .storyboard_video import VIDEO_WORKFLOW_DIR, load_video_workflow_pack
from .ai_gateway import _PinnedResolver, _resolve_provider_addresses
from fastapi import HTTPException


def _effective_model_value(kind: str, class_type: str, field: str, default: object) -> object:
    """Return the model filename the worker will actually pass to ComfyUI."""
    setting = None
    if kind == "text_to_image" and class_type == "CheckpointLoaderSimple" and field == "ckpt_name":
        setting = "MASOUD_STUDIO_COMFYUI_CHECKPOINT"
    elif kind == "image_to_video":
        setting = {
            ("UNETLoader", "unet_name"): "MASOUD_STUDIO_COMFYUI_VIDEO_UNET",
            ("CLIPLoader", "clip_name"): "MASOUD_STUDIO_COMFYUI_VIDEO_CLIP",
            ("VAELoader", "vae_name"): "MASOUD_STUDIO_COMFYUI_VIDEO_VAE",
            ("CLIPVisionLoader", "clip_name"): "MASOUD_STUDIO_COMFYUI_VIDEO_CLIP_VISION",
        }.get((class_type, field))
    if setting is None:
        return default
    configured = __import__("os").getenv(setting, "").strip()
    # Image generation requires an explicit checkpoint; video settings may
    # safely fall back to the versioned workflow pack defaults.
    if kind == "text_to_image":
        return configured or None
    return configured or default


def _entry(pack: dict, workflow_id: str, kind: str) -> dict:
    graph = pack.get("workflow") or {}
    models, nodes = set(), set()
    for node in graph.values():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        if isinstance(class_type, str):
            nodes.add(class_type)
        inputs = node.get("inputs")
        if isinstance(inputs, dict):
            for key, value in inputs.items():
                effective = _effective_model_value(kind, str(class_type or ""), key, value)
                if key in {"ckpt_name", "unet_name", "clip_name", "vae_name"} and isinstance(effective, str) and effective:
                    models.add(effective)
    return {
        "workflow_id": workflow_id, "version": str(pack.get("version", "1.0.0")),
        "engine": str(pack.get("engine", "comfyui")), "kind": kind,
        "description": str(pack.get("description", ""))[:500],
        "required_nodes": sorted(nodes), "required_models": sorted(models),
    }


def _load_pack(workflow_id: str, kind: str) -> dict:
    if kind == "text_to_image":
        return load_workflow_pack(workflow_id)
    if kind == "image_to_video":
        return load_video_workflow_pack(workflow_id)
    raise ValueError("Unsupported media workflow kind")


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


async def check_workflow_compatibility(workflow_id: str, kind: str) -> dict:
    """Compare a trusted local pack with the configured ComfyUI installation."""
    try:
        pack = _load_pack(workflow_id, kind)
    except (OSError, ValueError, TypeError, KeyError):
        return {"workflow_id": workflow_id, "kind": kind, "compatible": False,
                "engine_available": False, "error": "workflow_pack_invalid",
                "missing_nodes": [], "missing_models": [], "unsupported_inputs": []}

    try:
        client = ComfyUIClient()
        pinned = await _resolve_provider_addresses(client.host, client.port, allow_local=True)
        connector = aiohttp.TCPConnector(resolver=_PinnedResolver(pinned), use_dns_cache=False)
        timeout = aiohttp.ClientTimeout(total=20, connect=5, sock_read=12)
        async with aiohttp.ClientSession(connector=connector, timeout=timeout, trust_env=False) as session:
            async with session.get(client.base_url + "/system_stats", allow_redirects=False) as response:
                if response.status != 200:
                    return {"workflow_id": workflow_id, "kind": kind, "compatible": False,
                            "engine_available": False, "error": "comfyui_unavailable",
                            "missing_nodes": [], "missing_models": [], "unsupported_inputs": []}
                stats = await response.json(content_type=None)
            async with session.get(client.base_url + "/object_info", allow_redirects=False) as response:
                if response.status != 200:
                    return {"workflow_id": workflow_id, "kind": kind, "compatible": False,
                            "engine_available": True, "error": "comfyui_object_info_unavailable",
                            "missing_nodes": [], "missing_models": [], "unsupported_inputs": []}
                raw_info = await response.content.read(32 * 1024 * 1024 + 1)
                if len(raw_info) > 32 * 1024 * 1024:
                    return {"workflow_id": workflow_id, "kind": kind, "compatible": False,
                            "engine_available": True, "error": "comfyui_object_info_too_large",
                            "missing_nodes": [], "missing_models": [], "unsupported_inputs": []}
                object_info = json.loads(raw_info)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError, OSError, HTTPException):
        return {"workflow_id": workflow_id, "kind": kind, "compatible": False,
                "engine_available": False, "error": "comfyui_connection_failed",
                "missing_nodes": [], "missing_models": [], "unsupported_inputs": []}

    if not isinstance(object_info, dict):
        return {"workflow_id": workflow_id, "kind": kind, "compatible": False,
                "engine_available": True, "error": "comfyui_object_info_invalid",
                "missing_nodes": [], "missing_models": [], "unsupported_inputs": []}

    missing_nodes, missing_models, unsupported_inputs = set(), set(), set()
    graph = pack.get("workflow") or {}
    model_fields = {"ckpt_name", "unet_name", "clip_name", "vae_name"}
    for node_id, node in graph.items():
        if not isinstance(node, dict):
            continue
        class_type = node.get("class_type")
        definition = object_info.get(class_type) if isinstance(class_type, str) else None
        if not isinstance(definition, dict):
            missing_nodes.add(str(class_type or node_id))
            continue
        schema_inputs = definition.get("input") or {}
        choices_by_field = {}
        for section in ("required", "optional"):
            fields = schema_inputs.get(section) or {}
            if isinstance(fields, dict):
                choices_by_field.update(fields)
        node_inputs = node.get("inputs") or {}
        for field, default_value in node_inputs.items():
            if isinstance(default_value, list) and len(default_value) == 2 and isinstance(default_value[0], str):
                continue
            value = _effective_model_value(kind, str(class_type or ""), field, default_value)
            if field in model_fields and value is None:
                missing_models.add("MASOUD_STUDIO_COMFYUI_CHECKPOINT (not configured)")
                continue
            field_schema = choices_by_field.get(field)
            if not isinstance(field_schema, list) or not field_schema:
                unsupported_inputs.add(f"{class_type}.{field}")
                continue
            choices = field_schema[0]
            if isinstance(choices, list) and value not in choices:
                if field in model_fields:
                    missing_models.add(str(value))
                else:
                    unsupported_inputs.add(f"{class_type}.{field}={value}")
            elif field in model_fields and not isinstance(choices, list):
                unsupported_inputs.add(f"{class_type}.{field} (model inventory unavailable)")

    system = stats.get("system") if isinstance(stats, dict) else {}
    devices = []
    if isinstance(system, dict) and isinstance(system.get("devices"), list):
        for device in system["devices"][:8]:
            if isinstance(device, dict):
                devices.append({"name": str(device.get("name", "GPU"))[:120],
                                "type": str(device.get("type", ""))[:40]})
    missing_nodes, missing_models, unsupported_inputs = (
        sorted(missing_nodes), sorted(missing_models), sorted(unsupported_inputs)
    )
    return {
        "workflow_id": workflow_id, "kind": kind, "compatible": not (missing_nodes or missing_models or unsupported_inputs),
        "engine_available": True, "error": None, "missing_nodes": missing_nodes,
        "missing_models": missing_models, "unsupported_inputs": unsupported_inputs,
        "devices": devices,
    }
