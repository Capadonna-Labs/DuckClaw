"""
Egress guard para PQRSD-Assistant: el modelo a veces afirma registro + MDE-… sin ejecutar
admin_sql ni pqrsd_registrar_radicacion_crm (evidencia: gateway «tools usadas=ninguna» + fila ausente en DuckDB).
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path
from typing import Any

_PQRSD_PERSIST_TOOLS = frozenset({"admin_sql", "pqrsd_registrar_radicacion_crm"})

_rr = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
_REPO = Path(_rr).resolve() if _rr else Path(__file__).resolve().parents[5]
_DEBUG_LOG = Path(os.environ.get("DUCKCLAW_DEBUG_PQRSD_LOG") or _REPO / ".cursor" / "debug-8d6707.log")

_CLAIMS = re.compile(
    r"(Radicado\s+interno\s*:|quedó\s+registrad[oa]\s+en\s+el\s+sistema\s+interno|"
    r"✅[^\n]*registrad[oa]\s+en\s+el\s+sistema\s+interno)",
    re.IGNORECASE | re.DOTALL,
)


def _append_debug_ndjson(payload: dict[str, Any]) -> None:
    try:
        _DEBUG_LOG.parent.mkdir(parents=True, exist_ok=True)
        with _DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except OSError:
        pass


def pqrsd_reply_claims_internal_registration(reply: str) -> bool:
    text = (reply or "").strip()
    if len(text) < 20:
        return False
    if _CLAIMS.search(text):
        return True
    if re.search(r"MDE-\d{8}-\d{4}", text) and (
        "registrad" in text.lower() or "radicado" in text.lower()
    ):
        return True
    return False


def pqrsd_persist_tool_used(tool_names: list[str] | None) -> bool:
    for n in tool_names or []:
        if (n or "").strip() in _PQRSD_PERSIST_TOOLS:
            return True
    return False


def pqrsd_guard_registration_egress(
    reply: str,
    tool_names: list[str] | None,
    *,
    session_id: str = "",
) -> str:
    """
    Si el texto parece confirmar radicación interna pero no hubo herramienta de escritura,
    sustituye por un mensaje honesto (no inventar MDE-…).
    """
    if not pqrsd_reply_claims_internal_registration(reply):
        _append_debug_ndjson(
            {
                "sessionId": "8d6707",
                "timestamp": int(time.time() * 1000),
                "location": "pqrsd_registration_egress_guard.py:guard",
                "message": "skip_no_claim",
                "data": {"tools": tool_names or []},
                "hypothesisId": "H-pqrsd-egress",
                "runId": "verify-guard",
            }
        )
        return reply
    if pqrsd_persist_tool_used(tool_names):
        _append_debug_ndjson(
            {
                "sessionId": "8d6707",
                "timestamp": int(time.time() * 1000),
                "location": "pqrsd_registration_egress_guard.py:guard",
                "message": "allow_persist_tool",
                "data": {"tools": tool_names or []},
                "hypothesisId": "H-pqrsd-egress",
                "runId": "verify-guard",
            }
        )
        return reply
    _append_debug_ndjson(
        {
            "sessionId": "8d6707",
            "timestamp": int(time.time() * 1000),
            "location": "pqrsd_registration_egress_guard.py:guard",
            "message": "block_hallucinated_registration",
            "data": {"tools": tool_names or [], "session_id": session_id[:64]},
            "hypothesisId": "H-pqrsd-egress",
            "runId": "verify-guard",
        }
    )
    return (
        "⚠️ No pude confirmar el registro en la bóveda: en este turno no se ejecutó la herramienta de "
        "escritura en DuckDB (`admin_sql` o `pqrsd_registrar_radicacion_crm`). "
        "Tu caso no quedó guardado todavía. Reintenta escribiendo **autorizo** de nuevo; si persiste, "
        "quien administra el sistema debe revisar el gateway y la cola del db-writer."
    )
