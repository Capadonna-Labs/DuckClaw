"""
Síntesis LLM de la respuesta visible al usuario (Telegram): evita JSON/SQL/código crudo.

Spec: specs/features/worker-telegram-natural-language-egress.md
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any

_LOG = logging.getLogger(__name__)


def state_evidence_for_context_summary_rescind(state: dict[str, Any]) -> str:
    """
    Texto del turno con posible ``[SYSTEM_DIRECTIVE: SUMMARIZE_*]``.

    Algunos grafos (p. ej. ``StateGraph(dict)`` con canal ``__root__``) o rutas paralelas
    pueden dejar ``incoming`` vacío al llegar a ``set_reply``; el volcado sigue en el último
    ``HumanMessage`` que añadió ``prepare_node``.

    No hacer ``break`` tras el primer ``HumanMessage`` visto desde el final: si ese mensaje
    no trae la directiva (p. ej. ``content`` en bloques, o un turno de corrección previo),
    el volcado de ``/context`` puede estar en un humano anterior y sin esto ``rescind`` no
    construye el resumen determinístico.
    """
    from langchain_core.messages import HumanMessage

    from duckclaw.integrations.llm_providers import lc_message_content_to_text

    def _field_str(key: str) -> str:
        v = state.get(key)
        if isinstance(v, str):
            return v.strip().lstrip("\ufeff")
        return str(v or "").strip()

    for key in ("incoming", "input"):
        s = _field_str(key)
        if s and incoming_has_context_summarize_directive(s):
            return s

    for m in reversed(state.get("messages") or []):
        if not isinstance(m, HumanMessage):
            continue
        human_txt = lc_message_content_to_text(m).strip()
        if human_txt and incoming_has_context_summarize_directive(human_txt):
            return human_txt

    return _field_str("incoming") or _field_str("input")

SUMMARIZE_NEW_CONTEXT_MARK = "[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]"
SUMMARIZE_STORED_CONTEXT_MARK = "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]"

_MAX_EVIDENCE_CHARS = 12000
_MAX_SYNTH_TOKENS = 768

_FOOTER_HINTS = (
    "este bloque se obtuvo",
    "sintetiza en bullet",
    "no digas que acabas de guardar",
)


def _strip_summarize_instruction_tail(s: str) -> str:
    """Quita colas tipo «Sintetiza…» que el gateway añade al volcado."""
    lines_out: list[str] = []
    for ln in (s or "").splitlines():
        low = ln.strip().lower()
        if any(low.startswith(h) for h in _FOOTER_HINTS):
            break
        lines_out.append(ln)
    return "\n".join(lines_out).strip()


def _deterministic_stored_context_summary(evidence: str) -> str:
    """
    Último recurso si el LLM sigue devolviendo un ack trivial: viñetas desde ``--- registro N ---``.
    Sin segunda llamada al modelo (spec: el usuario no debe quedar sin resumen útil).
    """
    s = (evidence or "").strip()
    if not s:
        return ""
    for mark in (SUMMARIZE_NEW_CONTEXT_MARK, SUMMARIZE_STORED_CONTEXT_MARK):
        if mark in s:
            i = s.find(mark)
            s = s[i + len(mark) :].lstrip()
            break
    s = _strip_summarize_instruction_tail(s)
    if not s:
        return ""
    parts = re.split(r"---\s*registro\s+\d+[^\n]*---\s*\n", s, flags=re.IGNORECASE)
    bullets: list[str] = []
    seen_lower: set[str] = set()
    for raw in parts:
        t = (raw or "").strip()
        if not t:
            continue
        block = t.split("\n\n", 1)[0].strip()
        if len(block) > 420:
            block = block[:417] + "…"
        k = block.lower()
        if block and k not in seen_lower:
            seen_lower.add(k)
            bullets.append(block)
        if len(bullets) >= 24:
            break
    if not bullets:
        for ln in s.splitlines():
            x = ln.strip()
            if len(x) < 4:
                continue
            if x.startswith("[") and "DIRECTIVE" in x:
                continue
            if x.startswith("---"):
                continue
            kl = x.lower()
            if kl in seen_lower:
                continue
            seen_lower.add(kl)
            bullets.append(x[:420])
            if len(bullets) >= 20:
                break
    if not bullets:
        return ""
    body_lines = ["**Resumen del contexto (base de datos)**", ""]
    for b in bullets:
        body_lines.append(f"- {b}")
    body_lines.extend(
        [
            "",
            "**Siguientes pasos**",
            "- Revisa enlaces guardados si necesitas profundizar en un tema.",
            "- Añade hechos nuevos con `/context --add` para mantener la memoria al día.",
        ]
    )
    return "\n".join(body_lines)


def telegram_stored_context_summary_body_when_model_trivial(
    directive_full_text: str,
    model_reply_plain: str,
    *,
    html_header_will_duplicate_title: bool,
) -> str | None:
    """
    Pipeline ``/context --summary`` (Telegram): si el worker devolvió un ack trivial pese al volcado
    en la directiva, construir el cuerpo desde ``--- registro N ---`` (mismo parser que ``set_reply``).

    Cuando el gateway ya antepone ``<b>Resumen del contexto…</b>`` en HTML, quitar el título Markdown
    del bloque determinístico para no duplicar encabezado.
    """
    if not (directive_full_text or "").strip() or not (model_reply_plain or "").strip():
        return None
    if not incoming_has_context_summarize_directive(directive_full_text):
        return None
    if not reply_is_trivial_for_context_summary(model_reply_plain):
        return None
    det = _deterministic_stored_context_summary(directive_full_text)
    if not det:
        return None
    out = det.strip()
    if html_header_will_duplicate_title:
        out = re.sub(
            r"^\*\*Resumen del contexto \(base de datos\)\*\*\s*\n+",
            "",
            out,
            count=1,
        ).strip()
    return out or None


def nl_reply_synthesis_globally_disabled() -> bool:
    v = (os.environ.get("DUCKCLAW_DISABLE_NL_REPLY_SYNTHESIS") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def incoming_has_context_summarize_directive(text: str) -> bool:
    """True si el turno viene de ``/context --add`` o ``--summary`` (gateway)."""
    s = text or ""
    return SUMMARIZE_NEW_CONTEXT_MARK in s or SUMMARIZE_STORED_CONTEXT_MARK in s


def reply_is_trivial_for_context_summary(reply: str) -> bool:
    """
    Heurística: el modelo devolvió un ack vacío (p. ej. «Listo.») en un turno que debía sintetizar
    un volcado largo de memoria semántica.
    """
    s = (reply or "").strip()
    if not s:
        return True
    body = re.sub(r"^[^\n]+\s+\d+\s*\n+", "", s, count=1).strip()
    if not body:
        return True
    # MLX/OpenAI-compat suele envolver el ack en **negritas**; sin normalizar, la rama ``**``
    # más abajo marca «no trivial» y rescind nunca llama a la segunda síntesis.
    body_plain = re.sub(r"[`*_]+", "", body).strip()
    low_plain = body_plain.lower()
    if len(body_plain) <= 56 and re.match(
        r"^(listo|ok|hecho|vale|correcto|done|ready)\.?\s*$", low_plain
    ):
        return True
    low = body.lower()
    if len(body) <= 48 and re.match(r"^(listo|ok|hecho|vale|correcto|done|ready)\.?\s*$", low):
        return True
    if len(body) >= 500:
        return False
    first_ln = body.lstrip().split("\n", 1)[0].strip()
    if first_ln.startswith(("- ", "* ", "• ")):
        return False
    if any(x in body for x in ("•", "\n-", "\n*", "\n1.", "**")):
        return False
    lines = [ln for ln in body.splitlines() if ln.strip()]
    if len(lines) <= 4 and len(body) < 420:
        return True
    return False


def context_summary_synthesis_has_useful_bullets(reply: str) -> bool:
    """
    Al menos una viñeta con texto sustantivo (no solo «Listo.» / ack).

    Sirve para: (1) aceptar síntesis LLM tras rescind; (2) **entrada** al pipeline rescind:
    si el modelo devuelve ``**Resumen…**`` + «Listo.», ``reply_is_trivial_for_context_summary``
    da «no trivial» por la rama ``**`` y antes se hacía ``return`` sin segunda pasada — bug.
    """
    _ack_only = re.compile(
        r"^(listo|ok|hecho|vale|correcto|done|ready|n/a)\.?\s*$",
        re.IGNORECASE,
    )
    for ln in (reply or "").splitlines():
        t = ln.lstrip()
        if len(t) < 4:
            continue
        m = re.match(r"^[-*•]\s+(.+)$", t)
        if not m:
            m = re.match(r"^\d{1,2}\.\s+(.+)$", t)
        if not m:
            continue
        rest = re.sub(r"[`*_]+", "", (m.group(1) or "")).strip()
        if len(rest) < 8:
            continue
        if _ack_only.match(rest):
            continue
        return True
    return False


def context_summary_synthesis_acceptable(syn: str) -> bool:
    """
    True si la segunda pasada LLM aporta un resumen útil: viñetas sustantivas **o**
    prosa no trivial con longitud mínima y al menos dos frases (sin depender de ``- ``).
    """
    s = (syn or "").strip()
    if not s:
        return False
    if context_summary_synthesis_has_useful_bullets(s):
        return True
    if reply_is_trivial_for_context_summary(s):
        return False
    plain = re.sub(r"[`*_#]+", "", s).strip()
    if len(plain) < 120:
        return False
    chunks = re.split(r"(?<=[.!?])\s+", plain)
    substantive = [c for c in chunks if len(c.strip()) > 24]
    return len(substantive) >= 2


def rescind_trivial_context_summary_reply(
    llm: Any | None,
    spec: Any,
    *,
    incoming: str,
    reply_candidate: str,
) -> str:
    """
    Segunda pasada NL: MLX a veces responde «Listo.» tras un prompt enorme de SUMMARIZE_*.
    Re-sintetiza usando el volcado del ``incoming`` como evidencia (truncado en ``synthesize_*``).
    Orden: segunda pasada LLM si hay modelo y egress NL; si la síntesis no es aceptable,
    ``_deterministic_stored_context_summary`` (viñetas desde ``--- registro ---``).
    """
    inc = (incoming or "").strip()
    if not incoming_has_context_summarize_directive(inc):
        return reply_candidate

    det = _deterministic_stored_context_summary(inc)

    if context_summary_synthesis_has_useful_bullets(reply_candidate):
        return reply_candidate

    if llm is None:
        return det or reply_candidate
    if nl_reply_synthesis_globally_disabled():
        return det or reply_candidate
    if not bool(getattr(spec, "egress_natural_language_synthesis", True)):
        return det or reply_candidate

    wid = str(getattr(spec, "worker_id", "") or "").strip() or "worker"
    syn = synthesize_user_visible_reply(
        llm,
        user_ask=(
            "Directiva del sistema: el usuario pidió resumen de memoria semántica (/context). "
            "Redacta en español un resumen en **lenguaje natural**: párrafos breves y/o viñetas; "
            "agrupa por tema si encaja; usa solo datos del volcado; no inventes. "
            "Incluye **Siguientes pasos** con 1–2 ideas accionables. "
            "Prohibido contestar solo «listo» o vacío."
        ),
        raw_evidence=inc,
        worker_id=wid,
    )
    syn_st = (syn or "").strip()
    if context_summary_synthesis_acceptable(syn_st):
        return syn_st
    if det:
        return det
    return reply_candidate


def reply_needs_nl_synthesis(text: str) -> bool:
    """True si el texto es JSON objeto/array parseable (salida típica de tools o MLX)."""
    s = (text or "").strip()
    if len(s) < 2:
        return False
    if not (s.startswith("{") or s.startswith("[")):
        return False
    try:
        json.loads(s)
    except json.JSONDecodeError:
        return False
    return True


def _truncate_evidence(s: str) -> str:
    if len(s) <= _MAX_EVIDENCE_CHARS:
        return s
    return s[:_MAX_EVIDENCE_CHARS] + "\n\n…[evidencia truncada para la síntesis]"


def synthesize_user_visible_reply(
    llm: Any,
    *,
    user_ask: str,
    raw_evidence: str,
    worker_id: str,
) -> str:
    """Invoca el LLM sin tools; devuelve texto para el usuario o cadena vacía si falla."""
    from langchain_core.messages import HumanMessage, SystemMessage

    sys = SystemMessage(
        content=(
            "Eres un asistente que redacta la respuesta FINAL al usuario en español, para Telegram.\n"
            "Reglas obligatorias:\n"
            "- No pegues JSON, arrays, SQL ni bloques de código como cuerpo principal; parafrasea en prosa clara.\n"
            "- Usa Markdown ligero: **negritas**, listas con viñetas cuando ayuden.\n"
            "- Sé breve y directo; amplía solo si la evidencia lo exige.\n"
            "- Toda cifra o nombre de dato debe salir solo de la evidencia entre <evidence> y </evidence>; no inventes.\n"
            "- Termina con un apartado **Siguientes pasos** con 1–2 sugerencias concretas y útiles (sin inventar datos).\n"
            "- Si la evidencia es un error técnico, explícalo en lenguaje simple sin volver a pegar el JSON crudo entero."
        )
    )
    ev = _truncate_evidence(raw_evidence or "")
    human = HumanMessage(
        content=(
            f"Worker: `{worker_id}`\n"
            f"Pregunta o tarea del usuario:\n{user_ask or '(sin texto)'}\n\n"
            f"<evidence>\n{ev}\n</evidence>\n\n"
            "Redacta solo la respuesta al usuario."
        )
    )
    try:
        try:
            resp = llm.invoke([sys, human], max_tokens=_MAX_SYNTH_TOKENS)
        except TypeError:
            resp = llm.invoke([sys, human])
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
    return (str(out) or "").strip()


def maybe_synthesize_reply(
    llm: Any | None,
    *,
    spec: Any,
    user_ask: str,
    reply_candidate: str,
) -> str:
    """
    Si aplica política + heurística, sustituye ``reply_candidate`` por síntesis LLM.
    ``spec`` debe tener ``egress_natural_language_synthesis`` y ``worker_id``.
    """
    if llm is None:
        return reply_candidate
    if nl_reply_synthesis_globally_disabled():
        return reply_candidate
    if not bool(getattr(spec, "egress_natural_language_synthesis", True)):
        return reply_candidate
    if not reply_needs_nl_synthesis(reply_candidate):
        return reply_candidate
    wid = str(getattr(spec, "worker_id", "") or "").strip() or "worker"
    synthesized = synthesize_user_visible_reply(
        llm,
        user_ask=(user_ask or "").strip(),
        raw_evidence=reply_candidate,
        worker_id=wid,
    )
    return synthesized if synthesized else reply_candidate
