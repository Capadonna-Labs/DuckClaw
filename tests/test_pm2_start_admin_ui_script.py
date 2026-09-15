"""Guardrails for duckclaw-admin-ui PM2 entrypoint (artifact vault root)."""

from __future__ import annotations

from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
_SCRIPT = _REPO / "scripts" / "pm2-start-admin-ui.sh"


def test_pm2_start_admin_ui_lifts_vault_roots_from_monorepo_env() -> None:
    text = _SCRIPT.read_text(encoding="utf-8")
    assert "DUCKCLAW_EXTENSION_ROOT" in text
    assert "DUCKCLAW_REPO_ROOT" in text
    # Prefer admin/.env.local; never wholesale-source monorepo .env (HOSTNAME bind).
    assert 'ADMIN}/.env.local"' in text or "${ADMIN}/.env.local" in text
    assert 'source "${ROOT}/.env"' not in text
    assert ". \"${ROOT}/.env\"" not in text
    # Selective lift when admin env omitted vault roots (VPS Capadonna layout).
    assert "grep -E '^(DUCKCLAW_EXTENSION_ROOT|DUCKCLAW_REPO_ROOT)=" in text
    assert "HOSTNAME=\"${DUCKCLAW_ADMIN_BIND_HOST:-0.0.0.0}\"" in text
