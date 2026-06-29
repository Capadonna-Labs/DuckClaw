"""Packaged MCP connector presets (T1 profiles)."""

from __future__ import annotations

import logging
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

_SEED_FILENAME = "mcp_connector_presets.yaml"

_PRESET_DEFAULTS: dict[str, Any] = {
    "tool_allowlist": ["*"],
    "tool_denylist": [],
    "egress_hosts": [],
    "launch_args": [],
    "launch_env": {},
    "metadata": {},
    "read_only": True,
    "auth_kind": "none",
}


def bundled_mcp_connector_presets_path() -> Path:
    return Path(__file__).resolve().parent / "seeds" / _SEED_FILENAME


def resolve_mcp_connector_presets_path() -> Path:
    override = (os.environ.get("DUCKCLAW_MCP_PRESETS_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    repo_root = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    if repo_root:
        candidate = Path(repo_root).expanduser().resolve() / "config" / _SEED_FILENAME
        if candidate.is_file():
            return candidate
    return bundled_mcp_connector_presets_path()


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if key == "profile":
            continue
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(dict(out[key]), value)
        else:
            out[key] = value
    return out


def _resolve_preset_body(
    preset_id: str,
    raw: dict[str, Any],
    *,
    profiles: dict[str, dict[str, Any]],
    defaults: dict[str, Any],
) -> dict[str, Any]:
    profile_name = str(raw.get("profile") or "").strip()
    profile_body = dict(profiles.get(profile_name) or {}) if profile_name else {}
    merged = _deep_merge(_PRESET_DEFAULTS, defaults)
    merged = _deep_merge(merged, profile_body)
    merged = _deep_merge(merged, raw)
    merged.pop("profile", None)
    if not str(merged.get("display_name") or "").strip():
        merged["display_name"] = preset_id
    return merged


def _parse_presets_yaml(raw: dict[str, Any]) -> dict[str, dict[str, Any]]:
    defaults = raw.get("defaults") if isinstance(raw.get("defaults"), dict) else {}
    profiles_raw = raw.get("profiles") if isinstance(raw.get("profiles"), dict) else {}
    presets_raw = raw.get("presets") if isinstance(raw.get("presets"), dict) else {}
    profiles = {
        str(name).strip(): dict(body)
        for name, body in profiles_raw.items()
        if str(name).strip() and isinstance(body, dict)
    }
    out: dict[str, dict[str, Any]] = {}
    for preset_id, body in presets_raw.items():
        key = str(preset_id or "").strip().lower()
        if not key or not isinstance(body, dict):
            continue
        out[key] = _resolve_preset_body(key, body, profiles=profiles, defaults=defaults)
    return out


@lru_cache(maxsize=1)
def load_mcp_connector_presets() -> dict[str, dict[str, Any]]:
    path = resolve_mcp_connector_presets_path()
    if not path.is_file():
        raise FileNotFoundError(f"MCP connector presets not found: {path}")
    try:
        import yaml

        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            raise ValueError("mcp_connector_presets.yaml must be a mapping")
        presets = _parse_presets_yaml(raw)
        if not presets:
            raise ValueError("mcp_connector_presets.yaml requires at least one preset")
        return presets
    except Exception as exc:
        _log.warning("mcp_connector_presets: load %s: %s", path, exc)
        raise


def clear_mcp_connector_presets_cache() -> None:
    load_mcp_connector_presets.cache_clear()


def list_mcp_connector_presets() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for preset_id, body in load_mcp_connector_presets().items():
        out.append({"preset_id": preset_id, **body})
    return out


def preset_payload(preset_id: str) -> dict[str, Any] | None:
    key = (preset_id or "").strip().lower()
    raw = load_mcp_connector_presets().get(key)
    if not raw:
        return None
    return {"preset_id": key, **dict(raw)}
