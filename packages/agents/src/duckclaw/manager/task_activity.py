"""Task activity and audit helpers for the manager graph."""

from __future__ import annotations

import re
from typing import Any, Callable


def _tool_name_from_embedded_json_content(text: str) -> str | None:
    """Si el modelo emitió tool como JSON en el texto, extrae el nombre."""
    from duckclaw.integrations.llm_providers import coerce_json_tool_invoke

    raw = (text or "").strip()
    got = coerce_json_tool_invoke(raw)
    if got:
        return got[0]
    i = raw.find("{")
    if i > 0:
        got = coerce_json_tool_invoke(raw[i:])
        if got:
            return got[0]
    return None


def _messages_turn_for_tool_audit(messages: list[Any]) -> list[Any]:
    """
    Mensajes del turno actual respecto al último HumanMessage.

    Evita mezclar tool_calls de turnos viejos del historial y alinea con prepare_node.
    """
    try:
        from langchain_core.messages import HumanMessage
    except ImportError:
        HumanMessage = ()  # type: ignore[assignment, misc]
    last_user_index = -1
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, dict):
            role = str(message.get("role") or message.get("type") or "").lower()
            if role in ("human", "user"):
                last_user_index = index
                break
        elif HumanMessage and isinstance(message, HumanMessage):
            last_user_index = index
            break
    if last_user_index < 0:
        return messages
    return messages[last_user_index + 1 :]


def _is_ai_like_message(message: Any) -> bool:
    """True si el mensaje es un turno assistant (LangChain o dict ChatML)."""
    if message is None:
        return False
    if isinstance(message, dict):
        role = str(message.get("role") or message.get("type") or "").lower()
        return role in ("ai", "assistant", "model")
    message_type = getattr(message, "type", None)
    if isinstance(message_type, str) and message_type.lower() in ("ai", "assistant"):
        return True
    try:
        from langchain_core.messages import AIMessage

        return isinstance(message, AIMessage)
    except ImportError:
        return False


def _message_body_text_for_embedded_tool(message: Any) -> str:
    """Texto de ``content`` para parsear JSON de tool embebido."""
    if isinstance(message, dict):
        from duckclaw.graphs.conversation_traces import _stringify_lc_message_content

        return _stringify_lc_message_content(message.get("content"))
    from duckclaw.integrations.llm_providers import lc_message_content_to_text

    return lc_message_content_to_text(message)


def _worker_tool_names_from_messages(messages: list[Any] | None) -> list[str]:
    """
    Nombres de herramientas usadas en el turno del worker.

    Soporta AIMessage.tool_calls, ToolMessage.name y tool JSON embebido en content.
    """
    if not messages:
        return []
    turn = _messages_turn_for_tool_audit(messages)
    if not turn:
        return []
    try:
        from langchain_core.messages import ToolMessage
    except ImportError:
        ToolMessage = ()  # type: ignore[assignment, misc]

    names: list[str] = []
    for message in turn:
        if isinstance(message, dict):
            for tool_call in message.get("tool_calls") or []:
                if isinstance(tool_call, dict):
                    function = (
                        (tool_call.get("function") or {})
                        if isinstance(tool_call.get("function"), dict)
                        else {}
                    )
                    name = function.get("name") or tool_call.get("name")
                else:
                    name = getattr(tool_call, "name", None)
                if name:
                    names.append(str(name))
            role = str(message.get("role") or message.get("type") or "").lower()
            if role == "tool":
                tool_name = message.get("name")
                if tool_name:
                    names.append(str(tool_name))
            continue
        for tool_call in getattr(message, "tool_calls", None) or []:
            name = tool_call.get("name") if isinstance(tool_call, dict) else getattr(tool_call, "name", None)
            if name:
                names.append(str(name))
        additional_kwargs = getattr(message, "additional_kwargs", None) or {}
        if isinstance(additional_kwargs, dict):
            for tool_call in additional_kwargs.get("tool_calls") or []:
                if isinstance(tool_call, dict):
                    function = tool_call.get("function") if isinstance(tool_call.get("function"), dict) else {}
                    name = function.get("name") if isinstance(function, dict) else tool_call.get("name")
                else:
                    name = getattr(tool_call, "name", None)
                if name:
                    names.append(str(name))
        if ToolMessage and isinstance(message, ToolMessage):
            tool_name = getattr(message, "name", None)
            if tool_name:
                names.append(str(tool_name))
    names = list(dict.fromkeys(names))
    if not names and turn:
        for message in reversed(turn):
            if isinstance(message, dict):
                role = str(message.get("role") or message.get("type") or "").lower()
                if role == "tool" and message.get("name"):
                    names.append(str(message["name"]))
                    break
                if _is_ai_like_message(message):
                    embedded = _tool_name_from_embedded_json_content(
                        _message_body_text_for_embedded_tool(message).strip()
                    )
                    if embedded:
                        names.append(embedded)
                        break
                continue
            if ToolMessage and isinstance(message, ToolMessage):
                tool_name = getattr(message, "name", None)
                if tool_name:
                    names.append(str(tool_name))
                    break
                continue
            if _is_ai_like_message(message):
                embedded = _tool_name_from_embedded_json_content(
                    _message_body_text_for_embedded_tool(message).strip()
                )
                if embedded:
                    names.append(embedded)
                    break
    names = list(dict.fromkeys(names))
    if not names and turn:
        for message in turn:
            if not _is_ai_like_message(message):
                continue
            blob = _message_body_text_for_embedded_tool(message)
            if re.search(r'["\']name["\']\s*:\s*["\']read_sql["\']', blob) and re.search(
                r'["\']query["\']\s*:', blob, re.IGNORECASE
            ):
                names.append("read_sql")
                break
    return list(dict.fromkeys(names))


def _task_summary_for_activity(incoming: str, planned_task: str) -> str:
    """Resumen corto de la tarea para /tasks, no el planned_task completo."""
    task_text = (incoming or "").strip().lower()
    planned_text = (planned_task or "").strip().lower()
    if re.search(
        r"\b(nombre\s+de\s+la\s+db|nombre\s+db|cual\s+es\s+el\s+nombre|nombre\s+de\s+la\s+base)\b",
        task_text,
    ) or ("nombre" in task_text and ("db" in task_text or "base" in task_text or "datos" in task_text)) or (
        "get_db_path" in planned_text and "nombre" in planned_text
    ):
        return "Buscando el nombre de la db disponible."
    if (
        re.search(
            r"\b(tablas?|tables?|esquema|schema|estructura|listar\s+tablas|disponibles)\b",
            task_text,
        )
        or "tablas" in task_text
        or "qué tablas" in task_text
        or "que tablas" in task_text
        or "show tables" in planned_text
    ):
        return "Listando tablas de la base de datos."
    if incoming and len(incoming) > 48:
        return (incoming[:48] + "…").strip()
    return incoming or "Procesando solicitud."


def _activity_task_for_plan(plan_title: str | None, task_summary: str) -> str:
    """Texto visible en /tasks: título del plan si existe, resumen si no."""
    clean_plan_title = (plan_title or "").strip()
    if clean_plan_title:
        return clean_plan_title
    return (task_summary or "").strip() or "Procesando solicitud."


def _append_task_audit_safely(
    append_task_audit: Callable[..., Any],
    *,
    db: Any,
    chat_id: str,
    worker_id: str,
    incoming: str,
    status: str,
    elapsed_ms: int,
    plan_title: str | None = None,
) -> bool:
    """Ejecuta append_task_audit sin romper shortcuts del manager si la auditoría falla."""
    try:
        append_task_audit(
            db,
            chat_id,
            worker_id,
            incoming,
            status,
            elapsed_ms,
            plan_title=plan_title,
        )
    except Exception:
        return False
    return True


__all__ = [
    "_activity_task_for_plan",
    "_append_task_audit_safely",
    "_is_ai_like_message",
    "_message_body_text_for_embedded_tool",
    "_messages_turn_for_tool_audit",
    "_task_summary_for_activity",
    "_tool_name_from_embedded_json_content",
    "_worker_tool_names_from_messages",
]
