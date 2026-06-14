from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_BACKEND_ROOTS = (
    REPO_ROOT / "packages" / "agents" / "src" / "duckclaw",
    REPO_ROOT / "packages" / "shared" / "src" / "duckclaw",
    REPO_ROOT / "packages" / "duckops" / "duckops",
    REPO_ROOT / "services",
    REPO_ROOT / "scripts",
)
IGNORED_DIRS = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__"}
SCAN_SUFFIXES = {".py", ".md", ".yaml", ".yml", ".json", ".toml"}
ALLOWLIST = {
    # Historical migrations are persisted schema history; deleting or editing them
    # requires a separate migration review.
    "packages/shared/src/duckclaw/schema_migrations.py",
}
BANNED_RUNTIME_MARKERS = ("pqrsd", "pqr", "radicacion")


def _runtime_backend_files() -> list[Path]:
    files: list[Path] = []
    for root in RUNTIME_BACKEND_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in ALLOWLIST:
                continue
            files.append(path)
    return files


def test_pqrsd_runtime_backend_tokens_stay_removed() -> None:
    offenders: list[str] = []
    for path in _runtime_backend_files():
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for marker in BANNED_RUNTIME_MARKERS:
            if marker in text:
                offenders.append(f"{path.relative_to(REPO_ROOT).as_posix()}: {marker}")

    assert offenders == []
