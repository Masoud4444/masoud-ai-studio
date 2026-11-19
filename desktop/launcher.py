from __future__ import annotations

import base64
import ctypes
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import socket
import sys
import threading
import time
import urllib.request
import webbrowser
from ctypes import wintypes

from PIL import Image, ImageDraw
import pystray


class DATA_BLOB(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _blob(data: bytes):
    buffer = ctypes.create_string_buffer(data)
    return DATA_BLOB(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_byte))), buffer


def _dpapi(data: bytes, protect: bool) -> bytes:
    source, keepalive = _blob(data)
    output = DATA_BLOB()
    crypt = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt.CryptProtectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), wintypes.LPCWSTR, ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
    ]
    crypt.CryptProtectData.restype = wintypes.BOOL
    crypt.CryptUnprotectData.argtypes = [
        ctypes.POINTER(DATA_BLOB), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(DATA_BLOB),
        ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(DATA_BLOB),
    ]
    crypt.CryptUnprotectData.restype = wintypes.BOOL
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    kernel.LocalFree.restype = ctypes.c_void_p
    if protect:
        ok = crypt.CryptProtectData(ctypes.byref(source), "Masoud AI Studio credential key", None, None, None, 0, ctypes.byref(output))
    else:
        ok = crypt.CryptUnprotectData(ctypes.byref(source), None, None, None, None, 0, ctypes.byref(output))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output.pbData, output.cbData)
    finally:
        kernel.LocalFree(ctypes.cast(output.pbData, ctypes.c_void_p))


def _load_master_key(data_dir: Path) -> bytes:
    key_file = data_dir / "credential-key.dpapi"
    if key_file.exists():
        key = _dpapi(key_file.read_bytes(), protect=False)
        if len(key) != 32:
            raise RuntimeError("The protected credential key has an invalid length.")
        return key
    key = secrets.token_bytes(32)
    protected = _dpapi(key, protect=True)
    temp = key_file.with_suffix(".tmp")
    temp.write_bytes(protected)
    os.replace(temp, key_file)
    return key


def _configure_environment() -> Path:
    root = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "Masoud AI Studio"
    data_dir = root / "data"
    logs_dir = root / "logs"
    data_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(parents=True, exist_ok=True)
    key = _load_master_key(root)
    from sqlalchemy.engine import URL
    os.environ["MASOUD_STUDIO_DATABASE_URL"] = URL.create("sqlite", database=str(data_dir / "masoud_studio.db")).render_as_string(hide_password=False)
    os.environ["MASOUD_STUDIO_STORAGE_ROOT"] = str(data_dir / "storage")
    os.environ["MASOUD_STUDIO_CREDENTIAL_KEY"] = base64.urlsafe_b64encode(key).decode("ascii")
    os.environ["MASOUD_STUDIO_CREDENTIAL_KEY_VERSION"] = "1"
    os.environ["MASOUD_STUDIO_WORKER_ENABLED"] = "false"
    os.environ["MASOUD_STUDIO_DESKTOP_MODE"] = "true"
    os.environ["MASOUD_STUDIO_PORT"] = "8000"
    os.environ["MASOUD_STUDIO_SCHEMA_MODE"] = "migrate"
    return root


def _resource_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def _migrate(root: Path) -> None:
    from alembic import command
    from alembic.config import Config
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "backend" / "migrations").replace("%", "%%"))
    command.upgrade(config, "head")


def _tray_image():
    image = Image.new("RGBA", (64, 64), (24, 32, 48, 255))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((4, 4, 60, 60), radius=14, fill=(52, 94, 145, 255))
    draw.text((20, 15), "M", fill=(255, 255, 255, 255), stroke_width=1)
    return image


def main() -> int:
    if os.name != "nt":
        raise RuntimeError("The packaged desktop launcher currently supports Windows only.")
    app_data = _configure_environment()
    log_file = app_data / "logs" / "studio.log"
    logging.basicConfig(
        handlers=[RotatingFileHandler(log_file, maxBytes=2_000_000, backupCount=3, encoding="utf-8")],
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    root = _resource_root()
    os.chdir(root)
    try:
        _migrate(root)
    except Exception:
        logging.exception("Database migration failed; application startup aborted.")
        return 2

    with socket.socket() as probe:
        probe.settimeout(0.5)
        if probe.connect_ex(("127.0.0.1", 8000)) == 0:
            logging.error("Port 8000 is already in use; refusing to attach to an unknown service.")
            return 3

    from backend.app.main import app
    import uvicorn

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8000, log_config=None, access_log=False))
    thread = threading.Thread(target=server.run, name="masoud-studio-server", daemon=True)
    thread.start()
    health_url = "http://127.0.0.1:8000/health"
    healthy = False
    for _ in range(45):
        if not thread.is_alive():
            logging.error("Local server stopped before becoming healthy.")
            return 4
        try:
            with urllib.request.urlopen(health_url, timeout=1) as response:
                if response.status == 200:
                    healthy = True
                    break
        except Exception:
            time.sleep(1)
    if not healthy:
        logging.error("Local server did not become healthy within 45 seconds.")
        server.should_exit = True
        thread.join(timeout=10)
        return 5

    if "--smoke-test" in sys.argv:
        server.should_exit = True
        thread.join(timeout=20)
        return 0 if not thread.is_alive() else 6

    def open_studio(_icon=None, _item=None):
        webbrowser.open("http://127.0.0.1:8000", new=2)

    def exit_studio(icon, _item):
        server.should_exit = True
        icon.stop()

    icon = pystray.Icon(
        "MasoudAIStudio",
        _tray_image(),
        "Masoud AI Studio",
        menu=pystray.Menu(
            pystray.MenuItem("Open Masoud AI Studio", open_studio, default=True),
            pystray.MenuItem("Exit", exit_studio),
        ),
    )
    open_studio()
    try:
        icon.run()
    finally:
        server.should_exit = True
        thread.join(timeout=20)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
