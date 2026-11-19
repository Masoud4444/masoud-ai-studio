# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_submodules

hidden = (
    collect_submodules("backend.app")
    + collect_submodules("backend.migrations.versions")
    + collect_submodules("alembic")
    + collect_submodules("sqlalchemy")
    + collect_submodules("uvicorn")
    + collect_submodules("cryptography")
    + collect_submodules("pypdf")
    + collect_submodules("docx")
    + collect_submodules("pystray")
    + collect_submodules("PIL")
)

a = Analysis(
    ["desktop/launcher.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("alembic.ini", "."),
        ("backend/migrations", "backend/migrations"),
        ("frontend/dist", "frontend/dist"),
    ],
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "httpx", "IPython", "notebook"],
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
