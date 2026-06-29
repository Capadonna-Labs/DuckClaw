"""
Resolve Sensory voice_id from env map + session worker — config-driven, no hardcoded voice IDs.

Voice identity comes from manifest + environment variables, not constants in the pipeline.
"""

from __future__ import annotations

import json
import logging
from typing import Any

_log = logging.getLogger(__name__)


def resolve_voice_id_for_worker(
    worker_id: str,
    *,
    default_voice_id: str = "default",
    voice_map_json: str = "",
) -> str:
    """Map worker_id → voice_id via DUCKCLAW_TTS_VOICE_MAP JSON (same contract as gateway)."""
    default = (default_voice_id or "default").strip() or "default"
    wid = (worker_id or "").strip()
    mapping: dict[str, Any] = {}
    raw = (voice_map_json or "").strip()
    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                mapping = parsed
        except json.JSONDecodeError:
            _log.warning("invalid DUCKCLAW_TTS_VOICE_MAP JSON")
    if wid and wid in mapping:
        return str(mapping[wid]).strip()
    if "default" in mapping:
        return str(mapping["default"]).strip()
    return default


def resolve_sensory_voice_id(
    *,
    worker_id: str,
    app_state: dict[str, Any] | None,
    default_voice_id: str,
    voice_map_json: str = "",
) -> str:
    """Resolve voice for TTS: client app_state override → worker map → default env."""
    app = app_state or {}
    explicit = str(app.get("voice_id") or "").strip()
    if explicit:
        return explicit
    effective_worker = str(app.get("worker_id") or worker_id or "").strip()
    return resolve_voice_id_for_worker(
        effective_worker,
        default_voice_id=default_voice_id,
        voice_map_json=voice_map_json,
    )
