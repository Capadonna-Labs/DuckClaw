"""Agent-node helpers: cancel checks, identity, LLM failure messages, ComfyUI parse."""

from __future__ import annotations

import os
import re
from typing import Any

from duckclaw.guardrails.loader import load_guardrail

def _raise_if_chat_cancelled_from_state(state: dict) -> None:
    from duckclaw.graphs.chat_cancel import raise_if_chat_cancelled

    cid = str(state.get("chat_id") or state.get("session_id") or "").strip()
    if cid:
        raise_if_chat_cancelled(cid)


# Tarea explícita del manager (plan): nunca tratar como "sin tarea"
def _worker_log_label(worker_id: str) -> str:
    """Etiqueta corta solo para texto de log (no sustituye el id real del estado)."""
    w = (worker_id or "").strip()
    return w or "worker"


def _duckclaw_env_truthy(name: str) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _spec_logical_worker_id(spec: Any) -> str:
    return (getattr(spec, "logical_worker_id", None) or getattr(spec, "worker_id", "") or "").strip()


def _last_human_message_index(messages: list[Any]) -> int:
    from langchain_core.messages import HumanMessage

    for idx in range(len(messages or []) - 1, -1, -1):
        if isinstance(messages[idx], HumanMessage):
            return idx
    return -1


_COMFYUI_EDIT_PATH_RE = re.compile(
    r"\[COMFYUI_EDIT\s+source_image_path=([^\]]+)\]",
    re.IGNORECASE,
)


def _parse_comfyui_edit_inbound(incoming: str) -> dict[str, str] | None:
    """Compat wrapper for admin/Telegram inbound visual-edit payloads."""
    s = (incoming or "").strip()
    if "[COMFYUI_EDIT" not in s:
        return None
    m = _COMFYUI_EDIT_PATH_RE.search(s)
    if not m:
        return None
    source_path = m.group(1).strip()
    if not source_path:
        return None
    cap_m = re.search(r"Instrucciones:\s*«([^»]+)»", s)
    edit_prompt = cap_m.group(1).strip() if cap_m else ""
    if not edit_prompt:
        for line in s.splitlines():
            low = line.lower()
            if low.startswith("usuario dice:"):
                edit_prompt = line.split(":", 1)[-1].strip()
                break
    if not edit_prompt:
        edit_prompt = s[:500]
    return {"source_image_path": source_path, "edit_prompt": edit_prompt[:500]}


_TASK_AWARENESS_PROMPT = load_guardrail("prompts", "task_awareness_default")


def _identity_fields(state: dict) -> dict:
    return {
        "chat_id": state.get("chat_id") or state.get("session_id"),
        "tenant_id": state.get("tenant_id") or "default",
        "user_id": state.get("user_id") or "",
        "username": (state.get("username") or "").strip(),
        "vault_db_path": state.get("vault_db_path") or "",
    }

def _latest_human_index_with_vlm_visual_markers(messages: list[Any]) -> Optional[int]:
    """Human más reciente con payload VLM (mismo marcador que el gateway al Multimodal)."""
    from langchain_core.messages import HumanMessage

    from duckclaw.integrations.llm_providers import lc_message_content_to_text

    for i in range(len(messages or []) - 1, -1, -1):
        m = messages[i]
        if not isinstance(m, HumanMessage):
            continue
        txt = lc_message_content_to_text(m) or ""
        if "[VLM_CONTEXT" in txt or "Contexto visual adjunto:" in txt:
            return i
    return None


def _visual_asset_calls_since_last_human(messages: list[Any]) -> int:
    """Cuántas veces se invocó generate_visual_asset desde el último HumanMessage."""
    from langchain_core.messages import HumanMessage, ToolMessage

    count = 0
    for msg in reversed(messages or []):
        if isinstance(msg, HumanMessage):
            break
        if isinstance(msg, ToolMessage) and (getattr(msg, "name", "") or "") == "generate_visual_asset":
            count += 1
    return count


def _agent_node_llm_failure_user_message(exc: BaseException, *, provider: str) -> str:
    """Mensaje Telegram cuando falla invoke del LLM en agent_node (sin culpar a MLX si el proveedor es Groq)."""
    pl = (provider or "").strip().lower()
    raw = str(exc)
    low = raw.lower()
    mlx_hint = load_guardrail("errors", "llm_failure_mlx")
    groq_tokens_hint = load_guardrail("errors", "llm_failure_groq_tpm")
    is_groq_size_or_tpm = (
        "413" in raw
        or "rate_limit_exceeded" in low
        or "tokens per minute" in low
        or "request too large" in low
        or "too large for model" in low
    )
    if pl == "groq" and is_groq_size_or_tpm:
        return groq_tokens_hint
    detail = raw[:380] + ("…" if len(raw) > 380 else "")
    if pl == "groq":
        return load_guardrail("errors", "llm_failure_groq_generic").format(detail=detail)
    if pl == "deepseek":
        return load_guardrail("errors", "llm_failure_deepseek").format(detail=detail)
    if pl == "openai":
        return load_guardrail("errors", "llm_failure_openai").format(detail=detail)
    if pl == "openrouter" and ("402" in raw or "payment required" in low or "more credits" in low):
        return (
            "OpenRouter rechazó la petición (créditos insuficientes o `max_tokens` demasiado alto). "
            "Opciones: añade créditos en openrouter.ai/settings/credits, usa DeepSeek/Groq en el selector, "
            "o baja `DUCKCLAW_OPENROUTER_MAX_OUTPUT_TOKENS` (p. ej. 2048). "
            f"Detalle: {detail}"
        )
    if pl in ("mlx", "iotcorelabs"):
        return mlx_hint
    return load_guardrail("errors", "llm_failure_generic").format(detail=detail)
