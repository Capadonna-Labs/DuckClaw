"""Endpoints FastAPI del servidor LangGraph (invoke, stream, health, /graph)."""

from __future__ import annotations

import asyncio
import os
import time
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from duckclaw.graphs.graph_server_ephemeral import (
    invoke_ephemeral_gateway_graph as _invoke_ephemeral_gateway_graph,
)
from duckclaw.graphs.graph_server_invoke import _ainvoke
from duckclaw.graphs.graph_server_llm_config import _ensure_llm_config, _resolve_display_model
from duckclaw.graphs.graph_server_studio import _ensure_studio_graph
from duckclaw.utils.logger import format_chat_log_identity, structured_log_context


class InvokeRequest(BaseModel):
    message: str = Field(..., description="Mensaje del usuario")
    chat_id: str = Field("api", description="ID de sesión (para memoria de conversación)")
    tenant_id: str = Field("default", description="ID del tenant (para whitelist y aislamiento de workers)")
    history: list[dict] = Field(default_factory=list, description="Historial [{role, content}]")
    stream: bool = Field(False, description="Si true, usar /stream en su lugar")
    username: str | None = Field(None, description="Nombre del usuario (para grupos)")
    chat_type: str | None = Field(None, description="Tipo de chat: private, group, supergroup, etc.")
    user_id: str | None = Field(None, description="ID del usuario para resolver bóveda activa")


class InvokeResponse(BaseModel):
    reply: str
    model: str
    elapsed_ms: int
    chat_id: str
    usage_tokens: dict[str, int] | None = None


async def _async_sleep(seconds: float) -> None:
    await asyncio.sleep(seconds)


def register_graph_server_routes(app: FastAPI) -> None:
    """Registra rutas HTTP en la app FastAPI del graph server."""

    @app.get("/", summary="Info del servidor")
    async def root():
        from duckclaw.gateway_db import get_gateway_db_path

        return {
            "service": "DuckClaw LangGraph API",
            "version": "0.1.0",
            "model": _resolve_display_model(),
            "db_path": get_gateway_db_path() or "(default)",
            "tracing": os.environ.get("LANGCHAIN_TRACING_V2", "false"),
            "project": os.environ.get("LANGCHAIN_PROJECT", ""),
            "endpoints": ["/invoke", "/stream", "/health", "/docs"],
        }

    @app.get("/health", summary="Health check")
    async def health():
        return {"status": "ok", "model": _resolve_display_model()}

    @app.post("/invoke", response_model=InvokeResponse, summary="Invocar el grafo")
    async def invoke(req: InvokeRequest):
        """
        Envía un mensaje al grafo LangGraph y retorna la respuesta.
        Las trazas se envían automáticamente a LangSmith si LANGCHAIN_TRACING_V2=true.
        """
        try:
            _ensure_llm_config()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Error inicializando el grafo: {exc}")

        from duckclaw.manager.graph import trim_worker_graph_cache

        graph, db = await asyncio.to_thread(_invoke_ephemeral_gateway_graph, req.chat_id)
        history = req.history or []

        t0 = time.monotonic()
        uid = (req.user_id or "").strip() or req.chat_id
        chat_ident = format_chat_log_identity(req.chat_id, req.username)
        try:
            with structured_log_context(tenant_id=req.tenant_id, chat_id=chat_ident, worker_id="manager"):
                result = await _ainvoke(
                    graph,
                    req.message,
                    history,
                    req.chat_id,
                    tenant_id=req.tenant_id,
                    user_id=uid,
                    username=req.username,
                )
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Error en el grafo: {exc}")
        finally:
            try:
                db.close()
            except Exception:
                pass
            trim_worker_graph_cache()

        elapsed_ms = int((time.monotonic() - t0) * 1000)
        return InvokeResponse(
            reply=result.get("reply", ""),
            model=_resolve_display_model(),
            elapsed_ms=elapsed_ms,
            chat_id=req.chat_id,
            usage_tokens=result.get("usage_tokens"),
        )

    @app.post("/stream", summary="Invocar el grafo con streaming SSE")
    async def stream(req: InvokeRequest):
        """
        Streaming de la respuesta token por token usando Server-Sent Events (SSE).
        Cada evento tiene el formato: data: <token>\\n\\n
        El evento final es: data: [DONE]\\n\\n
        """
        try:
            _ensure_llm_config()
        except Exception as exc:
            raise HTTPException(status_code=503, detail=f"Error inicializando el grafo: {exc}")

        from duckclaw.manager.graph import trim_worker_graph_cache

        graph, db = await asyncio.to_thread(_invoke_ephemeral_gateway_graph, req.chat_id)

        async def event_generator() -> AsyncGenerator[str, None]:
            try:
                uid = (req.user_id or "").strip() or req.chat_id
                chat_ident = format_chat_log_identity(req.chat_id, req.username)
                with structured_log_context(tenant_id=req.tenant_id, chat_id=chat_ident, worker_id="manager"):
                    invoke_result = await _ainvoke(
                        graph,
                        req.message,
                        req.history,
                        req.chat_id,
                        tenant_id=req.tenant_id,
                        user_id=uid,
                        username=req.username,
                    )
                reply = invoke_result.get("reply", "") or ""
                for word in reply.split(" "):
                    yield f"data: {word} \n\n"
                    await _async_sleep(0.02)
                yield "data: [DONE]\n\n"
            except Exception as exc:
                yield f"data: [ERROR] {exc}\n\n"
            finally:
                try:
                    db.close()
                except Exception:
                    pass
                trim_worker_graph_cache()

        return StreamingResponse(
            event_generator(),
            media_type="text/event-stream",
            headers={"X-Accel-Buffering": "no", "Cache-Control": "no-cache"},
        )

    @app.get("/graph", summary="Estructura del grafo compilado")
    async def graph_info():
        """Retorna la estructura del grafo en formato JSON (compatible con LangSmith Studio)."""
        try:
            graph = _ensure_studio_graph()
            if hasattr(graph, "get_graph"):
                g = graph.get_graph()
                return JSONResponse(content={
                    "nodes": [str(n) for n in (g.nodes if hasattr(g, "nodes") else [])],
                    "edges": [str(e) for e in (g.edges if hasattr(g, "edges") else [])],
                })
            return {"graph": "compiled", "type": str(type(graph).__name__)}
        except Exception as exc:
            raise HTTPException(status_code=500, detail=str(exc))
