"""Install an extension's own Python dependencies into the DuckClaw venv.

Core ``pyproject.toml`` carries no vertical extras. An extension lists its
requirements files under ``python_requirements`` in its fly manifest; deploys call
this right after ``uv sync`` (an exact sync removes anything not in the lockfile).
"""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

from duckclaw.extensions.manifest import load_fly_extension_manifest


def extension_requirement_files() -> list[Path]:
    manifest = load_fly_extension_manifest()
    if manifest is None or manifest.source_path is None:
        return []
    base = manifest.source_path.parent
    files = [(base / rel).resolve() for rel in manifest.python_requirements]
    return [f for f in files if f.is_file()]


def install_extension_python_requirements(*, repo_root: Path, print_fn: Callable[[str], None] = print) -> bool:
    """``uv pip install -r`` each extension requirements file into ``repo_root``'s venv."""
    ok = True
    for req in extension_requirement_files():
        print_fn(f"==> uv pip install -r {req} (extension)")
        proc = subprocess.run(["uv", "pip", "install", "--quiet", "-r", str(req)], cwd=str(repo_root), check=False)
        if proc.returncode != 0:
            print_fn(f"ERROR: no se instalaron las dependencias de la extensión ({req})")
            ok = False
    return ok
