from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FORGE_ROOT = REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "forge"

REMOVED_LEGACY_PACKAGES = (
    FORGE_ROOT / "industries",
)

BACKEND_SCAN_ROOTS = (
    REPO_ROOT / "packages" / "agents",
    REPO_ROOT / "services",
    REPO_ROOT / "scripts",
    REPO_ROOT / "tests",
    REPO_ROOT / "config",
)

BANNED_BACKEND_REFERENCES = (
    "duckclaw.forge.industries",
    "duckclaw/forge/industries",
    "forge/industries",
    "INDUSTRIES_TEMPLATES_DIR",
    "industries_data",
)

SCAN_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".toml"}
IGNORED_DIRS = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__", "node_modules"}


def _backend_files() -> list[Path]:
    files: list[Path] = []
    for root in BACKEND_SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            if path.is_file() and path.suffix in SCAN_SUFFIXES:
                files.append(path)
    return files


def test_removed_legacy_forge_packages_stay_removed() -> None:
    existing = [str(path.relative_to(REPO_ROOT)) for path in REMOVED_LEGACY_PACKAGES if path.exists()]
    assert existing == []


def test_backend_does_not_reference_removed_legacy_forge_packages() -> None:
    offenders: list[str] = []
    current_test = Path(__file__).resolve()
    for path in _backend_files():
        if path.resolve() == current_test:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in BANNED_BACKEND_REFERENCES:
            if pattern in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {pattern}")

    assert offenders == []
