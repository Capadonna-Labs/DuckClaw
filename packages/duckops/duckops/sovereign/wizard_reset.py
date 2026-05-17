"""Reinicio del estado del wizard (borrador y preferencias locales)."""

from __future__ import annotations

import json
from pathlib import Path

from duckops.sovereign.draft import SovereignDraft

_WIZARD_DIR = Path.home() / ".config" / "duckclaw"
_DRAFT_PATH = _WIZARD_DIR / "wizard_draft.json"
_CONFIG_PATH = _WIZARD_DIR / "wizard_config.json"

NEUTRAL_DUCKDB_VAULT = "db/sovereign_memory.duckdb"
NEUTRAL_GATEWAY_PM2 = "DuckClaw-Gateway"
NEUTRAL_WORKER_CANDIDATES = ("AXIS-Maestro", "default")


def wizard_state_paths() -> tuple[Path, Path]:
    return _DRAFT_PATH, _CONFIG_PATH


def has_saved_wizard_state() -> bool:
    return _DRAFT_PATH.is_file() or _CONFIG_PATH.is_file()


def clear_wizard_state(*, draft: bool = True, config: bool = True) -> list[Path]:
    """Elimina borrador y/o wizard_config local. No toca ``.env`` del repo."""
    removed: list[Path] = []
    if draft and _DRAFT_PATH.is_file():
        _DRAFT_PATH.unlink()
        removed.append(_DRAFT_PATH)
    if config and _CONFIG_PATH.is_file():
        _CONFIG_PATH.unlink()
        removed.append(_CONFIG_PATH)
    return removed


def fresh_sovereign_draft(*, worker_id: str | None = None) -> SovereignDraft:
    """Borrador neutro sin leer .env ni sesiones previas."""
    wid = (worker_id or "AXIS-Maestro").strip() or "AXIS-Maestro"
    return SovereignDraft(
        wizard_profile="express",
        duckdb_vault_path=NEUTRAL_DUCKDB_VAULT,
        gateway_pm2_name=NEUTRAL_GATEWAY_PM2,
        default_worker_id=wid,
        tenant_id="default",
        wizard_creator_telegram_user_id="",
        wizard_creator_admin_display_name="",
        wizard_extra_admin_telegram_ids="",
        gateway_team_templates="",
        telegram_bot_token="",
        telegram_webhook_public_base_url="",
    )


def default_worker_for_fresh(pick_ids: list[str]) -> str:
    ids = set(pick_ids)
    for cand in NEUTRAL_WORKER_CANDIDATES:
        if cand in ids:
            return cand
    return pick_ids[0] if pick_ids else "AXIS-Maestro"


def load_saved_draft_or_none() -> SovereignDraft | None:
    if not _DRAFT_PATH.is_file():
        return None
    try:
        return SovereignDraft.model_validate_json(_DRAFT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return None


def describe_saved_state() -> str:
    parts: list[str] = []
    if _DRAFT_PATH.is_file():
        parts.append("borrador")
    if _CONFIG_PATH.is_file():
        try:
            data = json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                db = (data.get("db_path") or data.get("duckdb_vault_path") or "").strip()
                w = (data.get("default_worker_id") or "").strip()
                if db or w:
                    parts.append(f"última sesión ({w or '—'} · {db or '—'})")
                else:
                    parts.append("wizard_config.json")
        except Exception:
            parts.append("wizard_config.json")
    return ", ".join(parts) if parts else ""
