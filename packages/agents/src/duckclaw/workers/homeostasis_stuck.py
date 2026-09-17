"""Detect identical evaluate_homeostasis results across /loop ticks and escalate.

When the platform forces evaluate_homeostasis every tick and the sensor returns
metrics_aligned=false + hitl_required=false forever, prompt-only instructions
do not stop the burn. This module fingerprints the sensor payload, tracks a
streak on chat state, and returns a corrective nudge or escalate action.
"""

from __future__ import annotations

import hashlib
import json
import os
from typing import Any, Optional

from duckclaw.commands.loop_state_keys import (
    LOOP_HOMEOSTASIS_FP_KEY,
    LOOP_HOMEOSTASIS_STREAK_KEY,
    get_loop_chat_state,
    persist_loop_chat_state,
)

# After this many identical misaligned results, stop re-evaluating and escalate.
_DEFAULT_STREAK_LIMIT = 3


def homeostasis_stuck_streak_limit() -> int:
    try:
        return max(2, int(os.environ.get("DUCKCLAW_HOMEOSTASIS_STUCK_STREAK", str(_DEFAULT_STREAK_LIMIT))))
    except ValueError:
        return _DEFAULT_STREAK_LIMIT


def parse_homeostasis_tool_payload(content: str) -> Optional[dict[str, Any]]:
    raw = (content or "").strip()
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    return data if isinstance(data, dict) else None


def fingerprint_homeostasis_payload(data: dict[str, Any]) -> str:
    """Stable hash of the fields that define 'same stuck sensor reading'."""
    slice_: dict[str, Any] = {
        "metrics_aligned": data.get("metrics_aligned"),
        "homeostasis_achieved": data.get("homeostasis_achieved"),
        "hitl_required": data.get("hitl_required"),
        "deviations": data.get("deviations"),
        "loop_mode_hint": data.get("loop_mode_hint"),
    }
    # Prefer compact alert ids when present under tp_sl_monitor / deviations.
    monitor = data.get("tp_sl_monitor")
    if isinstance(monitor, dict):
        levels = monitor.get("levels")
        if isinstance(levels, list):
            slice_["level_ids"] = [
                {
                    "ticker": (lv.get("ticker") or lv.get("symbol") or ""),
                    "breached": lv.get("breached"),
                    "sl": lv.get("sl") or lv.get("stop_loss"),
                    "tp": lv.get("tp") or lv.get("take_profit"),
                }
                for lv in levels
                if isinstance(lv, dict)
            ][:24]
    blob = json.dumps(slice_, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]


def is_misaligned_without_hitl(data: dict[str, Any]) -> bool:
    metrics_aligned = data.get("metrics_aligned")
    achieved = data.get("homeostasis_achieved")
    hitl_required = data.get("hitl_required")
    aligned = metrics_aligned is True or achieved is True
    if aligned:
        return False
    if hitl_required is True:
        return False
    # Explicit false or missing → treat as not aligned (sensor ran, did not clear).
    if metrics_aligned is False or achieved is False:
        return True
    # Deviations present without alignment flags.
    deviations = data.get("deviations")
    if isinstance(deviations, dict) and deviations:
        return True
    if isinstance(deviations, list) and deviations:
        return True
    return False


def corrective_tools_from_payload(data: dict[str, Any]) -> list[str]:
    names: list[str] = []
    for key in ("skill_to_invoke", "corrective_tools", "recommended_tools"):
        raw = data.get(key)
        if isinstance(raw, str) and raw.strip():
            names.append(raw.strip())
        elif isinstance(raw, list):
            for item in raw:
                if isinstance(item, str) and item.strip():
                    names.append(item.strip())
                elif isinstance(item, dict):
                    n = str(item.get("tool") or item.get("name") or "").strip()
                    if n:
                        names.append(n)
    deviations = data.get("deviations")
    if isinstance(deviations, dict):
        for v in deviations.values():
            if isinstance(v, dict):
                n = str(v.get("skill_to_invoke") or v.get("tool") or "").strip()
                if n:
                    names.append(n)
    out: list[str] = []
    for n in names:
        if n not in out and n != "evaluate_homeostasis":
            out.append(n)
    return out[:6]


def record_homeostasis_observation(
    db: Any,
    chat_id: Any,
    data: dict[str, Any],
    *,
    tenant_id: str = "default",
) -> dict[str, Any]:
    """
    Update fingerprint/streak for this chat.

    Returns action dict:
      - action: "clear" | "nudge" | "escalate"
      - streak, fingerprint, corrective_tools
    """
    tid = str(tenant_id or "default").strip() or "default"
    cid = str(chat_id or "").strip()
    if not cid or db is None:
        return {"action": "clear", "streak": 0, "fingerprint": "", "corrective_tools": []}

    if not is_misaligned_without_hitl(data):
        persist_loop_chat_state(db, cid, LOOP_HOMEOSTASIS_FP_KEY, "", tenant_id=tid)
        persist_loop_chat_state(db, cid, LOOP_HOMEOSTASIS_STREAK_KEY, "0", tenant_id=tid)
        return {"action": "clear", "streak": 0, "fingerprint": "", "corrective_tools": []}

    fp = fingerprint_homeostasis_payload(data)
    prev_fp = (get_loop_chat_state(db, cid, LOOP_HOMEOSTASIS_FP_KEY) or "").strip()
    try:
        prev_streak = int((get_loop_chat_state(db, cid, LOOP_HOMEOSTASIS_STREAK_KEY) or "0").strip() or "0")
    except ValueError:
        prev_streak = 0

    if fp == prev_fp:
        streak = prev_streak + 1
    else:
        streak = 1

    persist_loop_chat_state(db, cid, LOOP_HOMEOSTASIS_FP_KEY, fp, tenant_id=tid)
    persist_loop_chat_state(db, cid, LOOP_HOMEOSTASIS_STREAK_KEY, str(streak), tenant_id=tid)

    limit = homeostasis_stuck_streak_limit()
    tools = corrective_tools_from_payload(data)
    if streak >= limit:
        return {
            "action": "escalate",
            "streak": streak,
            "fingerprint": fp,
            "corrective_tools": tools,
            "limit": limit,
        }
    return {
        "action": "nudge",
        "streak": streak,
        "fingerprint": fp,
        "corrective_tools": tools,
        "limit": limit,
    }


def build_stuck_nudge_message(*, streak: int, corrective_tools: list[str], escalate: bool) -> str:
    tools_txt = ", ".join(corrective_tools) if corrective_tools else "(tools de corrección del worker)"
    if escalate:
        return (
            "[SYSTEM_EVENT: LOOP_HOMEOSTASIS_STUCK] "
            f"evaluate_homeostasis devolvió el mismo resultado misaligned {streak} veces "
            "sin hitl_required. NO vuelvas a llamar evaluate_homeostasis con el mismo informe. "
            "Escala: llama request_homeostasis_validation con escalate_stuck=true "
            "(explica desviaciones al usuario) o pause_chat_autonomy si no hay acción segura. "
            f"Herramientas correctivas sugeridas: {tools_txt}."
        )
    return (
        "[SYSTEM_EVENT: LOOP_HOMEOSTASIS_NUDGE] "
        f"evaluate_homeostasis misaligned (racha {streak}) sin HITL. "
        "NO re-reportes el mismo sensor. Corrige desviaciones con tools del worker "
        f"({tools_txt}) o pide decisión al usuario. "
        "Solo vuelve a evaluate_homeostasis después de una corrección real."
    )


def maybe_append_homeostasis_stuck_nudge(
    new_msgs: list[Any],
    *,
    db: Any,
    state: dict[str, Any],
) -> list[Any]:
    """If last evaluate_homeostasis is stuck, append a SYSTEM nudge HumanMessage."""
    try:
        from langchain_core.messages import HumanMessage
    except Exception:
        return new_msgs
    try:
        for tm in reversed(new_msgs):
            if getattr(tm, "name", None) != "evaluate_homeostasis":
                continue
            payload = parse_homeostasis_tool_payload(str(getattr(tm, "content", "") or ""))
            if not payload:
                break
            chat = state.get("chat_id") or state.get("session_id") or ""
            tid = (state.get("tenant_id") or "").strip() or "default"
            obs = record_homeostasis_observation(db, chat, payload, tenant_id=tid)
            action = str(obs.get("action") or "")
            if action in ("nudge", "escalate"):
                return list(new_msgs) + [
                    HumanMessage(
                        content=build_stuck_nudge_message(
                            streak=int(obs.get("streak") or 0),
                            corrective_tools=list(obs.get("corrective_tools") or []),
                            escalate=action == "escalate",
                        )
                    )
                ]
            break
    except Exception:
        return new_msgs
    return new_msgs

