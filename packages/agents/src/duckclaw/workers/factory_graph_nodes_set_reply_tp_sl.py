"""TP/SL rewrite, breach heartbeat, and position-metrics retry for set_reply."""

from __future__ import annotations

import logging
from typing import Any, Callable

_log = logging.getLogger(__name__)


def apply_tp_sl_rewrite_and_breach_alerts(
    *,
    reply: str,
    messages: list[Any],
    state: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    """Rewrite reply with deterministic TP/SL section; emit breach heartbeats."""
    from duckclaw.position_metrics import apply_deterministic_tp_sl_rewrite

    rewritten, meta = apply_deterministic_tp_sl_rewrite(reply or "", messages)
    if meta.get("rewrote"):
        _log.info(
            "Position metrics rewrite: levels=%s claims_before=%s",
            meta.get("levels_found"),
            meta.get("claims_before"),
        )
        reply = rewritten
    breaches = list(meta.get("breaches") or [])
    if not breaches:
        return reply, state
    try:
        from duckclaw.graphs.chat_heartbeat import (
            is_admin_ui_chat_session,
            publish_admin_chat_heartbeat,
        )

        chat_hb = str(state.get("chat_id") or state.get("session_id") or "")
        if not (chat_hb and is_admin_ui_chat_session(chat_hb)):
            return reply, state
        seen = set(state.get("_tp_sl_breach_alerted") or [])
        new_seen = set(seen)
        for br in breaches:
            key = f"{br.get('ticker')}:{br.get('breached')}"
            if key in new_seen:
                continue
            new_seen.add(key)
            publish_admin_chat_heartbeat(
                chat_hb,
                (
                    f"TP/SL BREACH {br.get('ticker')} "
                    f"{str(br.get('breached') or '').upper()} "
                    f"@ {br.get('price')} "
                    f"(sl={br.get('sl')} tp={br.get('tp')})"
                ),
                kind="tp_sl_breach",
            )
        state = {**state, "_tp_sl_breach_alerted": sorted(new_seen)}
    except Exception:
        pass
    return reply, state


def enforce_position_metrics_with_optional_retry(
    *,
    reply: str,
    messages: list[Any],
    state: dict[str, Any],
    spec: Any,
    rescind_incoming: str,
    identity_fields: Callable[[dict[str, Any]], dict[str, Any]],
    enforce_rule: Callable[..., tuple[str, str | None]],
    retry_reason: str,
    retry_system_message: Callable[[], Any],
) -> tuple[str, dict[str, Any] | None]:
    """
    Apply position-metrics evidence rule.

    Returns (reply, None) to continue, or (reply, out_dict) to early-return a graph retry.
    """
    from duckclaw.position_metrics import (
        apply_deterministic_tp_sl_rewrite,
        should_skip_position_metrics_retry,
        strip_tp_sl_pct_claims,
    )

    pm_reply, pm_reason = enforce_rule(reply=reply, messages=messages, spec=spec)
    if pm_reason != retry_reason:
        return (pm_reply if pm_reason else reply), None

    pm_count = int(state.get("position_metrics_retry_count") or 0)
    skip_retry = should_skip_position_metrics_retry(
        messages=messages,
        incoming=str(state.get("incoming") or rescind_incoming or ""),
        reply=reply or "",
    )
    if pm_count < 1 and not skip_retry:
        _log.warning("Position metrics audit: %s — in-graph retry", pm_reason)
        out_pm: dict[str, Any] = {
            **state,
            "messages": list(messages) + [retry_system_message()],
            "reply": "",
            "internal_reply": "",
            "position_metrics_retry_count": pm_count + 1,
            "position_metrics_graph_retry": True,
            "position_metrics_draft_reply": (reply or "").strip(),
        }
        out_pm.update(identity_fields(state))
        return reply, out_pm

    _log.warning(
        "Position metrics audit: %s — %s",
        pm_reason,
        "skip retry (AH/no levels)" if skip_retry else "retries exhausted",
    )
    draft = (state.get("position_metrics_draft_reply") or reply or "").strip()
    stripped = strip_tp_sl_pct_claims(draft)
    rewritten2, _ = apply_deterministic_tp_sl_rewrite(stripped or pm_reply, messages)
    return (rewritten2 or stripped or pm_reply), None
