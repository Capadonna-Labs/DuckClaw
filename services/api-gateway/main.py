# services/api-gateway/main.py
"""
DuckClaw API Gateway — Microservicio unificado.

Punto de entrada único para Telegram (webhook/long polling), clientes HTTP, Angular y escrituras a DuckDB.
Endpoints: /api/v1/agent/chat, /api/v1/db/write, homeostasis, system health.
"""

from __future__ import annotations

import asyncio
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
from functools import partial
from pathlib import Path
from typing import Any, Literal, Optional
from urllib import request as _url_request
from urllib.error import URLError

# Multi-Vault: mismo `db/` que el resto del monorepo aunque el cwd del proceso no sea la raíz.
_REPO_ROOT_FOR_DB = Path(__file__).resolve().parent.parent.parent
os.environ.setdefault("DUCKCLAW_REPO_ROOT", str(_REPO_ROOT_FOR_DB))

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
import redis.asyncio as redis

from core.sandbox_figure_b64 import decode_sandbox_figure_base64, decode_valid_sandbox_image_bytes
from core.telegram_media_upload import send_sandbox_chart_to_telegram_sync
from core.war_rooms import (
    is_war_room_tenant,
    wr_lookup_member_clearance,
    wr_members_count,
)

from core.chat_history import (
    gateway_chat_history_enabled,
    history_redis_key,
    normalize_history_list,
    normalize_history_item,
    redis_load_chat_history,
    redis_save_chat_history,
)
from core.models import ChatRequest
from duckclaw.utils.telegram_markdown_v2 import escape_telegram_html, llm_markdown_to_telegram_html, plain_subchunks_for_telegram_html
from duckclaw.vaults import resolve_active_vault, validate_user_db_path, vault_scope_id_for_tenant
from duckclaw.integrations.telegram.telegram_agent_token import (
    PM2_GATEWAY_APP_TO_WORKER_ID,
    resolve_telegram_token_for_worker_id,
    telegram_token_from_pm2_env_dict,
)
from duckclaw.gateway_db import (
    GATEWAY_DB_ENV_KEYS,
    get_gateway_db_path,
    raw_gateway_db_path_from_mapping,
    resolve_env_duckdb_path,
)

# Cargar .env desde repo root
_repo_root = Path(__file__).resolve().parent.parent.parent
for _base in (_repo_root, Path.cwd()):
    _env = _base / ".env"
    if _env.is_file():
        for _line in _env.read_text(encoding="utf-8").splitlines():
            _line = _line.strip()
            if _line and not _line.startswith("#") and "=" in _line:
                _k, _, _v = _line.partition("=")
                _ks = _k.strip()
                if not _ks:
                    continue
                _vs = _v.strip().strip("'\"")
                # Esta clave controla hilos en graph_server: debe ganar el .env del repo
                # aunque el proceso traiga un valor vacío heredado del entorno.
                if _ks == "DUCKCLAW_CHAT_PARALLEL_INVOCATIONS":
                    os.environ[_ks] = _vs
                # Tavily: sin clave la tool no se registra o falla en backend; el .env del repo
                # debe poder fijarla aunque PM2 herede un valor vacío.
                elif _ks == "TAVILY_API_KEY" and _vs:
                    os.environ[_ks] = _vs
                else:
                    os.environ.setdefault(_ks, _vs)
        break


def _apply_db_path_from_api_gateways_pm2() -> tuple[bool, str | None]:
    """
    Varias apps PM2 comparten el mismo .env. Volcar al proceso las claves ``DUCKCLAW_*_DB_PATH``
    y ``DUCKDB_PATH`` del bloque ``config/api_gateways_pm2.json`` según
    ``DUCKCLAW_PM2_PROCESS_NAME`` o ``--port`` (uvicorn).

    También aplica `TELEGRAM_BOT_TOKEN` desde ese mismo bloque `env` si viene definido y no vacío:
    así BI-Analyst-Gateway puede usar el bot de BI aunque el .env global traiga el token de Finanz.
    Se ejecuta después de cargar .env, así este valor **sustituye** al de setdefault.

    Returns:
        (telegram_token_from_json, matched_app_name) — nombre PM2 del bloque elegido (p. ej.
        ``BI-Analyst-Gateway``), útil si ``DUCKCLAW_PM2_PROCESS_NAME`` no está en el entorno
        (uvicorn directo por puerto).
    """
    cfg = _repo_root / "config" / "api_gateways_pm2.json"
    if not cfg.is_file():
        os.environ.pop("DUCKCLAW_PM2_MATCHED_APP_NAME", None)
        return False, None
    try:
        raw = json.loads(cfg.read_text(encoding="utf-8"))
        apps = raw.get("apps") if isinstance(raw, dict) else None
        if not isinstance(apps, list):
            os.environ.pop("DUCKCLAW_PM2_MATCHED_APP_NAME", None)
            return False, None
    except Exception:
        os.environ.pop("DUCKCLAW_PM2_MATCHED_APP_NAME", None)
        return False, None

    proc_name = (os.environ.get("DUCKCLAW_PM2_PROCESS_NAME") or "").strip()
    chosen: dict | None = None
    if proc_name:
        for a in apps:
            if isinstance(a, dict) and (a.get("name") or "").strip() == proc_name:
                chosen = a
                break
    if chosen is None:
        port: int | None = None
        try:
            argv = sys.argv
            for i, x in enumerate(argv):
                if x == "--port" and i + 1 < len(argv):
                    port = int(argv[i + 1])
                    break
        except (ValueError, IndexError):
            port = None
        if port is not None:
            matches = [
                a for a in apps
                if isinstance(a, dict) and int(a.get("port") or 0) == port
            ]
            if len(matches) == 1:
                chosen = matches[0]
    if chosen is None:
        os.environ.pop("DUCKCLAW_PM2_MATCHED_APP_NAME", None)
        return False, None
    matched_name = (chosen.get("name") or "").strip() or None
    if matched_name:
        os.environ["DUCKCLAW_PM2_MATCHED_APP_NAME"] = matched_name
    else:
        os.environ.pop("DUCKCLAW_PM2_MATCHED_APP_NAME", None)
    env = chosen.get("env") if isinstance(chosen.get("env"), dict) else {}
    for key in GATEWAY_DB_ENV_KEYS:
        raw_v = str(env.get(key) or "").strip()
        if raw_v:
            os.environ[key] = resolve_env_duckdb_path(raw_v)
    legacy = str(env.get("DUCKCLAW_DB_PATH") or "").strip()
    if legacy and not any(str(env.get(k) or "").strip() for k in (
        "DUCKCLAW_FINANZ_DB_PATH",
        "DUCKCLAW_JOB_HUNTER_DB_PATH",
        "DUCKCLAW_SIATA_DB_PATH",
    )):
        os.environ.setdefault("DUCKCLAW_FINANZ_DB_PATH", resolve_env_duckdb_path(legacy))
    if not any(os.environ.get(k) for k in GATEWAY_DB_ENV_KEYS):
        dbp = raw_gateway_db_path_from_mapping(env)
        if dbp:
            os.environ["DUCKCLAW_FINANZ_DB_PATH"] = resolve_env_duckdb_path(dbp)
    _matched_app = (matched_name or "").strip()
    _wid = PM2_GATEWAY_APP_TO_WORKER_ID.get(_matched_app, "")
    tok = (
        telegram_token_from_pm2_env_dict(env, _wid)
        if _wid
        else (str(env.get("TELEGRAM_BOT_TOKEN") or "")).strip()
    )
    if tok:
        os.environ["TELEGRAM_BOT_TOKEN"] = tok
        return True, matched_name
    return False, matched_name


def _apply_telegram_token_per_gateway_env(*, matched_pm2_app_name: str | None) -> None:
    """
    Si el bloque PM2 no fijó token: resuelve desde .env con
    ``TELEGRAM_<ID_AGENT>_TOKEN`` (estándar) o nombres legados.

    Ver: ``duckclaw.integrations.telegram.telegram_agent_token``.
    """
    proc = (
        (os.environ.get("DUCKCLAW_PM2_PROCESS_NAME") or "").strip()
        or (matched_pm2_app_name or "").strip()
    )
    wid = PM2_GATEWAY_APP_TO_WORKER_ID.get(proc)
    if not wid:
        return
    alt = resolve_telegram_token_for_worker_id(wid)
    if alt:
        os.environ["TELEGRAM_BOT_TOKEN"] = alt


_telegram_token_from_pm2_json, _matched_pm2_app_name = _apply_db_path_from_api_gateways_pm2()
if not _telegram_token_from_pm2_json:
    _apply_telegram_token_per_gateway_env(matched_pm2_app_name=_matched_pm2_app_name)


def _effective_telegram_bot_token() -> str:
    """Token Bot API para este proceso (tras overrides PM2 + per-gateway + ContextVar multiplex)."""
    from duckclaw.integrations.telegram import effective_telegram_bot_token_outbound

    return effective_telegram_bot_token_outbound()


from duckclaw.pm2_gateway_db import dedicated_gateway_db_path_resolved


def _dedicated_gateway_vault_db_path() -> str | None:
    """
    Si este proceso es un gateway listado en api_gateways_pm2.json con rutas multiplex,
    esa DuckDB sustituye al vault activo del usuario (fly commands, manager, workers).
    """
    return dedicated_gateway_db_path_resolved()

try:
    from core.config import settings
except ImportError:
    class _Settings:
        PROJECT_NAME = "DuckClaw API Gateway"
        VERSION = "0.1.0"
        REDIS_URL = "redis://localhost:6379/0"

    settings = _Settings()

# Logs estructurados (Observabilidad 2.0)
from duckclaw.utils.logger import (
    configure_structured_logging,
    format_chat_id_for_terminal,
    get_obs_logger,
    log_err,
    log_req,
    log_res,
    reset_log_context,
    set_log_context,
)

_log_level_name = (os.environ.get("DUCKCLAW_LOG_LEVEL") or "INFO").strip().upper()
_log_level = getattr(logging, _log_level_name, logging.INFO)
configure_structured_logging(level=_log_level)
_gateway_log = logging.getLogger("duckclaw.gateway")
_obs_log = get_obs_logger()
_gateway_log.info(
    "Gateway startup: gateway_db_path=%s DUCKCLAW_PM2_MATCHED_APP_NAME=%s "
    "DUCKCLAW_WAR_ROOM_ACL_DB_PATH=%s | diagnóstico WR: pm2 logs … --lines 300 "
    "y grep telegram_inbound_early war_room_gate DROP_NO_MENTION rate_limited",
    get_gateway_db_path() or "(unset)",
    (os.environ.get("DUCKCLAW_PM2_MATCHED_APP_NAME") or "").strip() or "(unset)",
    (os.environ.get("DUCKCLAW_WAR_ROOM_ACL_DB_PATH") or "").strip() or "(unset)",
)

def _normalize_local_artifacts_to_db() -> None:
    """Mueve artefactos locales conocidos a `db/` si aparecen en la raíz."""
    try:
        repo_root = Path(__file__).resolve().parent.parent.parent
        db_dir = repo_root / "db"
        db_dir.mkdir(parents=True, exist_ok=True)
        for filename in ("SELECT", "dump.rdb"):
            src = repo_root / filename
            dst = db_dir / filename
            if src.exists():
                try:
                    if dst.exists():
                        src.unlink(missing_ok=True)
                    else:
                        src.replace(dst)
                except Exception:
                    pass
    except Exception:
        pass


def _langsmith_auth_log(*, auth_status: str, user_id: str, tenant_id: str) -> None:
    """
    Opcional: un run por request en LangSmith (Telegram Guard) satura el dashboard.

    Por defecto **no** se envía nada a LangSmith. Activar solo si hace falta depuración:
    ``DUCKCLAW_LANGSMITH_LOG_TELEGRAM_GUARD=true``

    La auditoría de seguridad sigue en logs estructurados del gateway (PM2) cuando corresponda.
    """
    try:
        if os.environ.get("DUCKCLAW_LANGSMITH_LOG_TELEGRAM_GUARD", "").strip().lower() not in (
            "1",
            "true",
            "yes",
        ):
            return
        api_key = os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY")
        if not api_key:
            return
        if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() not in ("true", "1"):
            return

        from langsmith import Client  # noqa: PLC0415

        from duckclaw.utils.langsmith_trace import create_completed_langsmith_run

        client = Client(api_key=api_key)
        tag = f"auth_status: {auth_status}"
        env_tag = os.getenv("DUCKCLAW_ENV", "dev")
        create_completed_langsmith_run(
            client,
            name="TelegramGuard",
            run_type="chain",
            inputs={"user_id": str(user_id), "tenant_id": str(tenant_id)},
            outputs={"auth_status": auth_status},
            tags=[tag, "telegram_guard", f"env:{env_tag}", f"tenant:{tenant_id}"],
        )
    except Exception:
        # Auditoría best-effort: nunca rompas el flujo de seguridad.
        pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = redis.from_url(str(settings.REDIS_URL), decode_responses=True)
    _normalize_local_artifacts_to_db()
    # Forzar que Redis persista dump.rdb dentro de db/ (best-effort).
    try:
        repo_root = Path(__file__).resolve().parent.parent.parent
        redis_dir = str((repo_root / "db").resolve())
        await app.state.redis.config_set("dir", redis_dir)
        await app.state.redis.config_set("dbfilename", "dump.rdb")
    except Exception:
        pass
    # DDL en runtime desactivado: ejecutar scripts/bootstrap_dbs.py y ensure_registry antes de PM2.
    app.state.telegram_mcp = None
    try:
        from duckclaw.forge.skills.telegram_mcp_bridge import (
            infer_repo_root,
            start_telegram_mcp_gateway_session,
        )

        _mcp_repo = infer_repo_root()
        _mcp_sess = await start_telegram_mcp_gateway_session(_mcp_repo)
        if _mcp_sess is not None:
            app.state.telegram_mcp = _mcp_sess
            _gateway_log.info("Telegram MCP: sesión stdio activa para egress")
    except Exception as exc:  # noqa: BLE001
        _gateway_log.warning("Telegram MCP: no se pudo iniciar (se usa Bot API directa): %s", exc)

    yield

    _tg_mcp = getattr(app.state, "telegram_mcp", None)
    if _tg_mcp is not None:
        try:
            await _tg_mcp.aclose()
        except Exception as exc:  # noqa: BLE001
            _gateway_log.warning("Telegram MCP: error al cerrar sesión: %s", exc)
        app.state.telegram_mcp = None

    await app.state.redis.aclose()


app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.VERSION,
    description="API unificada para Telegram, agentes y escrituras DuckDB.",
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


async def _observability_context_middleware(request: Request, call_next):
    """Inyecta tenant/worker/chat en contextvars para líneas de log (refinado en _invoke_chat)."""
    path = request.url.path or ""
    tenant = (request.headers.get("X-Tenant-Id") or "").strip() or "default"
    chat = (request.headers.get("X-Chat-Id") or "").strip() or "unknown"
    worker = "manager"
    m = re.search(r"/api/v1/agent/([^/]+)/chat", path)
    if m:
        worker = (m.group(1) or "manager").strip() or "manager"
    set_log_context(tenant_id=tenant, worker_id=worker, chat_id=chat)
    try:
        return await call_next(request)
    finally:
        reset_log_context()


app.middleware("http")(_observability_context_middleware)


async def _tailscale_auth_middleware(request: Request, call_next):
    auth_key = os.environ.get("DUCKCLAW_TAILSCALE_AUTH_KEY", "").strip()
    if not auth_key:
        return await call_next(request)
    path = request.url.path.rstrip("/") or "/"
    if path in ("/", "/health"):
        return await call_next(request)
    # Telegram Bot API no envía X-Tailscale-Auth-Key; webhook estándar y rutas path-multiplex.
    if path.startswith("/api/v1/telegram/"):
        return await call_next(request)
    header_key = request.headers.get("X-Tailscale-Auth-Key", "").strip()
    if header_key != auth_key:
        return JSONResponse(
            status_code=401,
            content={"detail": "X-Tailscale-Auth-Key inválida o faltante"},
        )
    return await call_next(request)


app.middleware("http")(_tailscale_auth_middleware)


# ── Locks por chat (concurrencia por grupo) ────────────────────────────────────

@asynccontextmanager
async def _chat_lock(chat_id: str):
    """
    Mutex por chat_id usando Redis (si está disponible).

    - Clave: lock:chat:{chat_id}
    - timeout: evita locks huérfanos si el proceso muere durante la ejecución.
    - blocking_timeout: tiempo máximo esperando el lock antes de soltar y continuar.
    """
    redis_client = getattr(app.state, "redis", None)
    if redis_client is None:
        # Sin Redis configurado: no aplicar mutex, pero no romper el flujo.
        yield
        return
    lock_key = f"lock:chat:{chat_id}"
    lock = redis_client.lock(lock_key, timeout=10, blocking_timeout=15)
    acquired = False
    try:
        acquired = await lock.acquire()
        yield
    finally:
        if acquired:
            try:
                await lock.release()
            except Exception:
                # No romper si no se puede liberar; expirará por timeout.
                pass


def _chat_parallel_invocations_enabled() -> bool:
    """
    Si True, no se serializa por chat_id: varios POST concurrentes (p. ej. Telegram)
    pueden ejecutar el grafo a la vez; «BI-Analyst N» es el índice entre instancias
    activas del mismo worker en ese chat (1 si eres el único en curso, 2 si hay dos, …).
    Riesgo: orden del historial Redis y estado /tasks pueden intercalarse; activar solo si lo necesitas.
    """
    return (os.environ.get("DUCKCLAW_CHAT_PARALLEL_INVOCATIONS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


@asynccontextmanager
async def _maybe_chat_lock(chat_id: str):
    if _chat_parallel_invocations_enabled():
        yield
        return
    async with _chat_lock(chat_id):
        yield


@asynccontextmanager
async def _maybe_chat_lock_for_request(chat_id: str, skip_session_lock: bool):
    """Evita lock de sesión para tareas internas (p. ej. SUMMARIZE_NEW_CONTEXT)."""
    if skip_session_lock:
        yield
        return
    async with _maybe_chat_lock(chat_id):
        yield


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
async def agent_history(
    request: Request,
    worker_id: str,
    session_id: str | None = None,
    chat_id: str | None = None,
    tenant_id: str | None = None,
):
    """
    Historial persistido en Redis (mismas claves que ``POST .../chat`` cuando no se envía ``history`` en el body).

    Usar el mismo ``session_id`` / ``chat_id`` que en el chat y el mismo tenant (query ``tenant_id``,
    cabecera ``X-Tenant-Id``, o el default efectivo del proceso).
    """
    redis_client = getattr(request.app.state, "redis", None)
    sid = (
        (session_id or "").strip()
        or (chat_id or "").strip()
        or (request.headers.get("X-Chat-Id") or "").strip()
        or (request.headers.get("X-Session-Id") or "").strip()
        or "default"
    )
    tid_src = (tenant_id or "").strip() or (request.headers.get("X-Tenant-Id") or "").strip() or None
    tid = _effective_tenant_id(tid_src)
    hist = await redis_load_chat_history(redis_client, tid, sid)
    from core.leila_output_guard import is_leila_store_tenant, scrub_leila_history_assistant_messages

    if is_leila_store_tenant(tid):
        hist = scrub_leila_history_assistant_messages(hist)
    out: dict[str, Any] = {
        "history": hist,
        "worker_id": worker_id,
        "tenant_id": tid,
        "session_id": sid,
    }
    if (os.environ.get("DUCKCLAW_GATEWAY_HISTORY_DEBUG") or "").strip().lower() in ("1", "true", "yes"):
        out["redis_key"] = history_redis_key(tid, sid)
        out["redis_connected"] = redis_client is not None
        out["gateway_chat_history_enabled"] = gateway_chat_history_enabled()
    return out


def _resolve_chat_session_id(body: ChatRequest, req: Request) -> tuple[str, str]:
    """
    Identificador de hilo para estado por chat (sandbox, /team, auditoría).

    Orden: cuerpo JSON (chat_id y alias Pydantic) → query ?chat_id= / ?session_id=
    → cabeceras X-Chat-Id, X-Session-Id, X-Duckclaw-Chat-Id.
    """
    cid = (body.chat_id or "").strip()
    if cid:
        return cid, "body.chat_id"
    for key in ("chat_id", "session_id", "thread_id", "chatId"):
        raw = req.query_params.get(key)
        if raw and str(raw).strip():
            return str(raw).strip(), f"query.{key}"
    for header in ("X-Chat-Id", "X-Session-Id", "X-Duckclaw-Chat-Id"):
        raw = req.headers.get(header)
        if raw and str(raw).strip():
            return str(raw).strip(), f"header.{header}"
    return "default", "default"


def _escape_sql_literal(v: Any, max_len: int = 256) -> str:
    """
    Escape simple SQL string literals for DuckDB when we don't use parameterized queries.
    """
    s = "" if v is None else str(v)
    return s.replace("'", "''")[:max_len]


async def _lookup_whitelist_role(redis_client: Any, db: Any, tenant_id: str, user_id: str) -> Optional[str]:
    """
    Telegram Guard whitelist lookup with Redis cache (TTL=1h) + DuckDB source of truth.
    """
    key = f"whitelist:{str(tenant_id or '').strip().lower()}:{user_id}"
    if redis_client is not None:
        try:
            cached = await redis_client.get(key)
            if cached:
                return str(cached).strip() or None
        except Exception:
            pass

    tid = _escape_sql_literal(tenant_id, max_len=128)
    uid = _escape_sql_literal(user_id, max_len=128)
    def _ensure_authorized_users_table() -> None:
        # Best-effort: usa el mismo `db` en el que estamos para evitar lock.
        if getattr(db, "_war_room_acl_readonly", False):
            return
        try:
            db.execute(_AUTHORIZED_USERS_TABLE_DDL)
        except Exception:
            # No rompemos; el SELECT de abajo dará None.
            return

    try:
        raw = db.query(
            f"SELECT role FROM main.authorized_users "
            f"WHERE lower(tenant_id)=lower('{tid}') AND user_id='{uid}' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            role = (rows[0].get("role") or "").strip()
            if role:
                if redis_client is not None:
                    try:
                        await redis_client.set(key, role, ex=3600)
                    except Exception:
                        pass
                return role
    except Exception:
        # Si la tabla no existe todavía, crearla y reintentar una vez.
        _ensure_authorized_users_table()
        try:
            raw = db.query(
                f"SELECT role FROM main.authorized_users "
                f"WHERE lower(tenant_id)=lower('{tid}') AND user_id='{uid}' LIMIT 1"
            )
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
            if rows and isinstance(rows[0], dict):
                role = (rows[0].get("role") or "").strip()
                if role:
                    if redis_client is not None:
                        try:
                            await redis_client.set(key, role, ex=3600)
                        except Exception:
                            pass
                    return role
        except Exception:
            pass
    return None


async def _lookup_wr_clearance(redis_client: Any, db: Any, tenant_id: str, user_id: str) -> Optional[str]:
    key = f"wr_clearance:{str(tenant_id or '').strip().lower()}:{user_id}"
    if redis_client is not None:
        try:
            cached = await redis_client.get(key)
            if cached:
                return str(cached).strip() or None
        except Exception:
            pass
    clearance = ""
    try:
        clearance = wr_lookup_member_clearance(db, tenant_id, user_id)
    except Exception:
        clearance = ""
    if clearance and redis_client is not None:
        try:
            await redis_client.set(key, clearance, ex=300)
        except Exception:
            pass
    return clearance or None


def _send_security_alert_to_admin(user_id: str, tenant_id: str) -> None:
    """
    Alert opcional al admin: Bot API nativa si hay token; si no, webhook n8n (best-effort).
    """
    admin_chat_id = (os.getenv("DUCKCLAW_ADMIN_CHAT_ID") or "").strip()
    plain = (
        f"🚨 Alerta de Seguridad: El usuario {user_id} ha intentado acceder 3 veces "
        f"sin autorización al tenant {tenant_id}."
    )
    if not admin_chat_id:
        _gateway_log.warning("Telegram Guard: DUCKCLAW_ADMIN_CHAT_ID vacío; no hay alerta al admin")
        return

    token = _effective_telegram_bot_token()
    if token:
        try:
            from duckclaw.integrations.telegram.telegram_outbound_sync import send_bot_message_sync

            if send_bot_message_sync(
                bot_token=token,
                chat_id=str(admin_chat_id),
                text=escape_telegram_html(plain),
                parse_mode="HTML",
                timeout_sec=15.0,
                log=_gateway_log,
            ):
                _gateway_log.info("Telegram Guard: alerta admin enviada vía Bot API nativa")
                return
        except Exception as exc:  # noqa: BLE001
            _gateway_log.warning("Telegram Guard: falló alerta nativa, se intenta webhook: %s", exc)

    if (os.getenv("DUCKCLAW_TELEGRAM_OUTBOUND_VIA") or "").strip().lower() != "n8n":
        _gateway_log.warning(
            "Telegram Guard: alerta admin no usa n8n (DUCKCLAW_TELEGRAM_OUTBOUND_VIA!=n8n)",
        )
        return

    webhook_url = (os.getenv("N8N_OUTBOUND_WEBHOOK_URL") or "").strip()
    auth_key = (os.getenv("N8N_AUTH_KEY") or getattr(settings, "N8N_AUTH_KEY", "") or "").strip()
    if not webhook_url:
        _gateway_log.warning(
            "Telegram Guard: no hay token Bot API ni webhook n8n configurado; alerta no enviada",
        )
        return
    headers: dict[str, Any] = {"Content-Type": "application/json"}
    if auth_key:
        headers["X-DuckClaw-Secret"] = auth_key
    payload = {
        "chat_id": str(admin_chat_id),
        "text": escape_telegram_html(plain),
        "parse_mode": "HTML",
    }
    data = json.dumps(payload).encode("utf-8")
    req = _url_request.Request(webhook_url, data=data, headers=headers, method="POST")
    try:
        with _url_request.urlopen(req, timeout=10) as resp:
            _ = resp.read()
        _gateway_log.info("Telegram Guard: alerta admin enviada vía webhook")
    except URLError as exc:
        _gateway_log.warning("Telegram Guard: error enviando alerta webhook: %s", exc)
    except Exception as exc:  # noqa: BLE001
        _gateway_log.warning("Telegram Guard: error enviando alerta webhook (unknown): %s", exc)


# Telegram sendMessage: máx. 4096 caracteres (https://core.telegram.org/bots/api#sendmessage).
_TELEGRAM_SENDMESSAGE_CHAR_LIMIT = 4096
# Trozos de texto plano; margen conservador para no superar 4096 tras escapar HTML.
_DEFAULT_TELEGRAM_REPLY_PLAIN_CHUNK = 2000
def _telegram_reply_plain_chunk_size() -> int:
    raw = (os.environ.get("DUCKCLAW_TELEGRAM_REPLY_CHUNK_PLAIN") or "").strip()
    if raw:
        try:
            return max(256, min(int(raw), _TELEGRAM_SENDMESSAGE_CHAR_LIMIT - 200))
        except ValueError:
            pass
    return _DEFAULT_TELEGRAM_REPLY_PLAIN_CHUNK


def _split_plain_text_for_telegram_reply(text: str, max_chunk: int) -> list[str]:
    """Parte texto plano; cada parte se escapa aparte para n8n → Telegram (límite 4096)."""
    if max_chunk < 64:
        max_chunk = 64
    t = text or ""
    if not t:
        return [""]
    out: list[str] = []
    i = 0
    n = len(t)
    while i < n:
        if n - i <= max_chunk:
            out.append(t[i:n])
            break
        end = i + max_chunk
        window = t[i:end]
        nl = window.rfind("\n")
        if nl > 0:
            end = i + nl + 1
        out.append(t[i:end])
        i = end
    return out


def _plain_subchunks_for_telegram_budget(plain: str, safe_fn: Any) -> list[str]:
    """Subdivide texto plano hasta que ``safe_fn`` (p. ej. escape HTML) no supere el límite de Telegram."""
    if not plain:
        return []
    cap = _TELEGRAM_SENDMESSAGE_CHAR_LIMIT - 32
    if len(safe_fn(plain)) <= cap:
        return [plain]
    if len(plain) <= 1:
        return [plain]
    mid = len(plain) // 2
    return _plain_subchunks_for_telegram_budget(plain[:mid], safe_fn) + _plain_subchunks_for_telegram_budget(
        plain[mid:], safe_fn
    )


def _strip_lines_mentioning_workspace_output(text: str) -> str:
    """Quita líneas que citan rutas del sandbox (/workspace/output/...) para no confundir al usuario en Telegram."""
    if not text or "/workspace/output/" not in text:
        return text
    lines = (text or "").splitlines()
    kept = [ln for ln in lines if "/workspace/output/" not in ln]
    out = "\n".join(kept).strip()
    return out if out else text


def _webhook_outbound_chat_reply_sync(*, chat_id: str, user_id: str, text: str) -> None:
    """POST al webhook de salida n8n solo si ``DUCKCLAW_TELEGRAM_OUTBOUND_VIA=n8n`` (legado)."""
    if (os.getenv("DUCKCLAW_TELEGRAM_OUTBOUND_VIA") or "").strip().lower() != "n8n":
        return
    url = (os.getenv("N8N_OUTBOUND_WEBHOOK_URL") or "").strip()
    if not url:
        _gateway_log.warning(
            "outbound webhook n8n: N8N_OUTBOUND_WEBHOOK_URL no está definido; no se reenvía a Telegram.",
        )
        return
    cid = str(chat_id or "").strip()
    uid = str(user_id or "").strip() or cid
    raw = (text or "").strip()
    if not cid or not raw:
        return
    auth_key = (os.getenv("N8N_AUTH_KEY") or getattr(settings, "N8N_AUTH_KEY", "") or "").strip()
    headers: dict[str, Any] = {"Content-Type": "application/json"}
    if auth_key:
        headers["X-DuckClaw-Secret"] = auth_key

    chunks = plain_subchunks_for_telegram_html(raw)
    if not chunks:
        chunks = [raw]

    for idx, part in enumerate(chunks):
        prefix = f"[{idx + 1}/{len(chunks)}]\n" if len(chunks) > 1 else ""
        payload = {
            "chat_id": cid,
            "user_id": uid,
            "text": llm_markdown_to_telegram_html(prefix + part),
            "parse_mode": "HTML",
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = _url_request.Request(url, data=data, headers=headers, method="POST")
        try:
            with _url_request.urlopen(req, timeout=30) as resp:
                _ = resp.read()
        except URLError as exc:
            _gateway_log.warning(
                "outbound fallback: error POST parte %s/%s chat_id=%s: %s",
                idx + 1,
                len(chunks),
                cid,
                exc,
            )
        except Exception as exc:  # noqa: BLE001
            _gateway_log.warning(
                "outbound fallback: error desconocido parte %s/%s: %s",
                idx + 1,
                len(chunks),
                exc,
            )


def _outbound_deliver_chat_text_sync(
    *,
    chat_id: str,
    user_id: str,
    text: str,
    telegram_mcp: Any = None,
    redis_url: str | None = None,
    tenant_id: str = "default",
) -> None:
    """
    Entrega texto largo al usuario: MCP (si hay sesión), luego **Bot API nativa**,
    y solo al final webhook n8n si sigue configurado.
    """
    from duckclaw.graphs.chat_heartbeat import normalize_telegram_chat_id_for_outbound

    cid_raw = str(chat_id or "").strip()
    cid = normalize_telegram_chat_id_for_outbound(cid_raw) or cid_raw
    uid_raw = str(user_id or "").strip()
    uid = normalize_telegram_chat_id_for_outbound(uid_raw) or uid_raw or cid
    raw = (text or "").strip()
    if not cid or not raw:
        _gateway_log.warning(
            "outbound deliver: omitido (chat_id=%s text vacío=%s)",
            format_chat_id_for_terminal(cid or cid_raw),
            not bool(raw),
        )
        return

    if telegram_mcp is not None:
        try:
            from duckclaw.forge.skills.telegram_mcp_bridge import run_async, send_long_plain_via_mcp_chunks

            ok = run_async(
                send_long_plain_via_mcp_chunks(telegram_mcp.session, chat_id=str(cid), plain_text=raw),
            )
            if ok:
                _gateway_log.info(
                    "outbound deliver: MCP OK chat_id=%s len_text=%s",
                    format_chat_id_for_terminal(cid),
                    len(raw),
                )
                return
            _gateway_log.warning("outbound deliver: MCP no entregó todo; fallback nativo chat_id=%s", cid)
        except Exception as exc:  # noqa: BLE001
            _gateway_log.warning("outbound deliver: MCP error %s; fallback nativo", exc)
            try:
                from core.telegram_mcp_dlq import push_telegram_mcp_dlq_blocking

                push_telegram_mcp_dlq_blocking(
                    redis_url,
                    tenant_id=tenant_id,
                    chat_id=str(cid),
                    tool="telegram_send_message",
                    args={"chat_id": str(cid), "text": "<outbound disconnect fallback>"},
                    error=str(exc)[:2000],
                )
            except Exception:
                pass

    token = _effective_telegram_bot_token()
    if token:
        try:
            from duckclaw.integrations.telegram.telegram_outbound_sync import (
                send_long_plain_text_markdown_v2_chunks_sync,
            )

            _gateway_log.info(
                "outbound deliver: intento Bot API nativo chat_id=%s len_text=%s",
                format_chat_id_for_terminal(cid),
                len(raw),
            )
            n = send_long_plain_text_markdown_v2_chunks_sync(
                bot_token=token,
                chat_id=cid,
                plain_text=raw,
                log=_gateway_log,
            )
            if n > 0:
                _gateway_log.info(
                    "outbound deliver: Bot API OK chat_id=%s partes=%s",
                    format_chat_id_for_terminal(cid),
                    n,
                )
                return
            _gateway_log.warning(
                "outbound deliver: Bot API no envió partes; fallback webhook si existe (chat_id=%s)",
                format_chat_id_for_terminal(cid),
            )
        except Exception as exc:  # noqa: BLE001
            _gateway_log.warning(
                "outbound deliver: error Bot API chat_id=%s: %s; fallback webhook si existe",
                format_chat_id_for_terminal(cid),
                exc,
            )

    _webhook_outbound_chat_reply_sync(chat_id=cid, user_id=uid, text=raw)


async def _authorize_or_reject(
    *,
    tenant_id: str,
    user_id: str,
    is_owner: bool,
    telegram_guard_acl_db_path: str | None = None,
) -> None:
    """
    Raises HTTPException(403) for unauthorized access.
    Also increments unauthorized attempts and triggers admin alert after 3 attempts.

    telegram_guard_acl_db_path:
        Si el webhook forzó una bóveda distinta (p. ej. ruta legado ``/webhook/finanz`` con
        ``DUCKCLAW_FINANZ_DB_PATH``), la whitelist ``main.authorized_users`` se lee de esa DuckDB.
        Con un gateway aislado por bot, suele ser ``None`` y se usa la bóveda del proceso (multiplex / ``get_gateway_db_path``).
    """
    # Check 1 (Bypass): owner bypass no DB/Redis access.
    if is_owner:
        _langsmith_auth_log(auth_status="authorized", user_id=user_id, tenant_id=tenant_id)
        return

    redis_client = getattr(app.state, "redis", None)
    from core.gateway_acl_db import ReadOnlyGatewayAclDb, get_gateway_acl_duckdb, get_war_room_acl_duckdb

    _guard_acl = (telegram_guard_acl_db_path or "").strip()
    if _guard_acl:
        db: Any = ReadOnlyGatewayAclDb(str(Path(_guard_acl).expanduser().resolve()))
    else:
        db = get_gateway_acl_duckdb()[0]
    if is_war_room_tenant(tenant_id):
        wr_db = get_war_room_acl_duckdb()
        # Bootstrap WR: mientras no haya miembros registrados, no bloquear al primer operador.
        # El zero-trust estricto se activa automáticamente cuando wr_members > 0.
        try:
            if wr_members_count(wr_db, tenant_id) <= 0:
                _langsmith_auth_log(auth_status="authorized", user_id=user_id, tenant_id=tenant_id)
                return
        except Exception:
            pass
        role = await _lookup_wr_clearance(redis_client, wr_db, tenant_id, user_id)
    else:
        role = await _lookup_whitelist_role(redis_client, db, tenant_id, user_id)
    if role:
        _langsmith_auth_log(auth_status="authorized", user_id=user_id, tenant_id=tenant_id)
        return

    # PM2 visibility: ruido en logs, pero respuesta silenciosa en Telegram (n8n no debería reenviar un texto).
    _gateway_log.warning(
        "[SECURITY_ALERT] Unauthorized access attempt: user_id=%s tenant_id='%s'",
        format_chat_id_for_terminal(str(user_id or "unknown")),
        tenant_id,
    )
    _langsmith_auth_log(auth_status="unauthorized_attempt", user_id=user_id, tenant_id=tenant_id)

    # Contador para alertas del admin (best-effort).
    if redis_client is not None:
        attempts_key = f"authz_unauthorized_attempts:{tenant_id}:{user_id}"
        try:
            attempts = await redis_client.incr(attempts_key)
            # TTL 1h para evitar crecimiento infinito
            if attempts == 1:
                await redis_client.expire(attempts_key, 3600)
            if attempts >= 3 and attempts - 3 < 1:
                await asyncio.get_running_loop().run_in_executor(
                    None, _send_security_alert_to_admin, user_id, tenant_id
                )
        except Exception:
            pass

    raise HTTPException(
        status_code=403,
        detail="Acceso denegado. No tienes autorización para interactuar con este agente.",
    )


def _effective_tenant_id(request_tenant: str | None) -> str:
    """
    Tenant efectivo para Redis, whitelist y logs.

    Si el cliente envía un tenant explícito (query, header o body) distinto del placeholder
    ``default``, ese valor **gana**: debe coincidir con el GET ``/history`` y el POST ``/chat``
    (misma clave ``duckclaw:gateway:chat_hist:{tenant}:{session}``).

    Si solo llega ``default`` u omisión, aplica DUCKCLAW_GATEWAY_TENANT_ID, heurística PM2
    (Leila-Gateway, BI-Analyst-Gateway) / rutas de DuckDB (leiladb, bi_analyst), y por último
    ``default``.
    """
    rt = (request_tenant or "").strip()
    if rt and rt.lower() != "default":
        return rt

    override = (os.getenv("DUCKCLAW_GATEWAY_TENANT_ID") or "").strip()
    if override:
        return override
    pm2 = (os.getenv("DUCKCLAW_PM2_PROCESS_NAME") or "").strip()
    if pm2 == "Leila-Gateway":
        return "Leila Store"
    if pm2 == "BI-Analyst-Gateway":
        return "BI-Analyst"
    dbp_src = get_gateway_db_path()
    dbp = str(dbp_src or "").lower()
    if "leiladb" in dbp:
        return "Leila Store"
    if "bi_analyst" in dbp:
        return "BI-Analyst"
    if "siatadb" in dbp:
        return "SIATA"
    return rt or "default"


@app.post("/api/v1/agent/chat")
@app.post("/api/v1/agent/{worker_id}/chat")
async def agent_chat(
    http_request: Request,
    worker_id: Optional[str] = None,
    body: ChatRequest | None = None,
):
    """
    Endpoint de chat multi-usuario.

    Recibe ChatRequest (message, chat_id, user_id, username, chat_type, history, stream)
    y mapea chat_id → session_id interno.
    Si el JSON no trae chat_id, se usan query params o cabeceras (ver _resolve_chat_session_id).
    """
    if body is None:
        body = ChatRequest(message="", chat_id="default", user_id="system", username="system", chat_type="private")
    session_id, session_source = _resolve_chat_session_id(body, http_request)
    body_tid = (body.tenant_id or "").strip() or "default"
    hdr_tid = (http_request.headers.get("X-Tenant-Id") or "").strip()
    if body_tid.lower() == "default" and hdr_tid:
        body_tid = hdr_tid
    tenant_id = _effective_tenant_id(None if body_tid.lower() == "default" else body_tid)
    chat_ident = _chat_identity_label(session_id, body.username)
    set_log_context(tenant_id=tenant_id, worker_id="manager", chat_id=chat_ident)
    if session_source == "default" and not (body.chat_id or "").strip():
        _gateway_log.warning(
            "[session] chat_id/session_id ausente; usando 'default' (source=%s). "
            "El estado por chat (/sandbox) no coincidirá con otros mensajes. "
            "Añade chat_id al body, ?chat_id= en la URL, o cabecera X-Chat-Id. "
            "| chat=%s",
            session_source,
            format_chat_id_for_terminal(session_id),
        )
    else:
        _gateway_log.info(
            "[session] chat_id resolved: %s (source=%s)",
            format_chat_id_for_terminal(chat_ident),
            session_source,
        )
    redis_client = getattr(http_request.app.state, "redis", None)
    _tg_mcp = getattr(http_request.app.state, "telegram_mcp", None)
    result = await _invoke_chat(
        body,
        worker_id or "finanz",
        session_id=session_id,
        tenant_id=tenant_id,
        redis_client=redis_client,
        telegram_mcp=_tg_mcp,
    )
    # Cliente HTTP puede cerrar antes (timeout ~300s, proxy, etc.): reenvío best-effort
    # a Telegram por Bot API nativa o webhook n8n.
    _fb = (os.getenv("DUCKCLAW_CHAT_OUTBOUND_ON_CLIENT_DISCONNECT", "true").strip().lower())
    if _fb in ("1", "true", "yes", ""):
        try:
            if await http_request.is_disconnected():
                resp_text = (result.get("response") or "").strip() if isinstance(result, dict) else ""
                if resp_text:
                    uid_fb = (body.user_id or "").strip() or session_id
                    _gateway_log.info(
                        "outbound fallback: cliente desconectado; entrega async a Telegram "
                        "(nativo o n8n) chat_id=%s len=%s",
                        format_chat_id_for_terminal(session_id),
                        len(resp_text),
                    )
                    loop = asyncio.get_running_loop()
                    _mcp_snap = _tg_mcp
                    _redis_url = str(settings.REDIS_URL)
                    await loop.run_in_executor(
                        None,
                        lambda: _outbound_deliver_chat_text_sync(
                            chat_id=session_id,
                            user_id=uid_fb,
                            text=resp_text,
                            telegram_mcp=_mcp_snap,
                            redis_url=_redis_url,
                            tenant_id=tenant_id,
                        ),
                    )
        except Exception as exc:  # noqa: BLE001
            _gateway_log.warning("outbound fallback: no se pudo comprobar/enviar: %s", exc)
    return result


def _truncate_log(s: str, max_len: int = 200) -> str:
    s = (s or "").strip()
    return s if len(s) <= max_len else s[:max_len] + "..."


def _chat_identity_label(chat_id: str, username: str | None) -> str:
    cid = (chat_id or "").strip() or "unknown"
    uname = (username or "").strip()
    return f"@{uname} ({cid})" if uname else cid


def _strip_markdown_bold(s: str) -> str:
    """Quita asteriscos de negrita Markdown (**texto**) para respuesta más limpia."""
    if not s or not isinstance(s, str):
        return s
    return re.sub(r"\*\*([^*]*)\*\*", r"\1", s)


def clean_agent_response(response: str) -> str:
    """
    Limpia menús residuales del LLM para que la respuesta final sea concisa.
    Quita líneas sueltas (p. ej. \"¿Cuál es mi tarea?\") y bullets de menú finanz sin truncar el resto del texto.
    """
    if not response or not isinstance(response, str):
        return response
    text = str(response)
    text = re.sub(r"(?is)<\s*pre\b[^>]*>", "", text)
    text = re.sub(r"(?is)<\s*/\s*pre\s*>", "", text)
    # No usar ".*" con DOTALL tras frases cortas: el BI Analyst sigue con párrafos útiles
    # después de "¿Cuál es mi tarea?" y eso borraba todo el cuerpo (Telegram solo veía el header).
    line_patterns = [
        r"(?im)^\s*¿Cuál\s+es\s+mi\s+tarea\?\s*$",
        r"(?im)^\s*¿Qué\s+te\s+gustaría\s+hacer\s+ahora\?\s*$",
        r"(?im)^-\s*📊\s*Resumen\s+financiero.*$",
        r"(?im)^-\s*💰\s*Registrar\s+transacciones.*$",
    ]
    for pattern in line_patterns:
        text = re.sub(pattern, "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _beautify_bi_analyst_telegram(text: str) -> str:
    """Convierte encabezados tipo ## INSIGHT en líneas con emoji (mejor lectura en Telegram)."""
    if not text or not isinstance(text, str):
        return text
    t = text
    t = re.sub(r"(?im)^#+\s*\*?\*?INSIGHT:?\*?\*?\s*", "📌 INSIGHT — ", t)
    t = re.sub(r"(?im)^#+\s*\*?\*?CAUSA:?\*?\*?\s*", "\n🔍 CAUSA — ", t)
    t = re.sub(r"(?im)^#+\s*\*?\*?RECOMENDACIÓN:?\*?\*?\s*", "\n💡 RECOMENDACIÓN — ", t)
    t = re.sub(r"(?im)^#+\s*\*?\*?RECOMENDACION:?\*?\*?\s*", "\n💡 RECOMENDACIÓN — ", t)
    t = re.sub(r"(?m)^#+\s+", "", t)
    return re.sub(r"\n{3,}", "\n\n", t).strip()


def _strip_bi_false_chart_delivery_lines(text: str) -> str:
    """Quita cierres que afirman envío de gráfico (el modelo no puede saber si Telegram recibió la foto)."""
    if not text or not isinstance(text, str):
        return text
    lines = text.splitlines()
    drop_phrases = (
        "se ha enviado en el chat",
        "se envió en el chat",
        "enviado en el chat",
        "grafico con el analisis completo",
        "gráfico con el análisis completo",
    )
    kept: list[str] = []
    for ln in lines:
        low = ln.lower()
        if any(p in low for p in drop_phrases) and ("gráfico" in low or "grafico" in low):
            continue
        kept.append(ln)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(kept)).strip()


async def _invoke_chat(
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
):
    """
    Orquesta la llamada al grafo LangGraph a partir de un ChatRequest.

    - session_id: ya resuelto (body + query + headers); debe ser el mismo en todos los POST del hilo.
    - telegram_multipart_tail_delivery: ``native`` | ``n8n`` | None (inferido por env) para partes 2..N del mensaje.
    """
    message = (payload.message or "").strip()
    session_id = (session_id or "default").strip() or "default"
    tenant_id = _effective_tenant_id(tenant_id)
    # Campos opcionales: defaults resilientes
    chat_type = (payload.chat_type or "private").strip().lower() or "private"
    username = (payload.username or "Usuario").strip() or "Usuario"
    user_id = (payload.user_id or "").strip()
    # Telegram DM: n8n a veces manda solo chat_id; para el Guard, user_id == chat_id.
    if not user_id and chat_type == "private":
        user_id = (session_id or "").strip()
    vault_user_id = user_id or session_id
    vault_scope = vault_scope_id_for_tenant(tenant_id)
    _, vault_db_path = resolve_active_vault(vault_user_id, vault_scope)
    _forced_v = (telegram_forced_vault_db_path or "").strip()
    _telegram_acl_for_guard: str | None = None
    if _forced_v:
        vault_db_path = resolve_env_duckdb_path(_forced_v)
        _telegram_acl_for_guard = vault_db_path
    else:
        _ded_vault = _dedicated_gateway_vault_db_path()
        if _ded_vault:
            vault_db_path = _ded_vault
    history = payload.history or []
    is_system_prompt = bool(payload.is_system_prompt or False)
    shared_db_path = (payload.shared_db_path or "").strip() or None
    history_for_model = normalize_history_list(list(history))
    if (
        not is_system_prompt
        and redis_client is not None
        and gateway_chat_history_enabled()
        and not history_for_model
    ):
        history_for_model = await redis_load_chat_history(redis_client, tenant_id, session_id)

    if not is_system_prompt:
        from core.leila_output_guard import is_leila_store_tenant, scrub_leila_history_assistant_messages

        if is_leila_store_tenant(tenant_id):
            history_for_model = scrub_leila_history_assistant_messages(history_for_model)

    # Observabilidad 2.1: fase orquestación HTTP → worker lógico "manager" (no el worker_id de ruta).
    chat_ident = _chat_identity_label(session_id, username)
    set_log_context(tenant_id=tenant_id, worker_id="manager", chat_id=chat_ident)
    log_req(_obs_log, "%s", _truncate_log(message), source="body")

    # Telegram Guard: autoriza antes de ejecutar comandos (/team, /sandbox, etc.)
    # y antes de invocar cualquier lógica LangGraph.
    owner_user_id = (os.getenv("DUCKCLAW_OWNER_ID") or os.getenv("DUCKCLAW_ADMIN_CHAT_ID") or "").strip()
    is_owner = bool(owner_user_id and user_id and str(user_id).strip() == str(owner_user_id).strip())
    if not is_system_prompt:
        await _authorize_or_reject(
            tenant_id=tenant_id,
            user_id=user_id,
            is_owner=is_owner,
            telegram_guard_acl_db_path=_telegram_acl_for_guard,
        )

    if not is_system_prompt and not is_owner:
        from core.gateway_acl_db import ReadOnlyGatewayAclDb, get_gateway_acl_duckdb
        from duckclaw.shared_db_grants import path_is_under_shared_tree, user_may_access_shared_path

        acl_db = (
            ReadOnlyGatewayAclDb(_telegram_acl_for_guard)
            if _telegram_acl_for_guard
            else get_gateway_acl_duckdb()[0]
        )
        _candidates = {s for s in ((shared_db_path or "").strip(), (os.getenv("DUCKCLAW_SHARED_DB_PATH") or "").strip()) if s}
        for candidate in _candidates:
            if not path_is_under_shared_tree(candidate):
                continue
            if not user_may_access_shared_path(
                acl_db,
                tenant_id=tenant_id,
                user_id=vault_user_id,
                shared_db_path=candidate,
            ):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Sin permiso para acceder a la base de datos compartida configurada.",
                )

    msg_stripped = (message or "").strip()
    # No invocar el grafo con mensaje vacío (evita plan vacío y respuesta "¿Cuál es mi tarea?")
    if not msg_stripped:
        return {
            "response": "No recibí ningún mensaje. Escribe tu consulta o comando (por ejemplo /tasks).",
            "session_id": session_id,
            "worker_id": worker_id,
            "elapsed_ms": 0,
        }
    try:
        from duckclaw.graphs.graph_server import ainvoke_manager_ephemeral
    except Exception as exc:
        _gateway_log.error(
            "graph init failed chat=%s: %s\n%s",
            format_chat_id_for_terminal(session_id),
            exc,
            traceback.format_exc(),
        )
        raise HTTPException(status_code=503, detail=f"Error inicializando el grafo: {exc}")

    # Concurrencia: por defecto un mensaje por chat_id (Redis lock). Opcional: paralelo (ver _maybe_chat_lock).
    # Fly (/team, /vault, /workers): si la bóveda es el mismo archivo que get_gateway_db_path(), usar motor
    # Python (mismo que GatewayDbEphemeralReadonly); si no, DuckClaw nativo en RW. Evita que /team --add
    # escriba vía C++ y /team lea vía duckdb Python sin ver las filas.
    _skip_lock = bool(getattr(payload, "skip_session_lock", None) or False)
    async with _maybe_chat_lock_for_request(session_id, _skip_lock):
        if msg_stripped.startswith("/"):
            cmd_reply: str | None = None
            fly_db = None
            try:
                from duckclaw import DuckClaw
                from duckclaw.graphs.on_the_fly_commands import handle_command, prepare_leila_fly_duckdb

                vpath = (vault_db_path or "").strip()
                Path(vpath).parent.mkdir(parents=True, exist_ok=True)
                _fly_engine: Literal["auto", "python"] = "auto"
                if vpath and vpath != ":memory:":
                    try:
                        if Path(vpath).resolve() == Path(get_gateway_db_path()).resolve():
                            _fly_engine = "python"
                    except OSError:
                        pass
                if (os.environ.get("DUCKCLAW_TEAM_WHITELIST_DEBUG") or "").strip().lower() in (
                    "1",
                    "true",
                    "yes",
                    "on",
                ):
                    try:
                        _gw_abs = str(Path(get_gateway_db_path()).resolve())
                        _v_abs = (
                            str(Path(vpath).resolve())
                            if vpath and vpath != ":memory:"
                            else (vpath or "")
                        )
                        _same = bool(
                            _v_abs
                            and _gw_abs
                            and Path(_v_abs).resolve() == Path(_gw_abs).resolve()
                        )
                        _gateway_log.info(
                            "fly_team_audit vault_resolved=%r gateway_resolved=%r same_file=%s fly_engine=%s",
                            _v_abs[-96:] if len(_v_abs) > 96 else _v_abs,
                            _gw_abs[-96:] if len(_gw_abs) > 96 else _gw_abs,
                            _same,
                            _fly_engine,
                        )
                    except OSError as _audit_exc:
                        _gateway_log.info("fly_team_audit path_compare_error=%s", _audit_exc)
                fly_db = DuckClaw(vpath, read_only=False, engine=_fly_engine)
                from duckclaw.graphs.graph_server import get_db as _fly_acl_db

                prepare_leila_fly_duckdb(
                    fly_db,
                    vpath,
                    user_id=vault_user_id,
                    tenant_id=tenant_id,
                    acl_db=_fly_acl_db(),
                )
                cmd_reply = handle_command(
                    fly_db,
                    session_id,
                    message,
                    requester_id=user_id,
                    tenant_id=tenant_id,
                    vault_user_id=vault_user_id,
                    username=username,
                )
            except Exception as exc:
                _gateway_log.error("fly command failed chat=%s: %s", format_chat_id_for_terminal(session_id), exc)
            finally:
                if fly_db is not None:
                    try:
                        fly_db.close()
                    except Exception:
                        pass
            if cmd_reply is not None:
                if _gateway_log.isEnabledFor(logging.DEBUG):
                    _gateway_log.debug(
                        "fly (backup) chat=%s: %s",
                        format_chat_id_for_terminal(session_id),
                        _truncate_log(cmd_reply),
                    )
                return {
                    "response": cmd_reply,
                    "session_id": session_id,
                    "worker_id": worker_id,
                    "elapsed_ms": 0,
                }

        try:
            from duckclaw.graphs.graph_server import _ensure_llm_config

            _ensure_llm_config()
        except Exception as exc:
            _gateway_log.error(
                "graph init failed chat=%s: %s\n%s",
                format_chat_id_for_terminal(session_id),
                exc,
                traceback.format_exc(),
            )
            raise HTTPException(status_code=503, detail=f"Error inicializando el grafo: {exc}")

        try:
            from duckclaw.graphs.activity import set_busy, set_idle
            set_busy(session_id, task=message)
        except Exception:
            pass
        t0 = time.monotonic()
        try:
            result = await ainvoke_manager_ephemeral(
                message,
                history_for_model,
                session_id,
                tenant_id=tenant_id,
                user_id=vault_user_id,
                username=username,
                vault_db_path=vault_db_path,
                shared_db_path=shared_db_path,
                is_system_prompt=is_system_prompt,
                outbound_telegram_bot_token=(outbound_telegram_bot_token or "").strip() or None,
            )
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
            log_err(_obs_log, "agent_chat failed: %s", exc)
            _gateway_log.error(
                "agent_chat failed chat=%s: %s\n%s",
                format_chat_id_for_terminal(session_id),
                exc,
                traceback.format_exc(),
            )
            raise HTTPException(status_code=500, detail=str(exc))

        try:
            from duckclaw.graphs.activity import set_idle
            set_idle(session_id)
        except Exception:
            pass
    reply_text = result.get("reply", "") if isinstance(result, dict) else (result or "")
    # Tokens EOT del modelo (p. ej. Slayer/MLX: <|eot_id|>) no deben llegar a Telegram ni a logs.
    try:
        from duckclaw.integrations.llm_providers import sanitize_worker_reply_text

        reply_text = sanitize_worker_reply_text(reply_text or "")
    except Exception:
        pass
    # Evitar doble escape Telegram: historial/n8n a veces reinyecta texto ya escapado y el modelo lo copia.
    try:
        from duckclaw.graphs.on_the_fly_commands import unescape_telegram_markdown_v2_layers

        reply_text = unescape_telegram_markdown_v2_layers(reply_text or "")
    except Exception:
        pass
    # Reddit MCP: último filtro antes de Telegram/logs (delegación manager, caché de grafos, rutas sin set_reply).
    try:
        from duckclaw.utils.formatters import format_reddit_mcp_reply_if_applicable

        reply_text = format_reddit_mcp_reply_if_applicable(reply_text or "")
    except Exception:
        pass
    # Grafo manager devuelve assigned_worker_id; refinar contexto de log para [RES]
    effective_worker_id = result.get("assigned_worker_id", worker_id) if isinstance(result, dict) else worker_id
    set_log_context(
        tenant_id=tenant_id,
        worker_id=effective_worker_id or worker_id,
        chat_id=chat_ident,
    )
    usage = result.get("usage_tokens") if isinstance(result, dict) else None
    tok_extra = ""
    if isinstance(usage, dict) and usage:
        tok_extra = (
            f" | 🪙 Tokens: {usage.get('total_tokens', 0)} "
            f"[P:{usage.get('input_tokens', 0)}, C:{usage.get('output_tokens', 0)}]"
        )
    elapsed_ms = int((time.monotonic() - t0) * 1000)
    log_res(
        _obs_log,
        "%s (⏱️ Total: %.1fs%s)",
        _truncate_log(reply_text),
        elapsed_ms / 1000.0,
        tok_extra,
    )
    _gateway_log.info(
        "out(chat_id=%s): %s",
        format_chat_id_for_terminal(chat_ident, as_repr=True),
        _truncate_log(reply_text),
    )
    reply_text = _strip_markdown_bold(reply_text or "")
    # Filtro UX: eliminar menús residuales del LLM antes de devolver al cliente
    reply_text = clean_agent_response(reply_text or "")
    if (effective_worker_id or worker_id or "").strip() == "LeilaAssistant":
        from core.leila_output_guard import scrub_leila_contact_surface

        reply_text = scrub_leila_contact_surface(reply_text)
    if (effective_worker_id or worker_id or "").strip() == "BI-Analyst":
        reply_text = _beautify_bi_analyst_telegram(reply_text or "")
        reply_text = _strip_bi_false_chart_delivery_lines(reply_text or "")
    # Texto plano para Redis/trazas; _telegram_safe solo en la respuesta al cliente (evita \\ que crece cada turno).
    reply_plain_for_storage = reply_text
    chart_sent = False
    if not is_system_prompt and isinstance(result, dict):
        photo_b64 = (result.get("sandbox_photo_base64") or "").strip()
        if photo_b64:
            png_bytes = decode_valid_sandbox_image_bytes(photo_b64)
            if not png_bytes:
                raw_try = decode_sandbox_figure_base64(photo_b64)
                _gateway_log.warning(
                    "sandbox chart: base64 no produce PNG/JPEG válido (b64_len=%s, decoded_len=%s, mod4=%s)",
                    len(photo_b64),
                    len(raw_try),
                    len("".join(photo_b64.split())) % 4,
                )
            if png_bytes:
                token = _effective_telegram_bot_token()
                if telegram_mcp is not None:
                    try:
                        from core.telegram_mcp_dlq import push_telegram_mcp_dlq
                        from duckclaw.forge.skills.telegram_mcp_bridge import send_sandbox_photo_via_mcp

                        out = await send_sandbox_photo_via_mcp(
                            telegram_mcp.session,
                            chat_id=str(session_id),
                            image_bytes=png_bytes,
                        )
                        if out.get("ok"):
                            chart_sent = True
                            _gateway_log.info("sandbox chart: enviado vía MCP chat_id=%s", session_id)
                        else:
                            err = str(out.get("error", out))
                            _gateway_log.warning("sandbox chart: MCP falló (%s); intento Bot API", err[:500])
                            await push_telegram_mcp_dlq(
                                redis_client,
                                tenant_id=tenant_id,
                                chat_id=str(session_id),
                                tool="telegram_send_photo",
                                args={"chat_id": str(session_id), "photo_base64": "<omitted>"},
                                error=err[:2000],
                            )
                    except Exception as exc:  # noqa: BLE001
                        _gateway_log.warning("sandbox chart: excepción MCP (%s); intento Bot API", exc)
                        try:
                            from core.telegram_mcp_dlq import push_telegram_mcp_dlq

                            await push_telegram_mcp_dlq(
                                redis_client,
                                tenant_id=tenant_id,
                                chat_id=str(session_id),
                                tool="telegram_send_photo",
                                args={"chat_id": str(session_id)},
                                error=str(exc)[:2000],
                            )
                        except Exception:
                            pass
                if not chart_sent and token:
                    loop = asyncio.get_running_loop()
                    chart_sent = bool(
                        await loop.run_in_executor(
                            None,
                            lambda: send_sandbox_chart_to_telegram_sync(
                                bot_token=token,
                                chat_id=str(session_id),
                                image_bytes=png_bytes,
                            ),
                        )
                    )
                elif not chart_sent and not token:
                    _gateway_log.warning(
                        "sandbox chart: hay PNG del sandbox pero no hay token Bot API (TELEGRAM_BOT_TOKEN "
                        "o TELEGRAM_<ID_AGENT>_TOKEN en el bloque PM2 / .env, p. ej. TELEGRAM_BI_ANALYST_TOKEN); "
                        "define uno para este proceso."
                    )
    if chart_sent:
        reply_plain_for_storage = _strip_lines_mentioning_workspace_output(reply_plain_for_storage or "")
    try:
        if not result.get("_audit_done"):
            from duckclaw.graphs.on_the_fly_commands import append_task_audit, get_worker_id_for_chat
            from duckclaw.graphs.graph_server import get_db
            db = get_db()
            wid = get_worker_id_for_chat(db, session_id) or worker_id
            plan_title = result.get("plan_title") if isinstance(result, dict) else None
            append_task_audit(db, session_id, wid, message, "SUCCESS", elapsed_ms, plan_title=plan_title)
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
                session_id, message, reply_plain_for_storage or "",
                worker_id=effective_worker_id, elapsed_ms=elapsed_ms, status="SUCCESS",
                system_prompt=system_for_trace,
                messages=trace_messages,
            )
    except Exception:
        pass
    _telegram_response_parts_count = 1
    try:
        coarse = _split_plain_text_for_telegram_reply(
            reply_plain_for_storage or "",
            _telegram_reply_plain_chunk_size(),
        )
        plain_parts: list[str] = []
        for piece in coarse:
            plain_parts.extend(_plain_subchunks_for_telegram_budget(piece, llm_markdown_to_telegram_html))
        if not plain_parts:
            plain_parts = [""]
        _telegram_response_parts_count = len(plain_parts)
        reply_text = llm_markdown_to_telegram_html(plain_parts[0])
        tail_plain = "\n\n".join(plain_parts[1:]) if len(plain_parts) > 1 else ""
        if tail_plain.strip():
            try:
                from core.telegram_multipart_tail_dispatch_async import dispatch_telegram_multipart_tail_async

                async def _send_telegram_tail() -> None:
                    try:
                        await dispatch_telegram_multipart_tail_async(
                            tail_plain=tail_plain,
                            session_id=session_id,
                            user_id=(user_id or "").strip() or session_id,
                            telegram_multipart_tail_delivery=telegram_multipart_tail_delivery,
                            effective_telegram_bot_token=_effective_telegram_bot_token,
                            n8n_outbound_push_sync=_webhook_outbound_chat_reply_sync,
                            telegram_mcp=telegram_mcp,
                            redis_client=redis_client,
                            tenant_id=tenant_id,
                        )
                    except Exception as tail_exc:  # noqa: BLE001
                        _gateway_log.warning(
                            "telegram reply tail: envío falló (nativo/n8n): %s",
                            tail_exc,
                        )

                asyncio.create_task(_send_telegram_tail())
            except Exception as exc:  # noqa: BLE001
                _gateway_log.warning("telegram reply tail: no se pudo programar envío: %s", exc)
    except Exception:
        try:
            reply_text = llm_markdown_to_telegram_html(reply_plain_for_storage or "")
            cap = _TELEGRAM_SENDMESSAGE_CHAR_LIMIT - 16
            if len(reply_text) > cap:
                reply_text = reply_text[:cap] + "…"
        except Exception:
            pass
    if (
        not is_system_prompt
        and redis_client is not None
        and gateway_chat_history_enabled()
    ):
        if is_war_room_tenant(tenant_id):
            from core.gateway_acl_db import get_war_room_acl_duckdb

            wr_role = await _lookup_wr_clearance(redis_client, get_war_room_acl_duckdb(), tenant_id, user_id)
            if not wr_role:
                return {
                    "response": "Clearance Revoked.",
                    "session_id": session_id,
                    "worker_id": effective_worker_id or worker_id,
                    "elapsed_ms": elapsed_ms,
                }
        u = normalize_history_item({"role": "user", "content": message})
        a = normalize_history_item({"role": "assistant", "content": reply_plain_for_storage})
        if u and a:
            await redis_save_chat_history(
                redis_client,
                tenant_id,
                session_id,
                history_for_model + [u, a],
            )
    # ``response`` debe ser Markdown/texto plano: el webhook de Telegram y
    # ``_outbound_deliver_chat_text_sync`` aplican ``llm_markdown_to_telegram_html`` una sola vez.
    # Si aquí devolviéramos ``reply_text`` (ya HTML), la segunda pasada escapa ``<a>`` → el usuario ve
    # literales ``<a href="...">`` en el cliente.
    out_resp: dict[str, Any] = {
        "response": reply_plain_for_storage or "",
        "session_id": session_id,
        "worker_id": effective_worker_id or worker_id,
        "elapsed_ms": elapsed_ms,
    }
    if _telegram_response_parts_count > 1:
        out_resp["response_parts"] = _telegram_response_parts_count
    # Texto en JSON; PNG del sandbox lo envía el gateway por Bot API (sendPhoto).
    if (
        not is_system_prompt
        and isinstance(result, dict)
        and (result.get("sandbox_photo_base64") or "").strip()
    ):
        out_resp["sandbox_chart_delivered"] = chart_sent
    return out_resp


# ── Escrituras DuckDB (encolar en Redis) ──────────────────────────────────────

class WriteRequest(BaseModel):
    query: str = Field(..., description="Consulta SQL parametrizada")
    params: list = Field(default_factory=list, description="Parámetros para la consulta")
    tenant_id: str = Field(default="default", description="ID del tenant")
    user_id: str | None = Field(default=None, description="ID del usuario dueño de la bóveda")
    db_path: str | None = Field(default=None, description="Ruta DuckDB destino (bóveda activa)")


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
    user_id = (req.user_id or "").strip() or "default"
    db_path = (req.db_path or "").strip()
    tid = (req.tenant_id or "").strip() or None
    if db_path and not validate_user_db_path(user_id, db_path, tenant_id=tid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="db_path inválido para el usuario.",
        )
    if db_path:
        from core.gateway_acl_db import get_gateway_acl_duckdb
        from duckclaw.shared_db_grants import path_is_under_shared_tree, user_may_access_shared_path

        if path_is_under_shared_tree(db_path) and not user_may_access_shared_path(
            get_gateway_acl_duckdb()[0],
            tenant_id=str(tid or "default").strip() or "default",
            user_id=user_id,
            shared_db_path=db_path,
        ):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Sin permiso para escribir en esta base de datos compartida.",
            )
    if not db_path:
        _ded = _dedicated_gateway_vault_db_path()
        if _ded:
            db_path = _ded
        else:
            _t_eff = str(tid or "default").strip() or "default"
            _, db_path = resolve_active_vault(user_id, vault_scope_id_for_tenant(_t_eff))
    payload = {
        "task_id": task_id,
        "tenant_id": req.tenant_id,
        "user_id": user_id,
        "db_path": db_path,
        "query": req.query,
        "params": req.params,
    }
    try:
        await app.state.redis.lpush("duckdb_write_queue", json.dumps(payload))
        return EnqueueResponse(status="enqueued", task_id=task_id)
    except redis.RedisError as e:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Error conectando al broker de mensajes: {str(e)}",
        )


# ── Telegram inbound webhook (integración nativa) ────────────────────────────

try:
    from routers.telegram_inbound_webhook import build_telegram_inbound_webhook_router

    app.include_router(
        build_telegram_inbound_webhook_router(
            invoke_agent_chat=_invoke_chat,
            resolve_effective_telegram_bot_token=_effective_telegram_bot_token,
        )
    )
except ImportError:
    pass


# ── Quotes router (microservicio: routers en services/api-gateway) ───────────

try:
    from routers.quotes import router as quotes_router
    app.include_router(quotes_router)
except ImportError:
    pass
