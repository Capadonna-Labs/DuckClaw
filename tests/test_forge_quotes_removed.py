from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_ROOTS = (
    REPO_ROOT / "packages" / "agents" / "src" / "duckclaw",
    REPO_ROOT / "services" / "api-gateway",
)
FORGE_QUOTES_DIR = (
    REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "forge" / "quotes"
)
QUOTES_ROUTER = REPO_ROOT / "services" / "api-gateway" / "routers" / "quotes.py"


def _python_files_under(path: Path) -> list[Path]:
    return [
        candidate
        for candidate in path.rglob("*.py")
        if ".venv" not in candidate.parts and "__pycache__" not in candidate.parts
    ]


def test_forge_quotes_package_and_gateway_router_are_removed() -> None:
    assert not FORGE_QUOTES_DIR.exists()
    assert not QUOTES_ROUTER.exists()

    offenders: list[str] = []
    forbidden_tokens = (
        "duckclaw.forge.quotes",
        "forge.quotes",
        "routers.quotes",
        "/api/v1/quotes",
    )
    for root in RUNTIME_ROOTS:
        for path in _python_files_under(root):
            text = path.read_text(encoding="utf-8")
            if any(token in text for token in forbidden_tokens):
                offenders.append(str(path.relative_to(REPO_ROOT)))

    assert offenders == []
