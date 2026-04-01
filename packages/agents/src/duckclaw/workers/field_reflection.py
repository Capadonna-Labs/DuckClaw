"""Field reflection (Finanz): detectar errores de tools, persistir lecciones, rankear Experiencia de Campo."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Optional


def finanz_field_reflection_enabled(spec: Any) -> bool:
    """True solo para worker lógico finanz y si manifest no desactiva field_reflection."""
    lid = (getattr(spec, "logical_worker_id", None) or getattr(spec, "worker_id", None) or "").strip().lower()
    if lid != "finanz":
        return False
    cfg = getattr(spec, "field_reflection_config", None) or {}
    return bool(cfg.get("enabled", True))

# Mensajes que no son éxito operativo (herramienta ausente / sandbox off)
_TOOL_FAILURE_HINTS = (
    "herramienta desconocida",
    "sandbox deshabilitado",
    "read_pool: resultado faltante",
)


def _safe_schema(name: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in (name or "").strip())


def tool_content_indicates_error(content: str, tool_name: str = "") -> bool:
    """True si el contenido de una ToolMessage indica fallo (spec Field Reflection)."""
    s = (content or "").strip()
    if not s:
        return False
    low = s.lower()
    if s.startswith("Error:"):
        return True
    for hint in _TOOL_FAILURE_HINTS:
        if hint in low:
            return True
    try:
        obj = json.loads(s)
        if isinstance(obj, dict):
            if "error" in obj and obj.get("error") is not None:
                return True
            ec = obj.get("exit_code")
            if ec is not None and ec != 0:
                return True
    except (json.JSONDecodeError, TypeError):
        pass
    _ = tool_name
    return False


def last_tool_batch_has_error(messages: list[Any]) -> bool:
    """
    Inspecciona el último AIMessage con tool_calls y las ToolMessage que le siguen.
    True si alguna respuesta de tool es error.
    """
    try:
        from langchain_core.messages import AIMessage, ToolMessage
    except ImportError:
        return False

    idx_ai: Optional[int] = None
    for idx in range(len(messages) - 1, -1, -1):
        m = messages[idx]
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            idx_ai = idx
            break
    if idx_ai is None:
        return False
    tool_calls = messages[idx_ai].tool_calls or []
    n = len(tool_calls)
    if n == 0:
        return False
    tail = messages[idx_ai + 1 : idx_ai + 1 + n]
    if len(tail) < n:
        return False
    for j, tc in enumerate(tool_calls):
        tm = tail[j]
        if not isinstance(tm, ToolMessage):
            return True
        name = (tc.get("name") or getattr(tm, "name", None) or "").strip()
        body = str(getattr(tm, "content", "") or "")
        if tool_content_indicates_error(body, name):
            return True
    return False


def lesson_belief_key(context_trigger: str, lesson_text: str) -> str:
    """Clave estable tipo lesson_<hash> (sin colisión con lake_* / homeostasis)."""
    raw = f"{(context_trigger or '').strip()}|{(lesson_text or '').strip().lower()[:800]}"
    h = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"lesson_{h}"


def tokenize_for_relevance(text: str) -> set[str]:
    return set(w.lower() for w in re.findall(r"\w+", (text or ""), flags=re.UNICODE))


def relevance_score(incoming_tokens: set[str], trigger: str, lesson: str, confidence: float) -> float:
    tt = tokenize_for_relevance(trigger)
    tl = tokenize_for_relevance(lesson)
    overlap_t = len(incoming_tokens & tt)
    overlap_l = len(incoming_tokens & tl)
    conf = float(confidence or 1.0)
    return overlap_t * 2.0 + overlap_l * 0.5 + conf * 0.05


def _sql_string_literal(value: str) -> str:
    """Literal SQL string (compatible con DuckClaw nativo: execute solo acepta un string)."""
    return "'" + (value or "").replace("'", "''") + "'"


def persist_field_lesson(
    db: Any,
    schema: str,
    belief_key: str,
    context_trigger: str,
    lesson_text: str,
    confidence_score: float,
) -> None:
    """
    INSERT field_lesson o sube confidence_score si existe la misma belief_key.
    Prohibido DELETE (regla de oro). No actualiza lesson_text en conflicto.
    """
    s = _safe_schema(schema)
    key_esc = "".join(c if c.isalnum() or c == "_" else "_" for c in belief_key.strip())
    if not key_esc.startswith("lesson_"):
        key_esc = "lesson_" + key_esc[:48]
    conf = max(0.0, float(confidence_score))
    lit_key = _sql_string_literal(key_esc)
    lit_trig = _sql_string_literal(context_trigger or "")
    lit_lesson = _sql_string_literal(lesson_text or "")
    sql = f"""
        INSERT INTO {s}.agent_beliefs (
            belief_key, target_value, observed_value, threshold,
            belief_kind, context_trigger, lesson_text, confidence_score
        )
        VALUES (
            {lit_key}, 0.0, NULL, 0.0, 'field_lesson', {lit_trig}, {lit_lesson}, {conf}
        )
        ON CONFLICT (belief_key) DO UPDATE SET
            confidence_score = GREATEST(
                COALESCE({s}.agent_beliefs.confidence_score, 1.0),
                COALESCE(excluded.confidence_score, 1.0)
            ),
            last_updated = now()
    """
    try:
        db.execute(sql)
    except TypeError:
        try:
            db.execute(
                sql,
                [key_esc, context_trigger or "", lesson_text or "", conf],
            )
        except Exception:
            pass
    except Exception:
        pass


def fetch_field_experience_candidates(db: Any, schema: str, limit_rows: int = 200) -> list[dict[str, Any]]:
    """Lee filas field_lesson recientes para rankear en Python."""
    s = _safe_schema(schema)
    try:
        raw = db.query(
            f"""
            SELECT belief_key, context_trigger, lesson_text, confidence_score, last_updated
            FROM {s}.agent_beliefs
            WHERE belief_kind = 'field_lesson'
              AND lesson_text IS NOT NULL
              AND LENGTH(TRIM(lesson_text)) > 0
            ORDER BY last_updated DESC
            LIMIT {int(limit_rows)}
            """
        )
        rows = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(rows, list):
            return []
        out: list[dict[str, Any]] = []
        for r in rows:
            if not isinstance(r, dict):
                continue
            out.append(
                {
                    "belief_key": r.get("belief_key") or "",
                    "context_trigger": r.get("context_trigger") or "",
                    "lesson_text": r.get("lesson_text") or "",
                    "confidence_score": float(r.get("confidence_score") or 1.0),
                }
            )
        return out
    except Exception:
        return []


def format_field_experience_block(incoming: str, db: Any, schema: str, top_n: int = 5) -> str:
    """Top-N lecciones por relevancia; cadena vacía si no hay filas."""
    rows = fetch_field_experience_candidates(db, schema)
    if not rows:
        return ""
    inc_tok = tokenize_for_relevance(incoming)
    if inc_tok:
        scored = [
            (relevance_score(inc_tok, r["context_trigger"], r["lesson_text"], r["confidence_score"]), r)
            for r in rows
        ]
        scored.sort(key=lambda x: -x[0])
        picked = [p[1] for p in scored[:top_n]]
    else:
        rows.sort(key=lambda r: -r["confidence_score"])
        picked = rows[:top_n]
    lines = [
        "## Experiencia de Campo",
        "Lecciones previas de ejecución (no sustituyen herramientas ni datos en vivo):",
    ]
    for r in picked:
        trig = (r.get("context_trigger") or "").strip() or "(sin trigger)"
        les = (r.get("lesson_text") or "").strip().replace("\n", " ")
        conf = r.get("confidence_score", 1.0)
        lines.append(f"- [{trig}] {les} (conf: {conf})")
    return "\n".join(lines)


def collect_tool_error_digest(messages: list[Any]) -> str:
    """Texto compacto del último batch de tools con error (para prompt del Reflector)."""
    try:
        from langchain_core.messages import AIMessage, ToolMessage
    except ImportError:
        return ""

    idx_ai: Optional[int] = None
    for idx in range(len(messages) - 1, -1, -1):
        m = messages[idx]
        if isinstance(m, AIMessage) and getattr(m, "tool_calls", None):
            idx_ai = idx
            break
    if idx_ai is None:
        return ""
    tool_calls = messages[idx_ai].tool_calls or []
    n = len(tool_calls)
    tail = messages[idx_ai + 1 : idx_ai + 1 + n]
    parts: list[str] = []
    for j, tc in enumerate(tool_calls):
        if j >= len(tail):
            break
        tm = tail[j]
        if not isinstance(tm, ToolMessage):
            continue
        name = (tc.get("name") or "").strip()
        body = str(getattr(tm, "content", "") or "")
        if tool_content_indicates_error(body, name):
            prev = str(body)[:1200]
            parts.append(f"Tool: {name}\nResult (truncado):\n{prev}")
    return "\n---\n".join(parts)


def parse_reflection_json(text: str) -> Optional[dict[str, Any]]:
    """Extrae JSON con context_trigger, lesson_text, confidence_score del LLM."""
    s = (text or "").strip()
    if not s:
        return None
    if "```" in s:
        for chunk in s.split("```"):
            chunk = chunk.strip()
            if chunk.lower().startswith("json"):
                chunk = chunk[4:].lstrip()
            if chunk.startswith("{"):
                s = chunk
                break
    m = re.search(r"\{[\s\S]*\}", s)
    if m:
        s = m.group(0)
    try:
        obj = json.loads(s)
        if not isinstance(obj, dict):
            return None
        ct = str(obj.get("context_trigger") or "").strip()
        lt = str(obj.get("lesson_text") or "").strip()
        if not ct or not lt:
            return None
        conf = obj.get("confidence_score", 1.0)
        try:
            conf_f = float(conf)
        except (TypeError, ValueError):
            conf_f = 1.0
        return {"context_trigger": ct[:500], "lesson_text": lt[:4000], "confidence_score": max(0.0, conf_f)}
    except (json.JSONDecodeError, TypeError):
        return None
