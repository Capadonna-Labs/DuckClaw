# services/api-gateway/main.py
"""
DuckClaw API Gateway — Microservicio unificado.

Punto de entrada único para n8n, Telegram, Angular y escrituras a DuckDB.
Endpoints: /api/v1/agent/chat, /api/v1/db/write, homeostasis, system health.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
import traceback
import uuid
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import redis.asyncio as redis

# Cargar .env desde repo root
_repo_root = Path(__file__).resolve().parent.parent.parent
for _base in (_repo_root, Path.cwd()):
    _env = _base / ".env"
    if _env.is_file():
        for _line in _env.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                if _k.strip():
                    os.environ.setdefault(_k.strip(), _v.strip().strip("'\""))
        break

try:
    from core.config import settings
except ImportError:
    class _Settings:
        PROJECT_NAME = "DuckClaw API Gateway"
        VERSION = "0.1.0"
        REDIS_URL = "redis://localhost:6379/0"
    settings = _Settings()

# Logs para PM2
def _ensure_log_handler():
    for name in ("duckclaw.gateway", "duckclaw.graphs.general_graph", "duckclaw.graphs.retail_graph", "duckclaw.graphs.manager_graph", "duckclaw.bi.agent"):
        log = logging.getLogger(name)
        if not log.handlers:
            h = logging.StreamHandler(sys.stdout)
            h.setLevel(logging.INFO)
            h.setFormatter(logging.Formatter("%(message)s"))
            log.addHandler(h)
            log.setLevel(logging.INFO)
_ensure_log_handler()
_gateway_log = logging.getLogger("duckclaw.gateway")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = redis.from_url(str(settings.REDIS_URL), decode_responses=True)
    yield
    await app.state.redis.aclose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API unificada para n8n, Telegram, agentes y escrituras DuckDB.",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _tailscale_auth_middleware(request: Request, call_next):
    auth_key = os.environ.get("DUCKCLAW_TAILSCALE_AUTH_KEY", "").strip()
    if not auth_key:
        return await call_next(request)
    path = request.url.path.rstrip("/") or "/"
    if path in ("/", "/health"):
        return await call_next(request)
    header_key = request.headers.get("X-Tailscale-Auth-Key", "").strip()
    if header_key != auth_key:
        return JSONResponse(
            status_code=401,
            content={"detail": "X-Tailscale-Auth-Key inválida o faltante"},
        )
    return await call_next(request)


app.middleware("http")(_tailscale_auth_middleware)


# ── Root y health ─────────────────────────────────────────────────────────────

@app.get("/")
async def root():
    return {
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "endpoints": [
            "/api/v1/agent/chat",
            "/api/v1/agent/{worker_id}/chat",
            "/api/v1/agent/workers",
            "/api/v1/agent/{worker_id}/history",
            "/api/v1/db/write",
            "/api/v1/homeostasis/status",
            "/api/v1/homeostasis/ask_task",
            "/api/v1/system/health",
        ],
    }


@app.get("/health")
async def health():
    return {"status": "ok", "service": "api-gateway"}


# ── System health ─────────────────────────────────────────────────────────────

@app.get("/api/v1/system/health")
async def system_health():
    tailscale = "unknown"
    if shutil.which("tailscale"):
        try:
            r = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            tailscale = "ok" if r.returncode == 0 else "error"
        except Exception:
            tailscale = "error"
    duckdb = "ok"
    mlx = "n/a"
    provider = (os.environ.get("DUCKCLAW_LLM_PROVIDER") or "").strip().lower()
    if provider == "mlx":
        mlx = "ok"
    return {"tailscale": tailscale, "duckdb": duckdb, "mlx": mlx}


# ── Homeostasis ───────────────────────────────────────────────────────────────

@app.get("/api/v1/homeostasis/status")
async def homeostasis_status():
    return []


class AskTaskBody(BaseModel):
    suggested_objectives: list[str] = Field(default_factory=list)


@app.post("/api/v1/homeostasis/ask_task")
async def homeostasis_ask_task(body: AskTaskBody = None):
    return {"ok": True, "trigger": "timer"}


# ── Agent ───────────────────────────────────────────────────────────────────

@app.get("/api/v1/agent/workers")
async def agent_workers():
    try:
        from duckclaw.workers.factory import list_workers
        workers = list_workers()
        return {"workers": workers}
    except Exception:
        return {"workers": ["finanz"]}


@app.get("/api/v1/agent/{worker_id}/history")
async def agent_history(worker_id: str, session_id: str = "default"):
    return {"history": [], "worker_id": worker_id}


class ChatBody(BaseModel):
    message: str = Field(..., description="Mensaje del usuario")
    session_id: str = Field("default", description="ID de sesión")
    history: list[dict] = Field(default_factory=list)
    stream: bool = Field(False, description="Streaming SSE")


@app.post("/api/v1/agent/chat")
@app.post("/api/v1/agent/{worker_id}/chat")
async def agent_chat(worker_id: Optional[str] = None, body: ChatBody = None):
    if body is None:
        body = ChatBody(message="", session_id="default")
    return await _invoke_chat(body.message, body.session_id, body.history, worker_id or "finanz")


def _truncate_log(s: str, max_len: int = 200) -> str:
    s = (s or "").strip()
    return s if len(s) <= max_len else s[:max_len] + "..."


def _strip_markdown_bold(s: str) -> str:
    """Quita asteriscos de negrita Markdown (**texto**) para respuesta más limpia."""
    if not s or not isinstance(s, str):
        return s
    return re.sub(r"\*\*([^*]*)\*\*", r"\1", s)


async def _invoke_chat(message: str, session_id: str, history: list, worker_id: str):
    _gateway_log.info("in: %s", _truncate_log(message))

    msg_stripped = (message or "").strip()
    # No invocar el grafo con mensaje vacío (evita plan vacío y respuesta "¿Cuál es mi tarea?")
    if not msg_stripped:
        return {
            "response": "No recibí ningún mensaje. Escribe tu consulta o comando (por ejemplo /tasks).",
            "session_id": session_id,
            "worker_id": worker_id,
            "elapsed_ms": 0,
        }
    if msg_stripped.startswith("/"):
        try:
            from duckclaw.graphs.on_the_fly_commands import handle_command
            from duckclaw.graphs.graph_server import get_db
            db = get_db()
            cmd_reply = handle_command(db, session_id, message)
            if cmd_reply is not None:
                _gateway_log.info("fly: %s", _truncate_log(cmd_reply))
                return {
                    "response": cmd_reply,
                    "session_id": session_id,
                    "worker_id": worker_id,
                    "elapsed_ms": 0,
                }
        except Exception as exc:
            _gateway_log.error("fly command failed: %s", exc)

    try:
        from duckclaw.graphs.graph_server import _get_or_build_graph, _ainvoke
        graph = _get_or_build_graph()
    except Exception as exc:
        _gateway_log.error("graph init failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=503, detail=f"Error inicializando el grafo: {exc}")

    try:
        from duckclaw.graphs.activity import set_busy, set_idle
        set_busy(session_id, task=message)
    except Exception:
        pass
    t0 = time.monotonic()
    try:
        result = await _ainvoke(graph, message, history or [], session_id)
    except Exception as exc:
        try:
            from duckclaw.graphs.activity import set_idle
            set_idle(session_id)
        except Exception:
            pass
        try:
            from duckclaw.graphs.on_the_fly_commands import append_task_audit, get_worker_id_for_chat
            from duckclaw.graphs.graph_server import get_db
            db = get_db()
            wid = get_worker_id_for_chat(db, session_id) or worker_id
            elapsed_fail = int((time.monotonic() - t0) * 1000)
            append_task_audit(db, session_id, wid, message, "FAILED", elapsed_fail)
        except Exception:
            pass
        try:
            if os.environ.get("DUCKCLAW_SAVE_CONVERSATION_TRACES", "true").strip().lower() in ("true", "1", "yes"):
                from duckclaw.graphs.conversation_traces import append_conversation_trace
                from duckclaw.graphs.on_the_fly_commands import get_effective_system_prompt
                from duckclaw.graphs.graph_server import get_db
                _db = get_db()
                _sys = (get_effective_system_prompt(_db, worker_id) or "").strip()
                _sys = _sys or (os.environ.get("DUCKCLAW_SYSTEM_PROMPT") or "").strip() or None
                append_conversation_trace(
                    session_id, message, str(exc)[:8192],
                    worker_id=worker_id, elapsed_ms=elapsed_fail, status="FAILED",
                    system_prompt=_sys,
                )
        except Exception:
            pass
        _gateway_log.error("agent_chat failed: %s\n%s", exc, traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(exc))

    try:
        from duckclaw.graphs.activity import set_idle
        set_idle(session_id)
    except Exception:
        pass
    reply_text = result.get("reply", "") if isinstance(result, dict) else (result or "")
    _gateway_log.info("out: %s", _truncate_log(reply_text))
    reply_text = _strip_markdown_bold(reply_text or "")
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    # Grafo manager devuelve assigned_worker_id; usarlo para respuesta y trazas
    effective_worker_id = result.get("assigned_worker_id", worker_id) if isinstance(result, dict) else worker_id
    try:
        if not result.get("_audit_done"):
            from duckclaw.graphs.on_the_fly_commands import append_task_audit, get_worker_id_for_chat
            from duckclaw.graphs.graph_server import get_db
            db = get_db()
            wid = get_worker_id_for_chat(db, session_id) or worker_id
            append_task_audit(db, session_id, wid, message, "SUCCESS", elapsed_ms)
    except Exception:
        pass
    try:
        if os.environ.get("DUCKCLAW_SAVE_CONVERSATION_TRACES", "true").strip().lower() in ("true", "1", "yes"):
            from duckclaw.graphs.conversation_traces import append_conversation_trace
            from duckclaw.graphs.on_the_fly_commands import get_effective_system_prompt
            from duckclaw.graphs.graph_server import get_db
            trace_messages = result.get("messages") if isinstance(result, dict) else None
            db = get_db()
            system_from_prompt = (get_effective_system_prompt(db, effective_worker_id) or "").strip()
            system_for_trace = system_from_prompt or (os.environ.get("DUCKCLAW_SYSTEM_PROMPT") or "").strip() or None
            append_conversation_trace(
                session_id, message, reply_text or "",
                worker_id=effective_worker_id, elapsed_ms=elapsed_ms, status="SUCCESS",
                system_prompt=system_for_trace,
                messages=trace_messages,
            )
    except Exception:
        pass
    try:
        from duckclaw.graphs.on_the_fly_commands import _telegram_safe
        reply_text = _telegram_safe(reply_text)
    except Exception:
        pass
    return {
        "response": reply_text,
        "session_id": session_id,
        "worker_id": effective_worker_id or worker_id,
        "elapsed_ms": elapsed_ms,
    }


# ── Escrituras DuckDB (encolar en Redis) ──────────────────────────────────────

class WriteRequest(BaseModel):
    query: str = Field(..., description="Consulta SQL parametrizada")
    params: list = Field(default_factory=list, description="Parámetros para la consulta")
    tenant_id: str = Field(default="default", description="ID del tenant")


class EnqueueResponse(BaseModel):
    status: str
    task_id: str


@app.post("/api/v1/db/write", response_model=EnqueueResponse, status_code=status.HTTP_202_ACCEPTED)
async def enqueue_write(req: WriteRequest):
    """Encola escrituras para el DB Writer (evita bloqueos en DuckDB)."""
    if req.query.strip().upper().startswith("SELECT"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Las consultas SELECT deben ejecutarse directamente, no encolarse.",
        )
    task_id = str(uuid.uuid4())
    payload = {"task_id": task_id, "tenant_id": req.tenant_id, "query": req.query, "params": req.params}
    try:
        await app.state.redis.lpush("duckdb_write_queue", json.dumps(payload))
        return EnqueueResponse(status="enqueued", task_id=task_id)
    except redis.RedisError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error conectando al broker de mensajes: {str(e)}",
        )


# ── Quotes router (microservicio: routers en services/api-gateway) ───────────

try:
    from routers.quotes import router as quotes_router
    app.include_router(quotes_router)
except ImportError:
    pass
