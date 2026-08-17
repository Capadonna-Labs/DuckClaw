# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for DuckClaw desktop sidecar (console build)."""

import os
import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

block_cipher = None
repo = Path(SPECPATH).resolve().parent.parent
hooks_dir = Path(SPECPATH).resolve() / "pyinstaller_hooks"
entry = repo / "services" / "desktop-sidecar" / "run.py"
gateway = repo / "services" / "api-gateway"
agents_src = repo / "packages" / "agents" / "src"
shared_src = repo / "packages" / "shared" / "src"
core_src = repo / "packages" / "core" / "src"
for _p in (agents_src, shared_src, core_src):
    _ps = str(_p)
    if _ps not in sys.path:
        sys.path.insert(0, _ps)


def _python_modules_under(agents_src: Path) -> list[str]:
    root = agents_src / "duckclaw"
    if not root.is_dir():
        return []
    mods: list[str] = []
    for py in root.rglob("*.py"):
        rel = py.relative_to(agents_src).with_suffix("")
        parts = list(rel.parts)
        if parts and parts[-1] == "__init__":
            parts = parts[:-1]
        if parts:
            mods.append(".".join(parts))
    return sorted(set(mods))


_agents_duckclaw = _python_modules_under(agents_src)

datas = []
seeds_src = repo / "packages" / "shared" / "src" / "duckclaw" / "seeds"
if seeds_src.is_dir():
    datas.append((str(seeds_src), "duckclaw" + os.sep + "seeds"))

# Magika (MarkItDown file-type detection) — models not picked up without explicit datas.
try:
    from PyInstaller.utils.hooks import collect_data_files as _collect_data_files

    datas.extend(_collect_data_files("magika"))
except Exception:
    pass

# ponytail: namespace duckclaw — PyInstaller misses agents portion; ship src + rth path hook
for _site, _src in (
    ("agents_site", agents_src),
    ("shared_site", shared_src),
    ("core_site", core_src),
):
    if _src.is_dir():
        datas.append((str(_src), _site))

hiddenimports = [
    "gateway_app",
    "asgi_app",
    "gateway_app_factory",
    *_agents_duckclaw,
    *collect_submodules("duckclaw"),
    *collect_submodules("core"),
    *collect_submodules("routers"),
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
]

a = Analysis(
    [str(entry)],
    pathex=[
        str(repo),
        str(gateway),
        str(repo / "services" / "db-writer"),
        str(agents_src),
        str(shared_src),
        str(core_src),
    ],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[str(hooks_dir)],
    hooksconfig={},
    runtime_hooks=[str(hooks_dir / "pyi_rth_duckclaw_namespace.py")],
    excludes=[
        "mlx",
        "mlx_vlm",
        "comfyui",
        "torch",
        "tensorflow",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="duckclaw_backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
