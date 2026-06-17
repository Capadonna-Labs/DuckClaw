"""Mercenary ephemeral sandbox node."""

from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Callable

from duckclaw.graphs.state import ManagerAgentState

_log = logging.getLogger(__name__)


def build_mercenary_node(
    *,
    db: Any,
) -> Callable[[ManagerAgentState], ManagerAgentState]:
    from duckclaw.graphs.activity import set_idle
    from duckclaw.graphs.on_the_fly_commands import append_task_audit
    from duckclaw.graphs.sandbox import run_mercenary_ephemeral

    def mercenary_node(state: ManagerAgentState) -> ManagerAgentState:
        """Ejecución efímera Caged Beast: Docker aislado → result.json → respuesta (sin invoke_worker)."""
        from duckclaw.graphs.activity import set_idle
        from duckclaw.graphs.on_the_fly_commands import append_task_audit
        from duckclaw.graphs.sandbox import run_mercenary_ephemeral

        chat_id = state.get("chat_id") or ""
        incoming = (state.get("incoming") or state.get("input") or state.get("message") or "").strip()
        plan_title = (state.get("plan_title") or "").strip() or None
        spec = state.get("mercenary_spec")
        assigned = (state.get("assigned_worker_id") or "").strip() or None

        if not isinstance(spec, dict) or not str(spec.get("directive") or "").strip():
            set_idle(chat_id)
            return {
                "reply": "No se pudo ejecutar el mercenario: especificación inválida.",
                "_audit_done": True,
                "assigned_worker_id": assigned,
            }  # type: ignore[return-value]

        directive = str(spec.get("directive") or "").strip()
        timeout_m = max(1, min(int(spec.get("timeout") or 300), 600))
        task_id = uuid.uuid4().hex[:20]
        t0 = time.monotonic()
        result = run_mercenary_ephemeral(directive, timeout_m, task_id=task_id)
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        ok = bool(result.get("ok"))
        status = "SUCCESS" if ok else "FAILED"
        try:
            append_task_audit(
                db,
                chat_id,
                "manager",
                incoming[:2000] if incoming else "(mercenary)",
                status,
                elapsed_ms,
                plan_title=plan_title or "Mercenario (sandbox)",
            )
        except Exception:
            pass
        set_idle(chat_id)

        if ok:
            payload = result.get("result") or {}
            body = json.dumps(payload, ensure_ascii=False, indent=2)
            if len(body) > 7500:
                body = body[:7500] + "\n…"
            reply = "**Mercenario (sandbox)** — ejecución aislada completada.\n\n```json\n" + body + "\n```"
        else:
            code = result.get("error_code") or "MERCENARY_ERROR"
            msg = (result.get("message") or "").strip()
            reply = f"**Mercenario:** error `{code}`\n\n{msg}"

        _log.info(
            "manager mercenary: ok=%s code=%s",
            ok,
            result.get("error_code") if not ok else "ok",
        )

        out: ManagerAgentState = {
            "reply": reply,
            "_audit_done": True,
            "assigned_worker_id": assigned,
            "plan_title": plan_title,
        }  # type: ignore[assignment]
        if "history" in state:
            out["history"] = state["history"]
        if "chat_id" in state:
            out["chat_id"] = state["chat_id"]
        if "tenant_id" in state:
            out["tenant_id"] = state["tenant_id"]
        if "user_id" in state:
            out["user_id"] = state["user_id"]
        if "vault_db_path" in state:
            out["vault_db_path"] = state["vault_db_path"]
        if "shared_db_path" in state:
            out["shared_db_path"] = state["shared_db_path"]
        if "username" in state:
            out["username"] = state["username"]
        if "available_templates" in state:
            out["available_templates"] = state["available_templates"]
        _ot_m = (state.get("outbound_telegram_bot_token") or "").strip()
        if _ot_m:
            out["outbound_telegram_bot_token"] = _ot_m
        return out

    return mercenary_node
