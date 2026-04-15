from __future__ import annotations

from typing import Annotated, List, Optional, TypedDict

from langchain_core.messages import BaseMessage
from langgraph.graph.message import add_messages


class ManagerAgentState(TypedDict, total=False):
    """
    Estado tipado para el grafo Manager.

    Claves mínimas:
    - messages: historial de mensajes del grafo (opcional, para compatibilidad con LangGraph).
    - chat_id: identificador del chat / sesión (tenant_id en task_audit_log).
    - tenant_id: identificador lógico del tenant (para whitelist y aislamiento de workers).
    - assigned_worker_id: worker al que se delegó la tarea (finanz, support, etc.).
    - incoming: mensaje original del usuario.
    - input: mismo texto que incoming cuando aplica (LangSmith / vista previa columna Input).
    - history: historial condensado de conversación (lista de mensajes o turnos).
    - planned_task: instrucción detallada que se envía al worker.
    - plan_title: título semántico del plan (máx. ~5 palabras).
    - tasks: lista de subtareas / todos inferidos por el planner.
    - task_summary: resumen corto para /tasks y activity.
    - available_templates: workers disponibles para delegación en este chat.
    - reply: respuesta final al usuario.
    - _audit_done: bandera interna para evitar doble escritura en task_audit_log.
    """

    messages: Annotated[List[BaseMessage], add_messages]
    chat_id: str
    tenant_id: str
    user_id: str
    username: str
    vault_db_path: str
    shared_db_path: str
    assigned_worker_id: Optional[str]

    incoming: str
    input: Optional[str]
    history: list

    planned_task: str
    plan_title: Optional[str]
    tasks: Optional[List[str]]
    task_summary: Optional[str]
    mercenary_spec: Optional[dict]

    available_templates: List[str]
    reply: str
    handoff_context: Optional[dict]
    active_mission: Optional[dict]
    mission_context_system_message: Optional[str]
    last_worker_raw_reply: Optional[str]
    suppress_subagent_egress: Optional[bool]
    internal_reply: Optional[str]
    _audit_done: bool
    sandbox_photo_base64: Optional[str]
    # Token Bot API del webhook que originó el turno (multiplex); heartbeats en hilos no heredan ContextVar.
    outbound_telegram_bot_token: Optional[str]

    # Worker de la ruta HTTP (p. ej. /api/v1/agent/Quant-Trader/chat). Usado para anclar SYSTEM_EVENT de /goals --delta.
    entry_worker_id: Optional[str]

    # Resiliencia Manager: replan tras fallos recuperables (ver agent_resilience + manager_graph).
    plan_attempt_index: Optional[int]
    plan_max_attempts: Optional[int]
    plan_failure_reasons: Optional[list]
    replan_requested: Optional[bool]

