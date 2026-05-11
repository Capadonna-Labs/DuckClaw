"""
Egress guard para PQRSD-Assistant: el modelo a veces afirma registro + MDE-… sin ejecutar
admin_sql ni pqrsd_registrar_radicacion_crm (evidencia: gateway «tools usadas=ninguna» + fila ausente en DuckDB).
"""

from __future__ import annotations

import re

_PQRSD_PERSIST_TOOLS = frozenset({"admin_sql", "pqrsd_registrar_radicacion_crm"})

_CLAIMS = re.compile(
    r"(Radicado\s+interno\s*:|quedó\s+registrad[oa]\s+en\s+el\s+sistema\s+interno|"
    r"✅[^\n]*registrad[oa]\s+en\s+el\s+sistema\s+interno)",
    re.IGNORECASE | re.DOTALL,
)


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
        return reply
    if pqrsd_persist_tool_used(tool_names):
        return reply
    return (
        "⚠️ No pude confirmar el registro en la bóveda: en este turno no se ejecutó la herramienta de "
        "escritura en DuckDB (`admin_sql` o `pqrsd_registrar_radicacion_crm`). "
        "Tu caso no quedó guardado todavía. Reintenta escribiendo **autorizo** de nuevo; si persiste, "
        "quien administra el sistema debe revisar el gateway y la cola del db-writer."
    )
