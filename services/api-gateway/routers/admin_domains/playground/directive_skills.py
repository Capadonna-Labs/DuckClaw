"""Directive skills: instrucciones de texto invocables con "/nombre" en el chat.

Distinto de los skills "python" (tools LangGraph reales, ver
``duckclaw.workers.skill_tool_registry``) — un directive skill no ejecuta código,
solo antepone su ``description`` (guardada en ``main.admin_skills``) como
instrucción para este turno cuando el mensaje empieza con "/<nombre>". Mismo
catálogo DB-first que ya usa /catalog/skills (ver ``catalog_skills.py``); un
directive skill se crea con ``skill_type="directive"`` y normalmente
``visibility="public"`` para que cualquier worker del tenant pueda invocarlo.
"""

from __future__ import annotations

import logging
import re

_log = logging.getLogger("duckclaw.gateway.playground.directive_skills")

_SLASH_NAME = re.compile(r"^/([a-zA-Z][a-zA-Z0-9_.-]{1,63})\b\s*(.*)$", re.DOTALL)


def _fetchall(result: object) -> list:
    """``db.execute()`` puede devolver un cursor (``.fetchall()``) o ya una lista
    (mismo shim que ``catalog_skills.py``, mismo wrapper DuckClaw)."""
    if hasattr(result, "fetchall"):
        return list(result.fetchall())
    if isinstance(result, list):
        return result
    return []


def extract_directive_skill(
    msg: str, *, tenant_id: str, actor_email: str
) -> tuple[str, str | None]:
    """Si ``msg`` empieza con "/<directive_skill_activo>", devuelve
    ``(msg_con_instruccion_antepuesta, texto_limpio_sin_prefijo)``. El segundo valor
    reemplaza ``original_user_message`` — sin él, ``resolve_fly_command_text`` seguiría
    viendo el "/nombre" crudo y trataría esto como fly command, saltándose el
    enriquecimiento de documentos/imágenes de un turno normal.
    Si no matchea ningún directive skill activo, devuelve ``(msg, None)`` intacto
    (nunca lanza)."""
    t = (msg or "").strip()
    if not t.startswith("/"):
        return msg, None
    m = _SLASH_NAME.match(t)
    if not m:
        return msg, None
    name, rest = m.group(1), m.group(2)
    try:
        from core.admin_identity import open_gateway_db

        with open_gateway_db(read_only=True) as db:
            rows = _fetchall(
                db.execute(
                    """
                    SELECT description FROM main.admin_skills
                    WHERE active = true AND skill_type = 'directive'
                      AND tenant_id = ? AND (visibility = 'public' OR owner_email = ?)
                      AND lower(name) = lower(?)
                    """,
                    [tenant_id, actor_email, name],
                )
            )
    except Exception as exc:  # noqa: BLE001
        _log.debug("directive skill lookup skip name=%r: %s", name, exc)
        return msg, None
    if not rows:
        return msg, None
    description = str(rows[0][0] or "").strip()
    if not description:
        return msg, None
    injected = f"[DIRECTIVA ACTIVA: /{name}]\n{description}\n\n{rest}".strip()
    return injected, rest
