"""Invocación LLM y política de síntesis NL para Telegram y consola admin."""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from duckclaw.egress.user_reply_nl_config import (
    _MAX_EVIDENCE_CHARS,
    _MAX_SYNTH_TOKENS,
    admin_nl_synthesis_max_output_tokens,
    admin_reply_already_polished,
    nl_reply_synthesis_globally_disabled,
)
from duckclaw.egress.user_reply_nl_reddit import (
    _body_looks_like_reddit_compact_listing_markdown,
    _body_looks_like_reddit_mcp_listing_json,
    _combined_tool_blocks_contain_json,
    _combined_tool_blocks_snake_prose,
    _deterministic_reddit_compact_listing_summary,
)

_LOG = logging.getLogger(__name__)

def reply_needs_nl_synthesis(text: str) -> bool:
    """True si el texto es JSON puro o bloques ``### tool`` + JSON o prosa de tool (MLX / egress)."""
    from duckclaw.egress.tool_response_repair import reply_is_tool_label_json_echo

    s = (text or "").strip()
    if len(s) < 2:
        return False
    if _body_looks_like_reddit_compact_listing_markdown(s):
        return True
    if _body_looks_like_reddit_mcp_listing_json(s):
        return True
    if s.startswith("{") or s.startswith("["):
        try:
            json.loads(s)
            return True
        except json.JSONDecodeError:
            pass
    if _combined_tool_blocks_contain_json(s):
        return True
    if _combined_tool_blocks_snake_prose(s):
        return True
    for line in s.splitlines():
        if reply_is_tool_label_json_echo(line.strip()):
            return True
    return False


def _truncate_evidence(s: str, max_chars: int) -> str:
    if len(s) <= max_chars:
        return s
    return s[:max_chars] + "\n\n…[evidencia truncada para la síntesis]"


def synthesize_user_visible_reply(
    llm: Any,
    *,
    user_ask: str,
    raw_evidence: str,
    worker_id: str,
    max_evidence_chars: int | None = None,
    max_tokens: int | None = None,
    for_admin_console: bool = False,
) -> str:
    """Invoca el LLM sin tools; devuelve texto para el usuario o cadena vacía si falla."""
    from langchain_core.messages import HumanMessage, SystemMessage

    ev_limit = max_evidence_chars if max_evidence_chars is not None else _MAX_EVIDENCE_CHARS
    if max_tokens is not None:
        mt = max_tokens
    elif for_admin_console:
        mt = admin_nl_synthesis_max_output_tokens()
    else:
        mt = _MAX_SYNTH_TOKENS

    _reddit_listing_rules = ""
    if _body_looks_like_reddit_compact_listing_markdown(raw_evidence or ""):
        _reddit_listing_rules = (
            "\n- La evidencia es un listado compacto de Reddit (cabecera ## r/…): NO repitas todas las viñetas ni los "
            "enlaces uno por uno. Resume en 2–5 frases los temas dominantes y menciona como máximo 1–2 hilos si son "
            "centrales; luego **Siguientes pasos**."
        )
    if for_admin_console:
        _base_rules = (
            "Eres un asistente que redacta la respuesta FINAL al usuario en español, para la consola web DuckClaw.\n"
            "Reglas obligatorias:\n"
            "- Usa Markdown rico: **negritas**, listas con viñetas, encabezados ## cuando organicen el contenido.\n"
            "- Puedes usar 1–3 emojis por sección si aportan claridad (📊 💡 ⚠️ ✅).\n"
            "- No optimices el texto para audio/TTS: cifras en formato normal ($736.68, 10:19), no en palabras.\n"
            "- No pegues JSON, arrays, SQL ni bloques de código como cuerpo principal; parafrasea en prosa clara.\n"
            "- Toda cifra o nombre de dato debe salir solo de la evidencia entre <evidence> y </evidence>; no inventes.\n"
            "- Si la evidencia es un error técnico, explícalo con viñetas y rutas/archivos en `código` cuando aplique.\n"
            "- Termina con **Siguientes pasos** (1–2 acciones concretas) si tiene sentido."
            f"{_reddit_listing_rules}"
        )
    else:
        _base_rules = (
            "Eres un asistente que redacta la respuesta FINAL al usuario en español, para Telegram.\n"
            "Reglas obligatorias:\n"
            "- No pegues JSON, arrays, SQL ni bloques de código como cuerpo principal; parafrasea en prosa clara.\n"
            "- Usa Markdown ligero: **negritas**, listas con viñetas cuando ayuden.\n"
            "- Sé breve y directo; amplía solo si la evidencia lo exige.\n"
            "- Toda cifra o nombre de dato debe salir solo de la evidencia entre <evidence> y </evidence>; no inventes.\n"
            "- Termina con un apartado **Siguientes pasos** con 1–2 sugerencias concretas y útiles (sin inventar datos).\n"
            "- Si la evidencia es un error técnico, explícalo en lenguaje simple sin volver a pegar el JSON crudo entero."
            f"{_reddit_listing_rules}"
        )
    _sys_text = _base_rules
    sys = SystemMessage(content=_sys_text)
    ev = _truncate_evidence(raw_evidence or "", ev_limit)
    human = HumanMessage(
        content=(
            f"Worker: `{worker_id}`\n"
            f"Pregunta o tarea del usuario:\n{user_ask or '(sin texto)'}\n\n"
            f"<evidence>\n{ev}\n</evidence>\n\n"
            "Redacta solo la respuesta al usuario."
        )
    )

    from duckclaw.integrations.llm_providers import invoke_chat_model_with_transient_retries

    try:
        try:
            resp = invoke_chat_model_with_transient_retries(llm, [sys, human], max_tokens=mt)
        except TypeError:
            resp = invoke_chat_model_with_transient_retries(llm, [sys, human])
    except Exception:
        _LOG.warning("nl_reply_synthesis: invoke failed", exc_info=True)
        return ""
    out = getattr(resp, "content", None)
    if out is None:
        out = str(resp)
    if isinstance(out, list):
        parts: list[str] = []
        for b in out:
            if isinstance(b, dict) and isinstance(b.get("text"), str):
                parts.append(b["text"])
            else:
                parts.append(str(b))
        out = "".join(parts)
    result = (str(out) or "").strip()
    return result


def maybe_synthesize_reply(
    llm: Any | None,
    *,
    spec: Any,
    user_ask: str,
    reply_candidate: str,
    for_admin_console: bool = False,
) -> str:
    """
    Si aplica política + heurística, sustituye ``reply_candidate`` por síntesis LLM.
    ``spec`` debe tener ``egress_natural_language_synthesis`` y ``worker_id``.

    Listado compacto Reddit: aunque ``DUCKCLAW_DISABLE_NL_REPLY_SYNTHESIS`` esté activo o el LLM
    devuelva vacío/echo del listado, se aplica un resumen **determinístico** (sin segundo modelo).
    """
    rc_compact = _body_looks_like_reddit_compact_listing_markdown(reply_candidate)

    def _reddit_det_or(candidate: str) -> str:
        if not _body_looks_like_reddit_compact_listing_markdown(candidate):
            return candidate
        det = _deterministic_reddit_compact_listing_summary(candidate)
        return det if det else candidate

    if llm is None:
        return _reddit_det_or(reply_candidate)
    if nl_reply_synthesis_globally_disabled():
        return _reddit_det_or(reply_candidate)
    if not bool(getattr(spec, "egress_natural_language_synthesis", True)):
        return _reddit_det_or(reply_candidate)
    if for_admin_console and admin_reply_already_polished(reply_candidate):
        return reply_candidate
    if not reply_needs_nl_synthesis(reply_candidate):
        return reply_candidate
    wid = str(getattr(spec, "worker_id", "") or "").strip() or "worker"
    synthesized = synthesize_user_visible_reply(
        llm,
        user_ask=(user_ask or "").strip(),
        raw_evidence=reply_candidate,
        worker_id=wid,
        for_admin_console=for_admin_console,
    )
    syn_st = (synthesized or "").strip()
    if rc_compact and (not syn_st or _body_looks_like_reddit_compact_listing_markdown(syn_st)):
        det = _deterministic_reddit_compact_listing_summary(reply_candidate)
        if det:
            return det
    return syn_st if syn_st else reply_candidate


def admin_display_reply_needs_enrichment(text: str) -> bool:
    """Consola admin: enriquecer prosa plana (sin **/##/emoji) para lectura web."""
    t = (text or "").strip()
    if len(t) < 10:
        return False
    if "**" in t or "##" in t:
        return False
    if any(ord(c) > 0x2600 for c in t[:800]):
        return False
    return True


def maybe_enrich_admin_display_reply(
    llm: Any | None,
    *,
    spec: Any,
    user_ask: str,
    reply_candidate: str,
    for_admin_console: bool,
) -> str:
    """
    Segunda pasada solo para admin UI cuando el modelo devolvió prosa tipo Telegram/TTS
    (``reply_needs_nl_synthesis`` no aplica porque no hay JSON ni bloques ``### tool``).
    """
    if not for_admin_console or llm is None:
        return reply_candidate
    if nl_reply_synthesis_globally_disabled():
        return reply_candidate
    rc = (reply_candidate or "").strip()
    if not admin_display_reply_needs_enrichment(rc):
        return reply_candidate
    wid = str(getattr(spec, "worker_id", "") or "").strip() or "worker"
    synthesized = synthesize_user_visible_reply(
        llm,
        user_ask=(user_ask or "").strip(),
        raw_evidence=rc,
        worker_id=wid,
        for_admin_console=True,
    )
    syn_st = (synthesized or "").strip()
    if syn_st:
        return syn_st
    return reply_candidate
