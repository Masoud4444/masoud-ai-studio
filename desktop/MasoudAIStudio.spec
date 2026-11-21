# -*- mode: python ; coding: utf-8 -*-
import os
from PyInstaller.utils.hooks import collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
hidden = (
    collect_submodules("backend.app")
    + collect_submodules("backend.migrations.versions")
    + collect_submodules("alembic", filter=lambda name: not name.startswith("alembic.testing"))
    + collect_submodules("sqlalchemy.dialects.sqlite")
    + collect_submodules("uvicorn")
    + collect_submodules("cryptography")
    + collect_submodules("pypdf")
    + collect_submodules("docx")
    + collect_submodules("pystray")
    + collect_submodules("PIL")
)

a = Analysis(
    [os.path.join(ROOT, "desktop", "launcher.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[
        (os.path.join(ROOT, "alembic.ini"), "."),
        (os.path.join(ROOT, "backend", "migrations"), "backend/migrations"),
        (os.path.join(ROOT, "frontend", "dist"), "frontend/dist"),
    ],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "httpx", "IPython", "notebook", "alembic.testing"],
    noarchive=False,
    optimize=1,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MasoudAIStudio",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="MasoudAIStudio",
)
