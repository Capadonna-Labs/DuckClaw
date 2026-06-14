from __future__ import annotations

import inspect
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = (
    REPO_ROOT / "packages" / "agents" / "src" / "duckclaw",
    REPO_ROOT / "services",
)
FORGE_CRM_DIR = (
    REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "forge" / "crm"
)


def _python_files_under(path: Path) -> list[Path]:
    return [
        candidate
        for candidate in path.rglob("*.py")
        if ".venv" not in candidate.parts and "__pycache__" not in candidate.parts
    ]


def test_forge_crm_package_is_removed_from_runtime_tree() -> None:
    assert not FORGE_CRM_DIR.exists()

    offenders: list[str] = []
    forbidden_tokens = ("duckclaw.forge.crm", "forge.crm")
    for root in RUNTIME_ROOTS:
        for path in _python_files_under(root):
            text = path.read_text(encoding="utf-8")
            if any(token in text for token in forbidden_tokens):
                offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == []


def test_worker_spec_does_not_expose_crm_config() -> None:
    from duckclaw.workers.manifest import WorkerSpec, build_spec_from_manifest

    assert "crm_config" not in WorkerSpec.__slots__
    assert "crm_config" not in inspect.signature(WorkerSpec).parameters

    spec = build_spec_from_manifest(
        {"name": "CRM-free", "crm": {"enabled": True}},
        "crm_free",
        REPO_ROOT,
    )

    assert not hasattr(spec, "crm_config")
