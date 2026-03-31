"""Ajuste de security_policy.yaml por plantilla (spec §5 Strix)."""

from __future__ import annotations

from pathlib import Path

from duckops.sovereign.atomic import atomic_write

FORGE_REL = Path("packages/agents/src/duckclaw/forge/templates")


def patch_security_policy(repo_root: Path, template_dir: str) -> bool:
    """
    Inserta un mount RO de ``<repo>/db`` en ``filesystem.readonly_mounts`` si falta.
    """
    path = (repo_root / FORGE_REL / template_dir / "security_policy.yaml").resolve()
    if not path.is_file():
        return False
    rr = str(repo_root.resolve()).replace("\\", "/")
    mount_line = f'    - "{rr}/db:/workspace/repo_db:ro"\n'
    text = path.read_text(encoding="utf-8")
    if "repo_db:ro" in text:
        return True
    needle = "readonly_mounts:\n"
    if needle not in text:
        return False
    new_text = text.replace(needle, needle + mount_line, 1)
    atomic_write(path, new_text)
    return True
