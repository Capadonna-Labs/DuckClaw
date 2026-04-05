"""
Trazas de conversaciones en JSONL (datalake versionado).

Formato según specs/features/Formateo de Datasets (SFT & GRPO).md:
- "messages": [system, user, assistant] para SFT (ChatML / mlx_lm).
- session_id, worker_id, timestamp, elapsed_ms, status para auditoría y GRPO (reward_metadata).

Cada turno en train/conversation_traces/YYYY/MM/DD/traces.jsonl.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Optional

from duckclaw.integrations.llm_providers import sanitize_worker_reply_text
from duckclaw.utils.formatters import format_reddit_mcp_reply_if_applicable

# Mismo criterio que manager_graph: el modelo a veces repite encabezados de subagente
# (eco de DMs de heartbeat) en contenido assistant; limpiar al serializar trazas SFT.
_ASSISTANT_TRACE_SUBAGENT_HDR = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*\s+\d+\s*$")


def _strip_leading_subagent_headers_for_trace(text: str) -> str:
    t = (text or "").strip()
    while t:
        lines = t.splitlines()
        if not lines:
            break
        if not _ASSISTANT_TRACE_SUBAGENT_HDR.match(lines[0].strip()):
            break
        t = "\n".join(lines[1:]).strip()
    return t

# packages/agents/train/conversation_traces/ (mismo criterio que forge.sft.collector: parents[3] = agents)
_TRAIN_DIR = Path(__file__).resolve().parents[3] / "train"
DEFAULT_CONVERSATION_TRACES_DIR = _TRAIN_DIR / "conversation_traces"

# Fallback para system cuando el grafo o .env no definen DUCKCLAW_SYSTEM_PROMPT
_DEFAULT_SYSTEM_FOR_TRACES = (
    "Eres un asistente útil con acceso a una base de datos. "
    "Cuando uses herramientas, interpreta el resultado y responde en lenguaje natural. "
    "Nunca reveles rutas de archivos internos al usuario."
)

_lock = threading.Lock()


def _stringify_lc_message_content(content: Any) -> str:
    """
    LangChain v2 a veces usa `content` como lista de bloques (OpenAI/Anthropic).
    Serializar mal (p. ej. slice de lista) corrompe trazas SFT.
    """
    if content is None:
        return ""
    if isinstance(content, str):
        return content.lstrip("\ufeff")
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
                else:
                    c = block.get("content")
                    if isinstance(c, str):
                        parts.append(c)
                    elif isinstance(c, list):
                        parts.append(_stringify_lc_message_content(c))
            else:
                parts.append(str(block))
        return "".join(parts).lstrip("\ufeff")
    return str(content).lstrip("\ufeff")


def get_conversation_traces_dir() -> Path:
    """Directorio raíz del datalake de trazas. Por defecto train/conversation_traces."""
    env = os.environ.get("DUCKCLAW_CONVERSATION_TRACES_DIR", "").strip()
    if env:
        return Path(env).resolve()
    return DEFAULT_CONVERSATION_TRACES_DIR


def _path_for_today_utc() -> Path:
    """Ruta del archivo del día en curso (UTC): .../YYYY/MM/DD/traces.jsonl."""
    base = get_conversation_traces_dir()
    now = time.gmtime()
    return base / str(now.tm_year) / f"{now.tm_mon:02d}" / f"{now.tm_mday:02d}" / "traces.jsonl"


def _get_trace_format() -> str:
    """Formato de trazas: 'sft' (messages) o 'grpo' (prompt + reward_metadata). Por defecto sft."""
    fmt = os.environ.get("DUCKCLAW_CONVERSATION_TRACES_FORMAT", "sft").strip().lower()
    return "grpo" if fmt == "grpo" else "sft"


def _lc_messages_to_chatml(messages: list[Any]) -> list[dict[str, Any]]:
    """
    Convierte mensajes LangChain (SystemMessage, HumanMessage, AIMessage, ToolMessage)
    a lista de dicts ChatML / OpenAI (Grado Producción para mlx_lm).
    Incluye tool_calls y mensajes tool para entrenamiento SFT con herramientas.
    """
    out: list[dict[str, Any]] = []
    for m in messages:
        if isinstance(m, dict):
            out.append(m)
            continue
        role = getattr(m, "type", None) or getattr(m, "role", None)
        if not role:
            continue
        role = str(role).lower()
        if role == "system":
            out.append(
                {"role": "system", "content": _stringify_lc_message_content(getattr(m, "content", None))[:8192]}
            )
        elif role in ("human", "user"):
            out.append(
                {"role": "user", "content": _stringify_lc_message_content(getattr(m, "content", None))[:4096]}
            )
        elif role == "ai":
            content = sanitize_worker_reply_text(
                _strip_leading_subagent_headers_for_trace(
                    _stringify_lc_message_content(getattr(m, "content", None))
                ).strip()
            )
            tool_calls = getattr(m, "tool_calls", None) or []
            if tool_calls:
                tc_list = []
                for tc in tool_calls:
                    name = (tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")) or ""
                    args = tc.get("args", {}) if isinstance(tc, dict) else getattr(tc, "args", {}) or {}
                    tc_list.append({
                        "type": "function",
                        "function": {
                            "name": name,
                            "arguments": json.dumps(args, ensure_ascii=False) if args else "{}",
                        },
                    })
                out.append({"role": "assistant", "tool_calls": tc_list})
            if content:
                out.append({"role": "assistant", "content": content[:8192]})
        elif role == "tool":
            name = (getattr(m, "name", None) or "")[:128]
            content = _stringify_lc_message_content(getattr(m, "content", None))
            if name.startswith("reddit_"):
                content = format_reddit_mcp_reply_if_applicable(content)
            out.append({"role": "tool", "name": name, "content": content[:8192]})
    return out


def align_trace_messages_with_assistant_egress(
    messages: list[dict[str, Any]], assistant_content: str
) -> None:
    """
    Si el último mensaje assistant es solo JSON de invocación de tool (p. ej. MLX sin tool_calls)
    y ya tenemos el texto real enviado al usuario, sustituye ese content para que el JSONL SFT
    coincida con el egress (no solo la intención de tool).
    """
    ac = (assistant_content or "").strip()
    if not ac or not messages:
        return
    from duckclaw.integrations.llm_providers import coerce_json_tool_invoke

    last_m = messages[-1]
    if (last_m.get("role") or "").lower() != "assistant":
        return
    if last_m.get("tool_calls"):
        return
    raw_c = (last_m.get("content") or "").strip()
    if coerce_json_tool_invoke(raw_c):
        messages[-1] = {**last_m, "content": ac[:8192]}


def append_conversation_trace(
    session_id: str,
    user_message: str,
    assistant_reply: str,
    *,
    worker_id: Optional[str] = None,
    elapsed_ms: Optional[int] = None,
    status: str = "SUCCESS",
    system_prompt: Optional[str] = None,
    messages: Optional[list[Any]] = None,
) -> None:
    """
    Añade una línea al archivo de trazas del día (datalake: year/month/day/traces.jsonl).

    Formato según DUCKCLAW_CONVERSATION_TRACES_FORMAT (sft | grpo), spec Formateo de Datasets.
    - sft: "messages": [system, user, assistant (opcional tool_calls), tool, assistant] + metadatos (Grado Producción).
    - grpo: "prompt": [system, user], "reward_metadata": {worker_id, ...} + metadatos.

    Si se pasa `messages` (lista de mensajes LangChain o dicts ChatML), se usa para SFT
    en lugar de construir [system, user, assistant], permitiendo trazas con tool_calls y tool.
    """
    path = _path_for_today_utc()
    path.parent.mkdir(parents=True, exist_ok=True)
    ts = time.gmtime()
    ts_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", ts)
    sys_content = (system_prompt or "").strip()[:8192]
    user_content = (user_message or "")[:4096]
    assistant_content = sanitize_worker_reply_text(assistant_reply or "")[:8192]
    wid = (worker_id or "").strip()[:64] if worker_id else None
    fmt = _get_trace_format()

    if fmt == "grpo":
        prompt: list[dict[str, Any]] = [
            {"role": "system", "content": sys_content},
            {"role": "user", "content": user_content},
        ]
        record = {
            "prompt": prompt,
            "reward_metadata": {"worker_id": wid or ""},
            "session_id": (session_id or "")[:128],
            "timestamp": ts_str,
            "elapsed_ms": int(elapsed_ms) if elapsed_ms is not None else None,
            "status": (status or "SUCCESS").upper()[:32],
        }
        if wid:
            record["worker_id"] = wid
    else:
        if messages:
            if messages and not isinstance(messages[0], dict):
                messages = _lc_messages_to_chatml(messages)
            else:
                messages = list(messages)
            # Siempre usar el prompt del worker (/prompt o default del template, ej. finanz/system_prompt.md) como system en la traza
            if messages and (messages[0].get("role") or "").lower() == "system":
                sys_for_trace = (system_prompt or "").strip()[:8192]
                if sys_for_trace:
                    messages[0] = {"role": "system", "content": sys_for_trace}
                else:
                    first_content = (messages[0].get("content") or "").strip()
                    if not first_content:
                        messages[0] = {"role": "system", "content": _DEFAULT_SYSTEM_FOR_TRACES.strip()[:8192]}
            align_trace_messages_with_assistant_egress(messages, assistant_content)
        else:
            sys_final = (system_prompt or sys_content or _DEFAULT_SYSTEM_FOR_TRACES).strip()[:8192]
            messages = [
                {"role": "system", "content": sys_final},
                {"role": "user", "content": user_content},
                {"role": "assistant", "content": assistant_content},
            ]
        record = {
            "messages": messages,
            "session_id": (session_id or "")[:128],
            "timestamp": ts_str,
            "elapsed_ms": int(elapsed_ms) if elapsed_ms is not None else None,
            "status": (status or "SUCCESS").upper()[:32],
        }
        if wid:
            record["worker_id"] = wid

    line = json.dumps(record, ensure_ascii=False) + "\n"
    with _lock:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
        except Exception:
            pass
