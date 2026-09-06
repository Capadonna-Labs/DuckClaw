"""Inyecta diagnóstico del lienzo HTML en turnos admin playground."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

_log = logging.getLogger("duckclaw.gateway.playground.canvas")

_MAX_TOOL_ERROR_DETAIL = 320


def sanitize_tool_error_detail(detail: str) -> str:
    s = re.sub(r"\s+", " ", (detail or "").strip())
    if len(s) > _MAX_TOOL_ERROR_DETAIL:
        return s[: _MAX_TOOL_ERROR_DETAIL - 1] + "…"
    return s


def enrich_message_with_canvas_context(*, msg: str, chat_id: str, vault_path: str) -> str:
    """Antepone estado del dashboard HTML cuando la fila en DB está ausente o inválida."""
    cid = (chat_id or "").strip()
    vp = (vault_path or "").strip()
    if not cid.startswith("admin-conv-") or not vp:
        return msg
    try:
        from duckclaw.forge.skills.custom_reports_bridge import _inspect_custom_report_impl
        from routers.admin_domains.playground.vault_access import open_playground_vault_db

        db = open_playground_vault_db(vp, read_only=True)
        try:
            raw = _inspect_custom_report_impl(db, report_id=cid)
        finally:
            db.close()
        payload: dict[str, Any] = json.loads(raw)
    except Exception as exc:
        _log.debug("canvas context skip chat_id=%r: %s", cid, exc)
        return msg
    status = str(payload.get("status") or "")
    if status == "valid":
        return msg
    block = (
        "[LIENZO_HTML_ESTADO] El dashboard HTML de esta conversación NO se puede renderizar.\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}\n"
        "Acción: inspect_custom_report(report_id=chat_id); republica HTML COMPLETO con "
        "publish_custom_report, o delega a un worker de reporting vía invoke_worker si tienes "
        "uno en allowed_delegates. NO uses execute_sandbox_script ni run_sandbox para HTML.\n"
    )
    body = (msg or "").strip()
    if body:
        return f"{block}\n--- Mensaje del usuario ---\n{body}"
    return block
