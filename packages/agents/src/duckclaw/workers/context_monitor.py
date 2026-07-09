"""Worker context compression helpers owned outside the factory."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Mapping, Optional

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore[misc, assignment]

from duckclaw.workers.provider_input_budget import estimate_tokens_from_messages, split_for_pruning
from duckclaw.workers.tool_output_truncation import truncate_tool_messages_for_llm

_log = logging.getLogger(__name__)


def compose_context_summary_prompt(base: str, conversation_summary: str) -> str:
    base_prompt = (base or "").strip()
    summary = (conversation_summary or "").strip()
    if not summary:
        return base_prompt
    if not base_prompt:
        return "Resumen compactado del hilo:\n" + summary
    return base_prompt + "\n\nResumen compactado del hilo:\n" + summary


def serialize_messages_for_summary(messages: list[Any]) -> str:
    lines: list[str] = []
    for message in messages or []:
        content = getattr(message, "content", None) or ""
        if not isinstance(content, str):
            content = str(content)
        content = content[:6000]
        name = type(message).__name__
        if name == "HumanMessage":
            lines.append("user: " + content)
        elif name == "AIMessage":
            lines.append("assistant: " + content)
        elif name == "ToolMessage":
            tool_name = getattr(message, "name", "") or "tool"
            lines.append(f"tool_{tool_name}: " + content[:4000])
    return "\n".join(lines)


def llm_fold_conversation_summary(
    llm: Any,
    head_msgs: list[Any],
    prior: str,
    *,
    fold_focus: str = "default",
    alignment_preface: str = "",
) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    blob = serialize_messages_for_summary(head_msgs)
    if fold_focus == "goals_alignment":
        system_prompt = (
            "Eres un asistente de compresión de contexto para un worker DuckClaw. "
            "Produce un resumen operativo breve en español centrado en alineación con "
            "las metas /goals: progreso, desvíos, decisiones del agente, evidencia "
            "pendiente, herramientas usadas y próximos pasos para cumplir objetivos. "
            "Sin saludos. Máximo ~800 palabras."
        )
    else:
        system_prompt = (
            "Eres un asistente de compresión de contexto para un worker DuckClaw. "
            "Produce un resumen operativo breve en español: intención del usuario, decisiones, "
            "hallazgos, errores, datos pendientes y herramientas relevantes. "
            "Sin saludos. Máximo ~800 palabras."
        )
    preface_block = ""
    if (alignment_preface or "").strip():
        preface_block = "Informe de alineación /goals:\n" + alignment_preface.strip() + "\n\n---\n"
    human_prompt = (
        preface_block
        + "Resumen previo del hilo (puede estar vacío):\n"
        + (prior or "")
        + "\n\n---\nTranscript a compactar:\n"
        + blob
    )
    try:
        reply = llm.invoke([SystemMessage(content=system_prompt), HumanMessage(content=human_prompt)])
        return (str(getattr(reply, "content", None) or "") or "").strip()[:12000]
    except Exception as exc:
        _log.warning("context pruning summary LLM failed: %s", exc)
        return ((prior or "").strip() + "\n[Error al generar resumen; contexto truncado.]").strip()


def build_summary_llm(
    primary_llm: Any,
    *,
    provider: str,
    model: str,
    base_url: str,
    build_llm: Callable[[str, str, str], Any] | None = None,
    env: Mapping[str, str] | None = None,
) -> Any:
    if primary_llm is None:
        return None
    env_map = env if env is not None else os.environ
    summary_provider = (env_map.get("DUCKCLAW_SUMMARY_LLM_PROVIDER") or "").strip() or provider
    summary_model = (env_map.get("DUCKCLAW_SUMMARY_LLM_MODEL") or "").strip() or model
    summary_base_url = (env_map.get("DUCKCLAW_SUMMARY_LLM_BASE_URL") or "").strip() or base_url
    summary_llm: Any = None
    try:
        if (summary_provider or "").lower() != "none_llm":
            builder = build_llm
            if builder is None:
                from duckclaw.integrations.llm_providers import build_llm as builder

            summary_llm = builder(summary_provider, summary_model, summary_base_url)
    except Exception as exc:
        _log.warning("summary LLM build failed, using primary: %s", exc)
    return summary_llm or primary_llm


def _summary_value(state: dict, summary_state_key: str) -> str:
    summary = state.get(summary_state_key)
    if summary is None and summary_state_key != "context_summary":
        summary = state.get("context_summary")
    if summary is None and summary_state_key != "analytical_summary":
        summary = state.get("analytical_summary")
    return (str(summary or "")).strip()


def _with_identity_fields(
    state: dict,
    out: dict,
    identity_fields: Callable[[dict], dict] | None,
) -> dict:
    if identity_fields is not None:
        out.update(identity_fields(state))
    return out


def apply_context_monitor_state(
    state: dict,
    *,
    pruning_config: dict[str, Any],
    prompt_base: str,
    llm_summary: Any = None,
    identity_fields: Callable[[dict], dict] | None = None,
    summary_state_key: str = "analytical_summary",
    force_prune: bool = False,
    fold_focus: str = "default",
    alignment_preface: str = "",
) -> dict:
    if not pruning_config.get("enabled"):
        return state

    from langchain_core.messages import SystemMessage

    messages = list(state.get("messages") or [])
    messages = truncate_tool_messages_for_llm(
        messages,
        int(pruning_config.get("tool_content_max_chars", 8000)),
    )
    estimated_tokens = estimate_tokens_from_messages(messages)
    needs_pruning = bool(force_prune) or (
        len(messages) > int(pruning_config.get("max_messages", 10))
        or estimated_tokens > int(pruning_config.get("max_estimated_tokens", 4000))
    )
    if not needs_pruning:
        return _with_identity_fields(state, {**state, "messages": messages}, identity_fields)
    if not messages or not isinstance(messages[0], SystemMessage):
        return _with_identity_fields(state, {**state, "messages": messages}, identity_fields)

    rest = messages[1:]
    keep_last = int(pruning_config.get("keep_last_messages", 3))
    if force_prune and len(rest) >= 2:
        keep_last = min(keep_last, len(rest) - 1)
        keep_last = max(1, keep_last)
    head, tail = split_for_pruning(rest, keep_last)
    prior = _summary_value(state, summary_state_key)
    if not head:
        trimmed = list(rest)
        system_message = messages[0]
        while (
            len(trimmed) > 1
            and estimate_tokens_from_messages([system_message] + trimmed)
            > int(pruning_config.get("max_estimated_tokens", 4000))
        ):
            trimmed = trimmed[1:]
        system_content = compose_context_summary_prompt(prompt_base, prior)
        out = {
            **state,
            "messages": [SystemMessage(content=system_content)] + trimmed,
            summary_state_key: prior,
        }
        return _with_identity_fields(state, out, identity_fields)

    new_summary = prior
    if llm_summary is not None:
        new_summary = llm_fold_conversation_summary(
            llm_summary,
            head,
            prior,
            fold_focus=fold_focus,
            alignment_preface=alignment_preface,
        )
    else:
        new_summary = ((prior + "\n") if prior else "") + "[Contexto anterior truncado.]"

    system_content = compose_context_summary_prompt(prompt_base, new_summary)
    out = {
        **state,
        "messages": [SystemMessage(content=system_content)] + tail,
        summary_state_key: new_summary,
    }
    return _with_identity_fields(state, out, identity_fields)


def build_context_monitor_node(
    *,
    pruning_config: dict[str, Any],
    prompt_base: str,
    llm_summary: Any = None,
    identity_fields: Callable[[dict], dict] | None = None,
    summary_state_key: str = "analytical_summary",
) -> Callable[[dict, Optional[RunnableConfig]], dict]:
    def context_monitor_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        return apply_context_monitor_state(
            state,
            pruning_config=pruning_config,
            prompt_base=prompt_base,
            llm_summary=llm_summary,
            identity_fields=identity_fields,
            summary_state_key=summary_state_key,
        )

    return context_monitor_node


__all__ = [
    "apply_context_monitor_state",
    "build_context_monitor_node",
    "build_summary_llm",
    "compose_context_summary_prompt",
    "llm_fold_conversation_summary",
    "serialize_messages_for_summary",
]
