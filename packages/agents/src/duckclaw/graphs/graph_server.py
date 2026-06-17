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

import os
from pathlib import Path
from typing import Any

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

from duckclaw.utils.logger import configure_structured_logging

_lvl_name = (os.environ.get("DUCKCLAW_LOG_LEVEL") or "INFO").strip().upper()
configure_structured_logging(level=getattr(_logging, _lvl_name, _logging.INFO))

# ── FastAPI app ────────────────────────────────────────────────────────────────

try:
    from fastapi import FastAPI, Request
    from fastapi.middleware.cors import CORSMiddleware
    from starlette.responses import JSONResponse
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

from duckclaw.graphs.graph_server_ephemeral import (  # noqa: E402
    invoke_ephemeral_gateway_graph as _invoke_ephemeral_gateway_graph,
    is_duckdb_lock_error as _is_duckdb_lock_error,
    resolve_llm_triplet_for_graph_invoke as _resolve_llm_triplet_for_graph_invoke,
)
from duckclaw.graphs.graph_server_invoke import (  # noqa: E402
    _ainvoke,
    ainvoke_manager_ephemeral,
)
from duckclaw.graphs.graph_server_llm_config import (  # noqa: E402
    _ensure_llm_config,
    _resolve_display_model,
    get_graph_state,
)
from duckclaw.graphs.graph_server_routes import (  # noqa: E402
    InvokeRequest,
    InvokeResponse,
    register_graph_server_routes,
)
from duckclaw.graphs.graph_server_studio import (  # noqa: E402
    _build_manager_graph_for_db,
    _ensure_studio_graph,
    _get_or_build_graph,
    _graph_init_error,
    get_graph,
)

# Compatibilidad histórica: tests y graph_server_ephemeral mutaban _graph_state en el facade.
_graph_state = get_graph_state()

register_graph_server_routes(app)


def get_db() -> Any:
    """
    Acceso RO efímero al DuckDB del gateway (sin handle persistente).
    Para comandos fly, ACL y auditoría desde el API Gateway.
    """
    from duckclaw.gateway_db import GatewayDbEphemeralReadonly, get_gateway_db_path

    p = get_gateway_db_path()
    os.makedirs(str(Path(p).parent), exist_ok=True)
    return GatewayDbEphemeralReadonly(p)


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
