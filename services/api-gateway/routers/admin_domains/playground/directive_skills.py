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

_log = logging.getLogger("duckclaw.gateway.playground.directive_skills")


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
    if not (msg or "").strip().startswith("/"):
        return msg, None
    try:
        from core.admin_identity import open_gateway_db
        from duckclaw.directive_skills import expand_directive_skill

        with open_gateway_db(read_only=True) as db:
            return expand_directive_skill(db, msg, tenant_id=tenant_id, actor_email=actor_email)
    except Exception as exc:  # noqa: BLE001
        _log.debug("directive skill lookup skip: %s", exc)
        return msg, None
