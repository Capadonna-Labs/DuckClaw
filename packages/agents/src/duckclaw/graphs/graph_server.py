"""
DuckClaw LangGraph API Server
─────────────────────────────
Expone el grafo LangGraph como una API REST para uso desde LangSmith,
aplicaciones externas o integración en internet.

Uso directo:
  python -m duckclaw.graphs.graph_server               # puerto 8123
  python -m duckclaw.graphs.graph_server --port 9000
  python -m duckclaw.graphs.graph_server --host 0.0.0.0 --port 8123

Via duckops:
  duckops serve --port 8123
  duckops serve --pm2 --name DuckClaw-API   # genera config/ecosystem.graph_api.config.cjs

Endpoints:
  GET  /             → info del grafo y configuración activa
  GET  /health       → {"status": "ok", "model": "mlx:Slayer-8B-V1.1"}
  POST /invoke       → invocar el grafo con un mensaje
  POST /stream       → invocar con streaming SSE (requiere Accept: text/event-stream)
  GET  /graph        → JSON del grafo compilado (para LangSmith Studio)
"""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any, AsyncGenerator, Optional

# ── dotenv ─────────────────────────────────────────────────────────────────────

def _load_dotenv() -> None:
    for base in (Path.cwd(), Path(__file__).resolve().parent.parent.parent):
        env_file = base / ".env"
        if env_file.is_file():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip()
                    if value.startswith('"') and value.endswith('"'):
                        value = value[1:-1]
                    elif value.startswith("'") and value.endswith("'"):
                        value = value[1:-1]
                    if key:
                        if key == "DUCKCLAW_CHAT_PARALLEL_INVOCATIONS":
                            os.environ[key] = value
                        else:
                            os.environ.setdefault(key, value)
            except Exception:
                pass
            break

_load_dotenv()

import logging as _logging
from functools import partial


def _parallel_chat_invocations_enabled() -> bool:
    """Alineado con DUCKCLAW_CHAT_PARALLEL_INVOCATIONS en services/api-gateway/main.py."""
    return (os.environ.get("DUCKCLAW_CHAT_PARALLEL_INVOCATIONS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


from duckclaw.utils.langsmith_trace import get_tracing_config
from duckclaw.utils.logger import (
    configure_structured_logging,
    extract_usage_from_messages,
    format_chat_log_identity,
    structured_log_context,
)

_lvl_name = (os.environ.get("DUCKCLAW_LOG_LEVEL") or "INFO").strip().upper()
configure_structured_logging(level=getattr(_logging, _lvl_name, _logging.INFO))

# ── FastAPI app ────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse, StreamingResponse
    from pydantic import BaseModel, Field
except ImportError as exc:
    raise ImportError(
        "Instala las dependencias del servidor:\n"
        "  uv sync --extra serve\n"
        "  # o: pip install fastapi uvicorn"
    ) from exc

app = FastAPI(
    title="DuckClaw LangGraph API",
    description="API REST para el grafo LangGraph de DuckClaw con trazas a LangSmith.",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def _tailscale_auth_middleware(request: Request, call_next):
    """Valida X-Tailscale-Auth-Key si DUCKCLAW_TAILSCALE_AUTH_KEY está definida."""
    from starlette.responses import JSONResponse
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

# ── Estado global del grafo ────────────────────────────────────────────────────
# No se guarda conexión DuckDB al archivo del gateway entre peticiones (evita lock con db-writer).
# Se cachea LLM + rutas; el grafo manager se compila por turno con un DuckClaw RO efímero.
# Para LangGraph Studio: grafo aparte contra :memory: (sin lock de archivo).

_graph_state: dict[str, Any] = {}
_graph_init_error: Optional[Exception] = None


def _ensure_llm_config() -> None:
    """Carga y cachea LLM y metadatos. No abre el .duckdb del gateway."""
    from duckclaw.integrations.llm_providers import (
        _ensure_duckclaw_llm_env_from_legacy_llm_vars,
        build_llm,
    )
    from duckclaw.gateway_db import get_gateway_db_path

    # Misma fusión LLM_* → DUCKCLAW_* que build_llm (evita leer solo DUCKCLAW_* obsoleto).
    _ensure_duckclaw_llm_env_from_legacy_llm_vars()

    provider = os.environ.get("DUCKCLAW_LLM_PROVIDER", "mlx").strip().lower()
    model = os.environ.get("DUCKCLAW_LLM_MODEL", "").strip()
    base_url = os.environ.get("DUCKCLAW_LLM_BASE_URL", "http://127.0.0.1:8080/v1").strip()
    fingerprint = (provider, model, base_url)

    if _graph_state.get("llm") is not None and _graph_state.get("_llm_env_fingerprint") == fingerprint:
        return

    # Proveedor/modelo/base cambiaron: el grafo Studio y el LLM global deben reconstruirse.
    if _graph_state.get("llm") is not None:
        try:
            _sd = _graph_state.get("studio_db")
            if _sd is not None and hasattr(_sd, "close"):
                _sd.close()
        except Exception:
            pass
        _graph_state.pop("studio_graph", None)
        _graph_state.pop("studio_db", None)
        _graph_state.pop("_llm_env_fingerprint", None)
        _graph_state.pop("llm", None)

    db_path = get_gateway_db_path()
    os.makedirs(str(Path(db_path).parent), exist_ok=True)

    system_prompt = os.environ.get(
        "DUCKCLAW_SYSTEM_PROMPT",
        "Eres un asistente útil con acceso a una base de datos.",
    ).strip()

    llm = build_llm(provider, model, base_url)
    if llm is None:
        raise RuntimeError(
            "No se pudo inicializar el LLM. "
            "Configura DUCKCLAW_LLM_PROVIDER y DUCKCLAW_LLM_BASE_URL en .env."
        )

    _graph_state["llm"] = llm
    _graph_state["_llm_env_fingerprint"] = fingerprint
    _graph_state["provider"] = provider
    _graph_state["model"] = model
    _graph_state["base_url"] = base_url
    _graph_state["db_path"] = db_path
    _graph_state["system_prompt"] = system_prompt


def _build_manager_graph_for_db(
    db: Any,
    *,
    llm_override: Any | None = None,
    llm_provider_override: str | None = None,
    llm_model_override: str | None = None,
    llm_base_url_override: str | None = None,
) -> Any:
    """Compila el grafo manager con la conexión ``db`` del turno (o :memory: para Studio)."""
    from duckclaw.forge import AgentAssembler, MANAGER_ROUTER_YAML

    _ensure_llm_config()
    llm = _graph_state["llm"] if llm_override is None else llm_override
    provider = _graph_state["provider"] if llm_provider_override is None else llm_provider_override
    model = _graph_state["model"] if llm_model_override is None else llm_model_override
    base_url = _graph_state["base_url"] if llm_base_url_override is None else llm_base_url_override
    db_path = _graph_state["db_path"]
    system_prompt = _graph_state["system_prompt"]

    # :memory: exige read_only=False en DuckDB; no advertir por ello.
    _dp = (getattr(db, "_path", None) or "").strip()
    if (
        db is not None
        and _dp
        and _dp != ":memory:"
        and not getattr(db, "_read_only", False)
    ):
        _logging.getLogger(__name__).warning(
            "graph_server: DuckClaw no está en read_only; revisar core y ruta gateway (multiplex)"
        )

    return AgentAssembler.from_yaml(MANAGER_ROUTER_YAML).build(
        db=db,
        llm=llm,
        system_prompt=system_prompt,
        llm_provider=provider,
        llm_model=model,
        llm_base_url=base_url,
        db_path=db_path,
    )


def _ensure_studio_graph() -> Any:
    """Grafo compilado contra :memory: para langgraph dev / GET /graph (sin lock al vault)."""
    if _graph_state.get("studio_graph") is not None:
        return _graph_state["studio_graph"]

    from duckclaw import DuckClaw

    # DuckDB: «Cannot launch in-memory database in read-only mode»
    mem = DuckClaw(":memory:", read_only=False)
    _graph_state["studio_db"] = mem
    _graph_state["studio_graph"] = _build_manager_graph_for_db(mem)
    return _graph_state["studio_graph"]


def _is_duckdb_lock_error(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "lock" in msg or "conflicting" in msg


def _open_duckclaw_readonly_with_retry(db_path: str) -> Any:
    """
    Abre DuckClaw RO al archivo; reintenta si el db-writer u otro proceso tiene el lock RW.
    Alineado con el backoff de ``context_injection_handler._connect_duckdb_writable``.
    """
    from duckclaw import DuckClaw

    raw_attempts = (os.environ.get("DUCKCLAW_GATEWAY_RO_LOCK_ATTEMPTS") or "24").strip()
    try:
        attempts = max(1, min(int(raw_attempts), 80))
    except ValueError:
        attempts = 24
    raw_sleep = (os.environ.get("DUCKCLAW_GATEWAY_RO_LOCK_BASE_SLEEP_S") or "0.15").strip()
    try:
        base_sleep_s = float(raw_sleep)
    except ValueError:
        base_sleep_s = 0.15
    base_sleep_s = max(0.05, base_sleep_s)

    log = _logging.getLogger(__name__)
    last: BaseException | None = None
    for i in range(attempts):
        try:
            return DuckClaw(db_path, read_only=True)
        except Exception as exc:
            last = exc
            if _is_duckdb_lock_error(exc):
                delay = base_sleep_s * min(i + 1, 12)
                log.warning(
                    "graph_server: DuckDB RO lock intento %s/%s, reintento en %.2fs: %s",
                    i + 1,
                    attempts,
                    delay,
                    exc,
                )
                time.sleep(delay)
                continue
            raise
    assert last is not None
    raise last


def _paths_same_canonical(a: str, b: str) -> bool:
    if not (a or "").strip() or not (b or "").strip():
        return False
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return (a or "").strip() == (b or "").strip()


def _invoke_ephemeral_gateway_graph(
    chat_id: str | None = None,
    vault_db_path: str | None = None,
) -> tuple[Any, Any]:
    """
    Abre DuckClaw RO al archivo del gateway, compila el manager y devuelve (graph, db).
    El caller debe ``db.close()`` y llamar ``clear_worker_graph_cache()`` en ``finally``.

    Si ``chat_id`` tiene llm_* en agent_config (p. ej. /model), el LLM del grafo sigue esa
    tripleta en lugar del cache global basado solo en env. Con ``vault_db_path``, la tripleta
    se resuelve primero en el vault del tenant (Telegram multiplex) y solo si no hay override
    se usa el hub.
    """
    from duckclaw.graphs.manager_graph import clear_worker_graph_cache
    from duckclaw.integrations.llm_providers import build_llm

    _ensure_llm_config()
    db_path = str(_graph_state["db_path"])
    os.makedirs(str(Path(db_path).parent), exist_ok=True)
    clear_worker_graph_cache()
    db = _open_duckclaw_readonly_with_retry(db_path)
    ovr: dict[str, Any] = {}
    _log = _logging.getLogger(__name__)
    trip: tuple[str, str, str] | None = None
    trip_source = "env_defaults"
    v_p = (vault_db_path or "").strip()
    try:
        from duckclaw.gateway_db import GatewayDbEphemeralReadonly
        from duckclaw.graphs.on_the_fly_commands import resolve_llm_triplet_for_chat_invocation

        same_file = bool(v_p and v_p != ":memory:" and _paths_same_canonical(v_p, db_path))
        if same_file:
            trip = resolve_llm_triplet_for_chat_invocation(db, chat_id)
            trip_source = "same_file_as_hub" if trip else "same_file_no_chat_override"
        elif v_p and v_p != ":memory:":
            try:
                trip = resolve_llm_triplet_for_chat_invocation(GatewayDbEphemeralReadonly(v_p), chat_id)
                trip_source = "vault_separate" if trip else "vault_separate_no_override"
            except Exception as exc:
                _log.warning(
                    "graph_server: resolve_llm_triplet vault read failed chat_id=%s vault_suffix=%s err=%s",
                    chat_id,
                    v_p[-96:] if len(v_p) > 96 else v_p,
                    exc,
                )
                trip = None
                trip_source = "vault_read_error"
        if trip is None and not same_file:
            trip = resolve_llm_triplet_for_chat_invocation(db, chat_id)
            if trip is not None:
                trip_source = "hub_only"
        if trip is not None:
            tp, tm, tu = trip
            try:
                built = build_llm(tp, tm, tu, prefer_env_provider=False)
            except Exception as exc:
                _log.warning(
                    "graph_server: build_llm(chat triplet) failed provider=%s err=%s",
                    tp,
                    exc,
                    exc_info=True,
                )
                built = None
            if built is not None:
                ovr = {
                    "llm_override": built,
                    "llm_provider_override": tp,
                    "llm_model_override": tm,
                    "llm_base_url_override": tu,
                }
                # region agent log
                try:
                    import importlib.util
                    import json as _json_dbg

                    _lpath = ""
                    try:
                        _spec_lp = importlib.util.find_spec("duckclaw.integrations.llm_providers")
                        if _spec_lp and _spec_lp.origin:
                            _lpath = str(_spec_lp.origin)
                    except Exception:
                        pass
                    _bm = getattr(built, "model_name", None) or getattr(built, "model", "") or ""
                    _bb = getattr(built, "openai_api_base", None) or getattr(built, "base_url", None) or ""
                    _payload = {
                        "sessionId": "c964f7",
                        "hypothesisId": "H-A",
                        "location": "graph_server.py:_invoke_ephemeral_gateway_graph",
                        "message": "build_llm_chat_triplet_ok",
                        "data": {
                            "trip_provider": tp,
                            "trip_model": (tm or "")[:120],
                            "trip_base": (tu or "")[:160],
                            "built_model": str(_bm)[:120],
                            "built_base": str(_bb)[:160],
                            "llm_providers_path": _lpath[-220:],
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                    with open(
                        "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
                        "a",
                        encoding="utf-8",
                    ) as _df:
                        _df.write(_json_dbg.dumps(_payload, ensure_ascii=False) + "\n")
                except Exception:
                    pass
                # endregion
            else:
                _log.warning(
                    "graph_server: build_llm returned None for chat triplet provider=%s model=%s",
                    tp,
                    (tm or "")[:80],
                )
        _env_llm_provider = str(_graph_state.get("provider") or "")
        _invoke_provider = _env_llm_provider
        if ovr.get("llm_provider_override"):
            _invoke_provider = str(ovr.get("llm_provider_override") or "")
        elif trip:
            _invoke_provider = str(trip[0] or "")
        _log.info(
            "graph_server: llm_invoke_override chat_id=%s trip_source=%s has_trip=%s ovr=%s global_provider=%s env_llm_provider=%s",
            chat_id,
            trip_source,
            trip is not None,
            bool(ovr),
            _invoke_provider,
            _env_llm_provider,
        )
    except Exception as exc:
        _log.warning("graph_server: LLM override resolution failed: %s", exc, exc_info=True)
    graph = _build_manager_graph_for_db(db, **ovr)
    return graph, db


# ── Pre-inicialización en tiempo de importación ────────────────────────────────
# langgraph dev importa este módulo antes del event loop: solo LLM (+ grafo :memory: opcional).

def _pre_init() -> None:
    global _graph_init_error
    try:
        _ensure_llm_config()
        _ensure_studio_graph()
    except Exception as exc:
        _graph_init_error = exc
        print(f"[graph_server] Pre-init warning: {exc}", flush=True)

_pre_init()


def _resolve_display_model() -> str:
    provider = os.environ.get("DUCKCLAW_LLM_PROVIDER", "mlx")
    if provider == "mlx":
        mid = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
        if mid:
            return f"mlx:{mid.rstrip('/').rsplit('/', 1)[-1]}"
        return "mlx:local"
    model = os.environ.get("DUCKCLAW_LLM_MODEL", "")
    return f"{provider}:{model}" if model else provider


# ── Pydantic models ────────────────────────────────────────────────────────────

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


# ── Endpoints ──────────────────────────────────────────────────────────────────

@app.get("/", summary="Info del servidor")
async def root():
    from duckclaw.gateway_db import get_gateway_db_path

    return {
        "service":    "DuckClaw LangGraph API",
        "version":    "0.1.0",
        "model":      _resolve_display_model(),
        "db_path":    get_gateway_db_path() or "(default)",
        "tracing":    os.environ.get("LANGCHAIN_TRACING_V2", "false"),
        "project":    os.environ.get("LANGCHAIN_PROJECT", ""),
        "endpoints":  ["/invoke", "/stream", "/health", "/docs"],
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

    from duckclaw.graphs.manager_graph import clear_worker_graph_cache

    graph, db = await asyncio.to_thread(_invoke_ephemeral_gateway_graph, req.chat_id)
    # Enriquecer el estado con identidad (username/chat_type) para general_graph.
    history = req.history or []
    state = {
        "incoming": req.message,
        "history": history,
        "username": req.username or "",
        "chat_type": (req.chat_type or "").lower() if req.chat_type else "",
    }

    t0 = time.monotonic()
    uid = (req.user_id or "").strip() or req.chat_id
    chat_ident = format_chat_log_identity(req.chat_id, req.username)
    try:
        with structured_log_context(tenant_id=req.tenant_id, chat_id=chat_ident, worker_id="manager"):
            # El grafo manager se encarga de mapear state → subgrafos; general_graph usará username/chat_type.
            result = await _ainvoke(
                graph,
                state["incoming"],
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
        clear_worker_graph_cache()

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

    from duckclaw.graphs.manager_graph import clear_worker_graph_cache

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
            clear_worker_graph_cache()

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
        # LangGraph compiled graphs exponen get_graph()
        if hasattr(graph, "get_graph"):
            g = graph.get_graph()
            return JSONResponse(content={
                "nodes": [str(n) for n in (g.nodes if hasattr(g, "nodes") else [])],
                "edges": [str(e) for e in (g.edges if hasattr(g, "edges") else [])],
            })
        return {"graph": "compiled", "type": str(type(graph).__name__)}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


# ── Helpers async ──────────────────────────────────────────────────────────────

async def _ainvoke(
    graph: Any,
    message: str,
    history: list,
    chat_id: str,
    *,
    tenant_id: str = "default",
    user_id: str | None = None,
    username: str | None = None,
    vault_db_path: str | None = None,
    shared_db_path: str | None = None,
    is_system_prompt: bool | None = False,
    outbound_telegram_bot_token: str | None = None,
) -> dict:
    """
    Invoca el grafo y retorna {"reply": str, "messages": list | None}.
    messages (cuando existe) es la secuencia completa del turno para trazas SFT (tool_calls, tool, assistant).
    """
    import asyncio

    # `input` primero: LangSmith suele usar esta clave para la columna **Input** en la tabla Runs
    # (convención LangChain). `incoming` sigue siendo la fuente de verdad en el grafo.
    _tok = (outbound_telegram_bot_token or "").strip() or None
    state: dict[str, Any] = {
        "input": message,
        "incoming": message,
        "history": history or [],
        "chat_id": chat_id,
        "tenant_id": tenant_id,
        "user_id": (user_id or "").strip() or str(chat_id),
        "username": (username or "").strip(),
        "vault_db_path": (vault_db_path or "").strip() or "",
        "shared_db_path": (shared_db_path or "").strip() or "",
    }
    if _tok:
        state["outbound_telegram_bot_token"] = _tok
    if is_system_prompt:
        state["is_system_prompt"] = True
    loop = asyncio.get_event_loop()

    trace_cfg = get_tracing_config(tenant_id, "manager", chat_id)
    # ainvoke sigue ejecutando nodos síncronos (p. ej. worker_graph.invoke) en el event loop
    # y bloquea otras peticiones HTTP. Con paralelismo por chat, mover invoke a un hilo.
    if _parallel_chat_invocations_enabled():
        result = await asyncio.to_thread(graph.invoke, state, trace_cfg)
    elif hasattr(graph, "ainvoke"):
        result = await graph.ainvoke(state, trace_cfg)
    else:
        result = await loop.run_in_executor(None, partial(graph.invoke, state, trace_cfg))

    reply = str(result.get("reply") or result.get("output") or "Sin respuesta.")
    messages = result.get("messages")
    usage = extract_usage_from_messages(messages)
    out: dict[str, Any] = {"reply": reply, "messages": messages}
    if usage:
        out["usage_tokens"] = usage
    # Manager → subagente: propagar para logs/auditoría en el API Gateway (evita [finanz] cuando el worker real es otro).
    for _k in (
        "assigned_worker_id",
        "plan_title",
        "_audit_done",
        "sandbox_photo_base64",
        "sandbox_photos_base64",
        "sandbox_document_paths",
    ):
        if _k in result:
            out[_k] = result[_k]
    return out


async def _async_sleep(seconds: float) -> None:
    import asyncio
    await asyncio.sleep(seconds)


# ── get_graph() para langgraph.json / LangSmith Studio ─────────────────────────

def get_graph() -> Any:
    """
    Entry point para langgraph dev / LangSmith Studio.
    Usa DuckDB :memory: para no mantener lock sobre el archivo del gateway.
    """
    if _graph_init_error is not None and _graph_state.get("llm") is None:
        raise _graph_init_error
    try:
        return _ensure_studio_graph()
    except Exception as exc:
        if _graph_init_error is not None:
            raise _graph_init_error from exc
        raise


def get_db() -> Any:
    """
    Acceso RO efímero al DuckDB del gateway (sin handle persistente).
    Para comandos fly, ACL y auditoría desde el API Gateway.
    """
    from duckclaw.gateway_db import GatewayDbEphemeralReadonly, get_gateway_db_path

    p = get_gateway_db_path()
    os.makedirs(str(Path(p).parent), exist_ok=True)
    return GatewayDbEphemeralReadonly(p)


def _get_or_build_graph() -> Any:
    """Compatibilidad: mismo grafo que LangGraph Studio (:memory:), no el del archivo del gateway."""
    return _ensure_studio_graph()


async def ainvoke_manager_ephemeral(
    message: str,
    history: list,
    chat_id: str,
    *,
    tenant_id: str = "default",
    user_id: str | None = None,
    username: str | None = None,
    vault_db_path: str | None = None,
    shared_db_path: str | None = None,
    is_system_prompt: bool | None = False,
    outbound_telegram_bot_token: str | None = None,
) -> dict:
    """
    Compila el manager con un DuckClaw RO efímero al gateway, invoca y cierra.
    Uso recomendado desde services/api-gateway en lugar de retener un grafo global.
    """
    from duckclaw.graphs.manager_graph import clear_worker_graph_cache

    _ensure_llm_config()
    graph, db = await asyncio.to_thread(_invoke_ephemeral_gateway_graph, chat_id, vault_db_path)
    try:
        return await _ainvoke(
            graph,
            message,
            history,
            chat_id,
            tenant_id=tenant_id,
            user_id=user_id,
            username=username,
            vault_db_path=vault_db_path,
            shared_db_path=shared_db_path,
            is_system_prompt=is_system_prompt,
            outbound_telegram_bot_token=outbound_telegram_bot_token,
        )
    finally:
        try:
            db.close()
        except Exception:
            pass
        clear_worker_graph_cache()


# ── __main__ ───────────────────────────────────────────────────────────────────

def _run_server(host: str = "0.0.0.0", port: int = 8123, reload: bool = False) -> None:
    import uvicorn
    print(f"🦆⚔️  DuckClaw LangGraph API → http://{host}:{port}", flush=True)
    print(f"   Docs  → http://{host}:{port}/docs", flush=True)
    print(f"   Model → {_resolve_display_model()}", flush=True)
    tracing = os.environ.get("LANGCHAIN_TRACING_V2", "false")
    project = os.environ.get("LANGCHAIN_PROJECT", "")
    if tracing == "true" and project:
        print(f"   LangSmith → project={project} (trazas activas)", flush=True)
    elif tracing != "true":
        print("   LangSmith → trazas DESACTIVADAS (añade LANGCHAIN_TRACING_V2=true a .env)", flush=True)
    uvicorn.run(
        "duckclaw.graphs.graph_server:app",
        host=host,
        port=port,
        reload=reload,
        log_level="info",
    )


if __name__ == "__main__":
    import argparse
    try:
        default_port = int(os.environ.get("DUCKCLAW_API_PORT", "8123"))
    except ValueError:
        default_port = 8123
    parser = argparse.ArgumentParser(description="DuckClaw LangGraph API Server")
    parser.add_argument("--host",   default="0.0.0.0", help="Host (default: 0.0.0.0)")
    parser.add_argument("--port",   default=default_port, type=int, help=f"Puerto (default: {default_port}, o DUCKCLAW_API_PORT)")
    parser.add_argument("--reload", action="store_true",    help="Reload automático en desarrollo")
    args = parser.parse_args()
    _run_server(host=args.host, port=args.port, reload=args.reload)
