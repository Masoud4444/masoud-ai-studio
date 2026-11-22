"""Registry and live compatibility checks for installed ComfyUI workflow packs."""
import aiohttp
import asyncio

from .storyboard_media import WORKFLOW_DIR, ComfyUIClient, load_workflow_pack
from .storyboard_video import VIDEO_WORKFLOW_DIR, load_video_workflow_pack
from .ai_gateway import _PinnedResolver, _resolve_provider_addresses


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

    client = ComfyUIClient()
    pinned = await _resolve_provider_addresses(client.host, client.port, allow_local=True)
    connector = aiohttp.TCPConnector(resolver=_PinnedResolver(pinned), use_dns_cache=False)
    timeout = aiohttp.ClientTimeout(total=20, connect=5, sock_read=12)
    try:
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
                object_info = await response.json(content_type=None)
    except (aiohttp.ClientError, asyncio.TimeoutError, ValueError):
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
        for field, value in node_inputs.items():
            if isinstance(value, list) and len(value) == 2 and isinstance(value[0], str):
                continue
            field_schema = choices_by_field.get(field)
            if not isinstance(field_schema, list) or not field_schema:
                if field in model_fields:
                    missing_models.add(str(value))
                else:
                    unsupported_inputs.add(f"{class_type}.{field}")
                continue
            choices = field_schema[0]
            if isinstance(choices, list) and value not in choices:
                if field in model_fields:
                    missing_models.add(str(value))
                else:
                    unsupported_inputs.add(f"{class_type}.{field}={value}")

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
