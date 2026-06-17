"""
Fachada de chat agente: orquesta prepare → grafo → finalize.

Owners:
- ``chat_session`` — session_id y cancelación
- ``chat_delivery_context`` / ``chat_vault_resolution`` — contexto de entrega y bóveda
- ``chat_invoke_prepare`` — auth, historial, validaciones
- ``chat_graph_runner`` — grafo LangGraph y fly commands
- ``chat_invoke_finalize`` — post-procesado, Redis, multipart Telegram
- ``chat_sse`` / ``chat_http_routes`` — transporte HTTP/SSE
"""

from __future__ import annotations

from typing import Any

from core.chat_delivery_context import merge_delivery_context
from core.chat_graph_runner import run_chat_graph
from core.chat_http_routes import _register_agent_chat_routes, router
from core.chat_invoke_finalize import finalize_chat_response
from core.chat_invoke_prepare import prepare_chat_invoke
from core.chat_session import abort_chat_invoke_task, resolve_chat_session_id
from core.chat_sse import invoke_chat_sse_body
from core.models import ChatRequest
from duckclaw.channels import GatewayDeliveryContext


async def invoke_chat(
    payload: ChatRequest,
    worker_id: str,
    session_id: str,
    tenant_id: str,
    *,
    redis_client: Any = None,
    telegram_multipart_tail_delivery: str | None = None,
    telegram_mcp: Any = None,
    telegram_forced_vault_db_path: str | None = None,
    outbound_telegram_bot_token: str | None = None,
    delivery_context: GatewayDeliveryContext | None = None,
):
    """
    Orquesta la llamada al grafo LangGraph a partir de un ChatRequest.

    - session_id: ya resuelto (body + query + headers); debe ser el mismo en todos los POST del hilo.
    - delivery_context: si se omite, se reconstruye desde kwargs ``telegram_*`` (compatibilidad).
    """
    dc = merge_delivery_context(
        delivery_context,
        telegram_multipart_tail_delivery=telegram_multipart_tail_delivery,
        telegram_mcp=telegram_mcp,
        telegram_forced_vault_db_path=telegram_forced_vault_db_path,
        outbound_telegram_bot_token=outbound_telegram_bot_token,
    )
    prepared = await prepare_chat_invoke(
        payload,
        worker_id,
        session_id,
        tenant_id,
        dc,
        redis_client=redis_client,
    )
    if isinstance(prepared, dict):
        return prepared

    result, t0 = await run_chat_graph(prepared, redis_client=redis_client)
    if isinstance(result, dict) and "reply" not in result and "response" in result:
        return result

    return await finalize_chat_response(
        prepared,
        result,
        t0=t0,
        redis_client=redis_client,
    )


_register_agent_chat_routes(
    invoke_chat=invoke_chat,
    invoke_chat_sse_body=invoke_chat_sse_body,
)

__all__ = [
    "abort_chat_invoke_task",
    "invoke_chat",
    "invoke_chat_sse_body",
    "resolve_chat_session_id",
    "router",
]
