"""Guardrails for removed domain-specific state-delta handlers."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]

_FORBIDDEN_DOMAIN_TOKENS = (
    "capadonna",
    "quant_state_delta",
    "quant-trader",
    "quant_trader",
)


def test_domain_state_delta_handler_is_not_core_db_writer() -> None:
    writer = _REPO / "services" / "db-writer"

    assert not (writer / "quant_state_delta_handler.py").exists()
    assert not (writer / "models" / "quant_state_delta.py").exists()
    assert not (writer / "domain_extension_loader.py").exists()


def test_db_writer_main_does_not_import_domain_state_delta_handler() -> None:
    main_source = (_REPO / "services" / "db-writer" / "main.py").read_text(encoding="utf-8")

    assert "quant_state_delta_handler" not in main_source
    assert "load_capadonna" not in main_source.lower()


def test_db_writer_py_files_avoid_hardcoded_product_domains() -> None:
    writer = _REPO / "services" / "db-writer"
    offenders: list[str] = []
    for path in writer.rglob("*.py"):
        if path.name == "__init__.py":
            continue
        text = path.read_text(encoding="utf-8").lower()
        for token in _FORBIDDEN_DOMAIN_TOKENS:
            if token in text:
                offenders.append(f"{path.relative_to(_REPO)} contains {token!r}")
    assert not offenders, "\n".join(offenders)
