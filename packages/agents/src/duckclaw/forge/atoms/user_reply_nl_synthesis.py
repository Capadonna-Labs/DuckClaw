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
SUMMARIZE_IMAGE_MARK = "[SYSTEM_DIRECTIVE: SUMMARIZE_IMAGE]"
VLM_GATEWAY_DOWN_META = "[META: VLM_GATEWAY_DOWN]"

_MAX_EVIDENCE_CHARS = 12000
_MAX_SYNTH_TOKENS = 768
# 2.ª pasada tras SUMMARIZE_*: el turno principal ya llenó KV en MLX; evidencia más corta evita OOM Metal.
_DEFAULT_CONTEXT_SUMMARY_SYNTH_EVIDENCE = 4500
_DEFAULT_CONTEXT_SUMMARY_SYNTH_MAX_TOKENS = 512


def _parse_bounded_int_env(name: str, default: int, *, lo: int, hi: int) -> int:
    raw = (os.environ.get(name) or "").strip()
    if raw.isdigit():
        return max(lo, min(hi, int(raw)))
    return default


def context_summary_synthesis_evidence_char_limit() -> int:
    """Tope de caracteres de ``<evidence>`` solo en la síntesis NL de ``rescind_*`` (SUMMARIZE_*)."""
    return _parse_bounded_int_env(
        "DUCKCLAW_CONTEXT_SUMMARY_SYNTH_MAX_CHARS",
        _DEFAULT_CONTEXT_SUMMARY_SYNTH_EVIDENCE,
        lo=1200,
        hi=_MAX_EVIDENCE_CHARS,
    )


def context_summary_synthesis_max_output_tokens() -> int:
    return _parse_bounded_int_env(
        "DUCKCLAW_CONTEXT_SUMMARY_SYNTH_MAX_TOKENS",
        _DEFAULT_CONTEXT_SUMMARY_SYNTH_MAX_TOKENS,
        lo=128,
        hi=2048,
    )


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


_BARE_SUMMARIZE_STORED_REPLY = re.compile(
    r"^\s*\[SYSTEM_DIRECTIVE:\s*SUMMARIZE_STORED_CONTEXT\]\s*$",
    re.IGNORECASE,
)
_BARE_SUMMARIZE_IMAGE_REPLY = re.compile(
    r"^\s*\[SYSTEM_DIRECTIVE:\s*SUMMARIZE_IMAGE\]\s*$",
    re.IGNORECASE,
)

# Plantillas que Gemma/MLX suele inventar en turnos SUMMARIZE_NEW_CONTEXT (no vienen del texto pegado).
_NEW_CONTEXT_WRONG_ACCOUNT_TEMPLATES = (
    "los usuarios finales esperan",
    "¿qué te gustaría hacer con est",
    "próximas operaciones pendientes",
    "siguiente paso: ¿qué te gustaría",
)

# Términos de ledger local/IBKR: si aparecen en la respuesta pero no en el volcado NEW → alucinación probable.
_NEW_CONTEXT_LEDGER_LEXEMES = (
    "bancolombia",
    "nequi",
    "davivienda",
    "ibkr",
    "inversión ibkr",
    "inversion ibkr",
    "saldos guardados en la base",
    "total disponible en las cuentas locales",
    "efectivo disponible de",
)

_DEBUG_LOG_PATH_4A0206 = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-4a0206.log"
_NOISY_UNUSED_RE = re.compile(r"<unused\d+>", re.IGNORECASE)
_NON_ALNUM_TOKEN_RE = re.compile(r"[^\w<>/-]", re.UNICODE)

_DEBUG_LOG_PATH = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-adf9d8.log"


def _agent_debug_log(*, hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": "adf9d8",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(__import__("time").time() * 1000),
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as _f:
            _f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # endregion


def _deterministic_new_context_summary(evidence: str) -> str:
    """
    Viñetas solo desde el cuerpo del usuario en ``SUMMARIZE_NEW_CONTEXT`` (sin ``--- registro ---``).
    Último recurso cuando el modelo emite STORED, saldos ficticios o plantillas de cuentas.
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
    bullets: list[str] = []
    seen_lower: set[str] = set()
    for para in re.split(r"\n\s*\n+", s):
        p = " ".join((para or "").split()).strip()
        if len(p) < 12:
            continue
        low = p.lower()
        if low in seen_lower:
            continue
        seen_lower.add(low)
        bullets.append(p[:480] + ("…" if len(p) > 480 else ""))
        if len(bullets) >= 12:
            break
    if not bullets:
        for ln in s.splitlines():
            x = " ".join(ln.split()).strip()
            if len(x) < 12:
                continue
            if x.startswith("[") and "DIRECTIVE" in x:
                continue
            xl = x.lower()
            if xl in seen_lower:
                continue
            seen_lower.add(xl)
            bullets.append(x[:480])
            if len(bullets) >= 10:
                break
    if not bullets:
        return ""
    body_lines = ["**Resumen del contexto ingresado**", ""]
    for b in bullets:
        body_lines.append(f"- {b}")
    body_lines.extend(
        [
            "",
            "**Siguientes pasos**",
            "- Si quieres más detalle sobre un punto, añádelo con `/context --add`.",
            "- Para ver todo lo guardado: `/context --summary`.",
        ]
    )
    return "\n".join(body_lines)


def _new_context_reply_needs_deterministic_reset(reply: str, incoming: str) -> tuple[bool, str]:
    """
    True si la respuesta del modelo contradice un turno NEW (marcador STORED, plantillas de cuentas,
    lexemas de ledger ausentes en el volcado).
    """
    r = (reply or "").strip()
    inc = (incoming or "").strip()
    if not r:
        return True, "empty_reply"
    r_low = r.lower()
    inc_low = inc.lower()
    if SUMMARIZE_STORED_CONTEXT_MARK in r:
        return True, "stored_mark_in_reply"
    for needle in _NEW_CONTEXT_WRONG_ACCOUNT_TEMPLATES:
        if needle in r_low and needle not in inc_low:
            return True, f"template:{needle[:24]}"
    for lex in _NEW_CONTEXT_LEDGER_LEXEMES:
        if lex in r_low and lex not in inc_low:
            return True, f"ledger_lex:{lex}"
    # Montos COP/USD tipo ledger sin que el usuario pegara símbolo de moneda en el bloque
    if re.search(r"\$[\d.,]+\s*(cop|usd)\b", r_low):
        if "$" not in inc and "cop" not in inc_low and "usd" not in inc_low:
            return True, "currency_amounts_no_evidence"
    return False, ""


def _log_4a0206(*, hypothesis_id: str, location: str, message: str, data: dict[str, Any]) -> None:
    # region agent log
    try:
        payload = {
            "sessionId": "4a0206",
            "runId": "pre-fix",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(__import__("time").time() * 1000),
        }
        with open(_DEBUG_LOG_PATH_4A0206, "a", encoding="utf-8") as _f:
            _f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # endregion


def _new_context_vlm_noise_metrics(incoming: str) -> dict[str, Any]:
    s = (incoming or "").strip()
    has_vlm = "[VLM_CONTEXT" in s
    has_new = SUMMARIZE_NEW_CONTEXT_MARK in s
    visual = ""
    if "Contexto visual adjunto:" in s:
        visual = s.split("Contexto visual adjunto:", 1)[1]
        visual = visual.split("[VLM_CONTEXT", 1)[0]
    token_list = [t for t in re.split(r"\s+", visual) if t]
    token_count = len(token_list)
    unused_count = len(_NOISY_UNUSED_RE.findall(visual))
    deployments_count = visual.lower().count("deployments")
    unique_ratio = (
        (len(set(t.lower() for t in token_list)) / float(token_count))
        if token_count
        else 1.0
    )
    junk_token_count = 0
    for tok in token_list:
        clean = _NON_ALNUM_TOKEN_RE.sub("", tok)
        if len(clean) < 2:
            junk_token_count += 1
    junk_ratio = (junk_token_count / float(token_count)) if token_count else 0.0
    noisy = bool(
        has_new
        and has_vlm
        and (
            unused_count >= 3
            or deployments_count >= 6
            or (token_count >= 120 and unique_ratio < 0.45)
            or (token_count >= 80 and junk_ratio > 0.35)
        )
    )
    return {
        "has_new_directive": has_new,
        "has_vlm_context": has_vlm,
        "token_count": token_count,
        "unused_count": unused_count,
        "deployments_count": deployments_count,
        "unique_ratio": round(unique_ratio, 4),
        "junk_ratio": round(junk_ratio, 4),
        "noisy": noisy,
    }


def _deterministic_noisy_vlm_new_context_summary(incoming: str) -> str:
    s = (incoming or "").strip()
    m_hash = re.search(r"image_hash=([0-9a-f]{16,64})", s, re.IGNORECASE)
    m_conf = re.search(r"confidence=([0-9.]+)", s, re.IGNORECASE)
    h = m_hash.group(1) if m_hash else "N/D"
    c = m_conf.group(1) if m_conf else "N/D"
    return (
        "**Resumen del contexto ingresado**\n\n"
        "- El texto extraído por visión presenta baja legibilidad y alto ruido sintáctico; no es confiable para inferencias temáticas finas.\n"
        f"- Evidencia VLM recibida: `image_hash={h}` y `confidence={c}`.\n"
        "- Se conserva el bloque como contexto bruto en VSS, pero se evita interpretar categorías no explícitas para no alucinar contenido.\n\n"
        "**Siguientes pasos**\n"
        "- Reenvía la imagen con mayor resolución o recorte del titular relevante.\n"
        "- Si el objetivo es precisión, agrega 1-3 líneas de texto manual junto a `/context --add`."
    )


def repair_summarize_new_context_egress(reply: str, *, incoming: str) -> str:
    """
    Corrige egress en ``SUMMARIZE_NEW_CONTEXT``: MLX/Gemma a veces antepone ``SUMMARIZE_STORED_CONTEXT``
    o inventa saldos/IBKR pese a que el volcado es solo notas (spec: dominio único, sin cuentas en ese turno).
    """
    inc = (incoming or "").strip()
    if SUMMARIZE_NEW_CONTEXT_MARK not in inc:
        return reply
    _mx = _new_context_vlm_noise_metrics(inc)
    _log_4a0206(
        hypothesis_id="H3",
        location="user_reply_nl_synthesis.repair_summarize_new_context_egress",
        message="vlm_new_context_noise_metrics",
        data=_mx,
    )
    if bool(_mx.get("noisy")):
        _log_4a0206(
            hypothesis_id="H4",
            location="user_reply_nl_synthesis.repair_summarize_new_context_egress",
            message="replace_noisy_vlm_summary",
            data={"reason": "low_signal_vlm_ocr"},
        )
        return _deterministic_noisy_vlm_new_context_summary(inc)
    r = (reply or "").strip()
    # Quitar una o más líneas iniciales erróneas STORED
    while r:
        first_line, _, rest = r.partition("\n")
        fl = first_line.strip()
        if re.match(
            r"^\[SYSTEM_DIRECTIVE:\s*SUMMARIZE_STORED_CONTEXT\]\s*$",
            fl,
            re.IGNORECASE,
        ):
            r = rest.lstrip()
            continue
        break
    r = r.replace(SUMMARIZE_STORED_CONTEXT_MARK, "").strip()
    need, reason = _new_context_reply_needs_deterministic_reset(r, inc)
    if need:
        det = _deterministic_new_context_summary(inc)
        if det:
            _agent_debug_log(
                hypothesis_id="H1",
                location="user_reply_nl_synthesis.repair_summarize_new_context_egress",
                message="replaced_with_deterministic_new_context",
                data={"reason": reason, "reply_preview": (r or "")[:120]},
            )
            return det
        _agent_debug_log(
            hypothesis_id="H2",
            location="user_reply_nl_synthesis.repair_summarize_new_context_egress",
            message="reset_needed_but_det_empty",
            data={"reason": reason},
        )
    return r if r else (reply or "")


def _fallback_bullets_from_visual_context_dump(inc: str) -> str:
    """
    Si el modelo devuelve solo la marca STORED en un turno NEW/VLM, viñetas mínimas desde
    ``Contexto visual adjunto:`` sin segunda llamada LLM.
    """
    s = (inc or "").strip()
    if "Contexto visual adjunto:" not in s or "[VLM_CONTEXT" not in s:
        return ""
    i = s.find("Contexto visual adjunto:")
    chunk = s[i + len("Contexto visual adjunto:") :].strip()
    j = chunk.find("[VLM_CONTEXT")
    if j >= 0:
        chunk = chunk[:j].strip()
    chunk = chunk[:2800].strip()
    if not chunk:
        return ""
    bullets: list[str] = []
    for raw_ln in chunk.splitlines():
        ln = raw_ln.strip()
        if len(ln) < 4:
            continue
        if ln.startswith(("- ", "* ", "• ")):
            bullets.append(ln[:420])
        else:
            bullets.append(f"- {ln[:400]}")
        if len(bullets) >= 14:
            break
    if not bullets:
        return ""
    body = "**Resumen del contexto ingresado**\n\n" + "\n".join(bullets)
    body += (
        "\n\n**Siguientes pasos**\n"
        "- Si el visión falló a menudo, revisa ``mlx_vlm`` en el venv del gateway y ``GEMINI_API_KEY``.\n"
    )
    return body


def replace_bare_summarize_image_on_vlm_gateway_down(reply: str, *, incoming: str) -> str:
    """
    MLX/Gemma a veces emite solo ``SUMMARIZE_IMAGE`` cuando el usuario trae ``[META: VLM_GATEWAY_DOWN]``
    (ingesta VLM falló: sin píxeles en el prompt del worker).
    """
    r = (reply or "").strip()
    if not _BARE_SUMMARIZE_IMAGE_REPLY.match(r):
        return reply
    inc = (incoming or "").strip()
    if VLM_GATEWAY_DOWN_META not in inc:
        return reply
    return (
        "La ingesta de visión en el gateway no pudo analizar la imagen en este turno (no hay bloque "
        "[VLM_CONTEXT]). Si viste un aviso de Gemini 503 o de MLX en el mismo puerto que el LM de texto, "
        "reintenta más tarde, instala **mlx-vlm** en el venv del gateway, o sirve visión en otro puerto "
        "(`VLM_MLX_BASE_URL`). Mientras tanto, **describe en texto** qué muestra la imagen (ticker, números, "
        "pantalla) y sigo con ese contexto."
    )


def replace_bare_wrong_summarize_stored_echo(reply: str, *, incoming: str) -> str:
    """
    MLX/Gemma a veces emite solo ``[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]`` en turnos
    ``SUMMARIZE_NEW_CONTEXT`` o con volcado VLM (confunde con ``--summary``).
    """
    r = (reply or "").strip()
    if not _BARE_SUMMARIZE_STORED_REPLY.match(r):
        return reply
    inc = (incoming or "").strip()
    if SUMMARIZE_NEW_CONTEXT_MARK in inc or (
        "Contexto visual adjunto:" in inc and "[VLM_CONTEXT" in inc
    ):
        fb = _fallback_bullets_from_visual_context_dump(inc)
        return fb if fb else reply
    return reply


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
        max_evidence_chars=context_summary_synthesis_evidence_char_limit(),
        max_tokens=context_summary_synthesis_max_output_tokens(),
    )
    syn_st = (syn or "").strip()
    if context_summary_synthesis_acceptable(syn_st):
        return syn_st
    if det:
        return det
    return reply_candidate


_TOOL_BLOCK_HEADER = re.compile(r"^###\s+([a-zA-Z0-9_.-]+)\s*$", re.MULTILINE)


def _combined_tool_blocks_contain_json(s: str) -> bool:
    """
    True si hay bloques ``### nombre_tool`` seguidos de cuerpo JSON (p. ej. salida unida en
    ``set_reply`` cuando MLX emite tools embebidas y se ejecutan varias en un turno).
    """
    if "### " not in s:
        return False
    for m in _TOOL_BLOCK_HEADER.finditer(s):
        rest = s[m.end() :]
        nxt = re.search(r"^\s*###\s+", rest, re.MULTILINE)
        chunk = rest if not nxt else rest[: nxt.start()]
        t = chunk.lstrip()
        if t.startswith("[") or t.startswith("{"):
            return True
    return False


_TOOL_BLOCK_SNAKE_NAME = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")


def _combined_tool_blocks_snake_prose(s: str) -> bool:
    """
    True si hay ``### snake_case_tool`` seguido de texto (p. ej. ``get_ibkr_portfolio`` + «Estado:…»).
    Sin esto, ``reply_needs_nl_synthesis`` no dispara la 2.ª pasada y el usuario ve el encabezado crudo.
    """
    if "### " not in s:
        return False
    for m in _TOOL_BLOCK_HEADER.finditer(s):
        name = (m.group(1) or "").strip()
        if not _TOOL_BLOCK_SNAKE_NAME.match(name):
            continue
        rest = s[m.end() :]
        nxt = re.search(r"^\s*###\s+", rest, re.MULTILINE)
        chunk = (rest if not nxt else rest[: nxt.start()]).strip()
        if chunk:
            return True
    return False


def _body_looks_like_reddit_mcp_listing_json(s: str) -> bool:
    """
    Listados MCP (subreddit + posts) a menudo van con prefijo ``finanz N`` y no pasan el
    ``startswith('{')`` de la heurística JSON pura; si además el JSON está truncado,
    ``json.loads`` falla y el usuario ve el volcado crudo en Telegram.
    """
    if '"posts"' not in s or '"subreddit"' not in s:
        return False
    return bool(re.search(r'"subreddit"\s*:', s) and re.search(r'"posts"\s*:', s))


def _body_looks_like_reddit_compact_listing_markdown(s: str) -> bool:
    """
    Tras ``format_reddit_mcp_reply_if_applicable`` el modelo a veces devuelve solo el Markdown
    compacto (cabecera ``## r/… (Top N posts)`` + viñetas con ``[Enlace](…)``). Eso ya no es JSON
    ni bloque ``### tool_*``, así que sin esta rama ``reply_needs_nl_synthesis`` queda en False y
    el usuario ve el payload en lugar de un resumen + siguientes pasos.
    """
    t = (s or "").strip()
    if "[Enlace](" not in t:
        return False
    if not re.search(r"^##\s+r/[\w.+-]+\s+\(Top\s+\d+\s+posts\)", t, re.MULTILINE | re.IGNORECASE):
        return False
    return "Score:" in t or "*Extracto:*" in t


def _reddit_compact_subreddit_from_header(s: str) -> str:
    m = re.search(r"^##\s+r/([\w.+-]+)\s+\(Top\s+\d+\s+posts\)", (s or "").strip(), re.MULTILINE | re.IGNORECASE)
    return (m.group(1) or "reddit").strip() if m else "reddit"


def _deterministic_reddit_compact_listing_summary(s: str) -> str:
    """
    Resumen sin LLM a partir del listado compacto (títulos + scores). Cubre el caso
    ``DUCKCLAW_DISABLE_NL_REPLY_SYNTHESIS=1`` o fallo/echo del modelo en la segunda pasada.
    """
    if not _body_looks_like_reddit_compact_listing_markdown(s):
        return ""
    sub = _reddit_compact_subreddit_from_header(s)
    titles: list[str] = []
    for raw_ln in (s or "").splitlines():
        ln = raw_ln.strip()
        if not ln.startswith("- "):
            continue
        if " (Score:" not in ln:
            continue
        body = ln[2:].strip()
        idx = body.find(" (Score:")
        if idx <= 0:
            continue
        title = body[:idx].strip()
        title = re.sub(r"^\*+", "", title)
        title = re.sub(r"\*+$", "", title).strip()
        if len(title) < 6:
            continue
        if len(title) > 160:
            title = title[:159] + "…"
        titles.append(title)
        if len(titles) >= 6:
            break
    if not titles:
        return ""
    joined = "; ".join(titles[:5])
    if len(titles) > 5:
        joined += "; …"
    return (
        f"En **r/{sub}** los hilos más visibles en el listado hablan de: {joined}.\n\n"
        "**Siguientes pasos**\n"
        "- Abre el **Enlace** de un hilo si quieres el contexto completo en Reddit.\n"
        "- Si buscas un solo post, pega su URL directa y pide «resume solo este»."
    )


def reply_needs_nl_synthesis(text: str) -> bool:
    """True si el texto es JSON puro o bloques ``### tool`` + JSON o prosa de tool (MLX / egress)."""
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
    return _combined_tool_blocks_snake_prose(s)


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
) -> str:
    """Invoca el LLM sin tools; devuelve texto para el usuario o cadena vacía si falla."""
    from langchain_core.messages import HumanMessage, SystemMessage

    ev_limit = max_evidence_chars if max_evidence_chars is not None else _MAX_EVIDENCE_CHARS
    mt = max_tokens if max_tokens is not None else _MAX_SYNTH_TOKENS

    _reddit_listing_rules = ""
    if _body_looks_like_reddit_compact_listing_markdown(raw_evidence or ""):
        _reddit_listing_rules = (
            "\n- La evidencia es un listado compacto de Reddit (cabecera ## r/…): NO repitas todas las viñetas ni los "
            "enlaces uno por uno. Resume en 2–5 frases los temas dominantes y menciona como máximo 1–2 hilos si son "
            "centrales; luego **Siguientes pasos**."
        )
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
    _finanz_extra = (
        "\n- Worker Finanz: si la evidencia incluye varias cuentas locales con `balance` y `currency` (p. ej. JSON de "
        "`read_sql` sobre cuentas), incluye **líneas de subtotal por cada moneda** presente, sumando solo balances de "
        "la evidencia. Si también hay bloque IBKR, conserva totales del broker en su divisa; **no** unifiques COP y USD "
        "en un solo total sin tipo de cambio en la evidencia."
    )
    _sys_text = _base_rules + (_finanz_extra if (worker_id or "").strip().lower() == "finanz" else "")
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
    if not reply_needs_nl_synthesis(reply_candidate):
        return reply_candidate
    wid = str(getattr(spec, "worker_id", "") or "").strip() or "worker"
    synthesized = synthesize_user_visible_reply(
        llm,
        user_ask=(user_ask or "").strip(),
        raw_evidence=reply_candidate,
        worker_id=wid,
    )
    syn_st = (synthesized or "").strip()
    if rc_compact and (not syn_st or _body_looks_like_reddit_compact_listing_markdown(syn_st)):
        det = _deterministic_reddit_compact_listing_summary(reply_candidate)
        if det:
            return det
    return syn_st if syn_st else reply_candidate
