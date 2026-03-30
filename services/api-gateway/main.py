# services/api-gateway/main.py
"""
DuckClaw API Gateway — Microservicio unificado.

Punto de entrada único para n8n, Telegram, Angular y escrituras a DuckDB.
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
from typing import Any, Optional
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

from core.chat_history import (
    gateway_chat_history_enabled,
    history_redis_key,
    normalize_history_list,
    normalize_history_item,
    redis_load_chat_history,
    redis_save_chat_history,
)
from core.models import ChatRequest
from duckclaw.utils.telegram_markdown_v2 import escape_telegram_markdown_v2
from duckclaw.vaults import ensure_registry as ensure_vault_registry
from duckclaw.vaults import resolve_active_vault, validate_user_db_path

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


def _apply_db_path_from_api_gateways_pm2() -> tuple[bool, str | None]:
    """
    Varias apps PM2 comparten el mismo .env; `setdefault` puede dejar DUCKCLAW_DB_PATH
    apuntando a finanzdb para todos. Forzar la ruta del bloque correcto en
    config/api_gateways_pm2.json según DUCKCLAW_PM2_PROCESS_NAME (PM2) o --port (uvicorn).

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
    dbp = (env.get("DUCKCLAW_DB_PATH") or "").strip()
    if not dbp:
        return False, matched_name
    pth = Path(dbp)
    if not pth.is_absolute():
        pth = (_repo_root / pth).resolve()
    else:
        pth = pth.resolve()
    os.environ["DUCKCLAW_DB_PATH"] = str(pth)
    tok = (env.get("TELEGRAM_BOT_TOKEN") or "").strip()
    if tok:
        os.environ["TELEGRAM_BOT_TOKEN"] = tok
        return True, matched_name
    return False, matched_name


def _apply_telegram_token_per_gateway_env(*, matched_pm2_app_name: str | None) -> None:
    """
    Fallback cuando el bloque PM2 no trae TELEGRAM_BOT_TOKEN: varias gateways comparten
    .env con un solo TELEGRAM_BOT_TOKEN (p. ej. Finanz) y sendPhoto iría al bot equivocado.

    - BI-Analyst-Gateway → TELEGRAM_BOT_TOKEN_BI_ANALYST
    - Leila-Gateway → TELEGRAM_BOT_TOKEN_LEILA
    - SIATA-Gateway → TELEGRAM_BOT_TOKEN_SIATA
    """
    proc = (
        (os.environ.get("DUCKCLAW_PM2_PROCESS_NAME") or "").strip()
        or (matched_pm2_app_name or "").strip()
    )
    namespaced = {
        "BI-Analyst-Gateway": "TELEGRAM_BOT_TOKEN_BI_ANALYST",
        "Leila-Gateway": "TELEGRAM_BOT_TOKEN_LEILA",
        "SIATA-Gateway": "TELEGRAM_BOT_TOKEN_SIATA",
    }
    var = namespaced.get(proc)
    if not var:
        return
    alt = (os.getenv(var) or "").strip()
    if alt:
        os.environ["TELEGRAM_BOT_TOKEN"] = alt


_telegram_token_from_pm2_json, _matched_pm2_app_name = _apply_db_path_from_api_gateways_pm2()
if not _telegram_token_from_pm2_json:
    _apply_telegram_token_per_gateway_env(matched_pm2_app_name=_matched_pm2_app_name)


def _effective_telegram_bot_token() -> str:
    """Token Bot API para este proceso (tras overrides PM2 + per-gateway)."""
    return (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()


from duckclaw.pm2_gateway_db import dedicated_gateway_db_path_resolved


def _dedicated_gateway_vault_db_path() -> str | None:
    """
    Si este proceso es un gateway listado en api_gateways_pm2.json con DUCKCLAW_DB_PATH,
    esa ruta sustituye al vault activo del usuario (fly commands, manager, workers).
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

_AUTHORIZED_USERS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS main.authorized_users (
    tenant_id VARCHAR,
    user_id VARCHAR,
    username VARCHAR,
    role VARCHAR DEFAULT 'user',
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, user_id)
);
"""

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
    # Prepara el esquema de Telegram Guard (idempotente).
    try:
        # Importante: reutilizar la misma conexión DuckDB que mantiene graph_server
        # para evitar conflictos de lock.
        from duckclaw.graphs.graph_server import get_db

        db = get_db()
        db.execute(
            """
            CREATE TABLE IF NOT EXISTS main.authorized_users (
                tenant_id VARCHAR,
                user_id VARCHAR,
                username VARCHAR,
                role VARCHAR DEFAULT 'user',
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (tenant_id, user_id)
            );
            """
        )
        from duckclaw.shared_db_grants import ensure_user_shared_db_access_table

        ensure_user_shared_db_access_table(db)
    except Exception as exc:
        _gateway_log.warning("Telegram Guard: no se pudo inicializar authorized_users: %s", exc)
    try:
        from duckclaw.graphs.graph_server import get_db
        from duckclaw.forge import ensure_leila_mvp_schema

        ensure_leila_mvp_schema(get_db())
    except Exception as exc:
        _gateway_log.warning("Leila MVP: no se pudo inicializar leila_products/leila_orders: %s", exc)
    try:
        ensure_vault_registry()
    except Exception as exc:
        _gateway_log.warning("Multi-Vault: no se pudo inicializar user_vaults: %s", exc)
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
    key = f"whitelist:{tenant_id}:{user_id}"
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
        try:
            db.execute(_AUTHORIZED_USERS_TABLE_DDL)
        except Exception:
            # No rompemos; el SELECT de abajo dará None.
            return

    try:
        raw = db.query(
            f"SELECT role FROM main.authorized_users WHERE tenant_id='{tid}' AND user_id='{uid}' LIMIT 1"
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
                f"SELECT role FROM main.authorized_users WHERE tenant_id='{tid}' AND user_id='{uid}' LIMIT 1"
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


def _send_security_alert_to_admin(user_id: str, tenant_id: str) -> None:
    """
    Alert opcional al admin via webhook n8n (best-effort).
    """
    admin_chat_id = (os.getenv("DUCKCLAW_ADMIN_CHAT_ID") or "").strip()
    webhook_url = (os.getenv("N8N_OUTBOUND_WEBHOOK_URL") or "").strip()
    auth_key = (os.getenv("N8N_AUTH_KEY") or getattr(settings, "N8N_AUTH_KEY", "") or "").strip()

    if not admin_chat_id or not webhook_url:
        _gateway_log.warning(
            "Telegram Guard: no se pudo enviar alerta (admin_chat_id=%r webhook=%r)",
            admin_chat_id,
            bool(webhook_url),
        )
        return

    text = f"🚨 Alerta de Seguridad: El usuario {user_id} ha intentado acceder 3 veces sin autorización al tenant {tenant_id}."
    headers: dict[str, Any] = {"Content-Type": "application/json"}
    if auth_key:
        headers["X-DuckClaw-Secret"] = auth_key

    payload = {"chat_id": str(admin_chat_id), "text": escape_telegram_markdown_v2(text)}
    data = json.dumps(payload).encode("utf-8")
    req = _url_request.Request(webhook_url, data=data, headers=headers, method="POST")

    try:
        with _url_request.urlopen(req, timeout=10) as resp:
            _ = resp.read()
    except URLError as exc:
        _gateway_log.warning("Telegram Guard: error enviando alerta webhook: %s", exc)
    except Exception as exc:  # noqa: BLE001
        _gateway_log.warning("Telegram Guard: error enviando alerta webhook (unknown): %s", exc)


# Telegram sendMessage: máx. 4096 caracteres (https://core.telegram.org/bots/api#sendmessage).
_TELEGRAM_SENDMESSAGE_CHAR_LIMIT = 4096
# Trozos de texto plano antes de _telegram_safe; conservador para no superar 4096 tras escapar MarkdownV2.
_DEFAULT_TELEGRAM_REPLY_PLAIN_CHUNK = 2000
# Webhook outbound: margen para prefijo [i/n] tras escape.
_OUTBOUND_CHAT_CHUNK = 3600


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
    """Subdivide texto plano hasta que ``safe_fn`` (p. ej. MarkdownV2) no supere el límite de Telegram."""
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


def _push_chat_reply_via_n8n_outbound_sync(*, chat_id: str, user_id: str, text: str) -> None:
    """
    Entrega la respuesta del chat al webhook de salida (mismo contrato que The Mind / n8n).

    Usado cuando el cliente HTTP ya cerró (p. ej. timeout de n8n en 300s) pero el agente
    terminó después: sin esto, el nodo «Responder Telegram» nunca recibe el JSON.
    """
    url = (os.getenv("N8N_OUTBOUND_WEBHOOK_URL") or "").strip()
    if not url:
        _gateway_log.warning(
            "outbound fallback: cliente desconectado pero N8N_OUTBOUND_WEBHOOK_URL no está definido; "
            "no se puede reenviar la respuesta a Telegram."
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

    chunks: list[str] = []
    i = 0
    while i < len(raw):
        chunks.append(raw[i : i + _OUTBOUND_CHAT_CHUNK])
        i += _OUTBOUND_CHAT_CHUNK
    if not chunks:
        chunks = [raw]

    for idx, part in enumerate(chunks):
        prefix = f"[{idx + 1}/{len(chunks)}]\n" if len(chunks) > 1 else ""
        payload = {
            "chat_id": cid,
            "user_id": uid,
            "text": escape_telegram_markdown_v2(prefix + part),
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


async def _authorize_or_reject(*, tenant_id: str, user_id: str, is_owner: bool) -> None:
    """
    Raises HTTPException(403) for unauthorized access.
    Also increments unauthorized attempts and triggers admin alert after 3 attempts.
    """
    # Check 1 (Bypass): owner bypass no DB/Redis access.
    if is_owner:
        _langsmith_auth_log(auth_status="authorized", user_id=user_id, tenant_id=tenant_id)
        return

    redis_client = getattr(app.state, "redis", None)
    from duckclaw.graphs.graph_server import get_db

    db = get_db()
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
    dbp = (os.getenv("DUCKCLAW_DB_PATH") or "").lower()
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
    result = await _invoke_chat(
        body,
        worker_id or "finanz",
        session_id=session_id,
        tenant_id=tenant_id,
        redis_client=redis_client,
    )
    # n8n suele usar timeout ~300s; si el agente tarda más, el cliente aborta y esta respuesta
    # no llega al flujo. Reenvío best-effort al webhook de Telegram (mismo que alertas / The Mind).
    _fb = (os.getenv("DUCKCLAW_CHAT_OUTBOUND_ON_CLIENT_DISCONNECT", "true").strip().lower())
    if _fb in ("1", "true", "yes", ""):
        try:
            if await http_request.is_disconnected():
                resp_text = (result.get("response") or "").strip() if isinstance(result, dict) else ""
                if resp_text:
                    uid_fb = (body.user_id or "").strip() or session_id
                    _gateway_log.info(
                        "outbound fallback: cliente desconectado; reenvío a n8n webhook (chat_id=%s, len=%s)",
                        format_chat_id_for_terminal(session_id),
                        len(resp_text),
                    )
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(
                        None,
                        lambda: _push_chat_reply_via_n8n_outbound_sync(
                            chat_id=session_id,
                            user_id=uid_fb,
                            text=resp_text,
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
    Elimina bloques tipo \"¿Cuál es mi tarea?\", \"Puedo ayudarte con:\" y menús de resumen financiero.
    """
    if not response or not isinstance(response, str):
        return response
    text = str(response)
    # No usar "Puedo ayudarte con:.*" con DOTALL: el modelo lo escribe en respuestas válidas
    # (p. ej. BI Analyst) y se borraba todo el cuerpo del mensaje antes de Telegram.
    patterns = [
        r"¿Cuál\s+es\s+mi\s+tarea\?.*",
        r"¿Qué\s+te\s+gustaría\s+hacer\s+ahora\?.*",
        r"-\s*📊\s*Resumen\s+financiero.*",
        r"-\s*💰\s*Registrar\s+transacciones.*",
    ]
    for pattern in patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE | re.DOTALL)
    return text.strip()


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
):
    """
    Orquesta la llamada al grafo LangGraph a partir de un ChatRequest.

    - session_id: ya resuelto (body + query + headers); debe ser el mismo en todos los POST del hilo.
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
    _, vault_db_path = resolve_active_vault(vault_user_id)
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
        )

    if not is_system_prompt and not is_owner:
        from duckclaw.graphs.graph_server import get_db
        from duckclaw.shared_db_grants import path_is_under_shared_tree, user_may_access_shared_path

        acl_db = get_db()
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
    if msg_stripped.startswith("/"):
        try:
            from duckclaw import DuckClaw
            from duckclaw.graphs.on_the_fly_commands import handle_command, prepare_leila_fly_duckdb

            vpath = (vault_db_path or "").strip()
            Path(vpath).parent.mkdir(parents=True, exist_ok=True)
            fly_db = DuckClaw(vpath)
            from duckclaw.graphs.graph_server import get_db as _fly_acl_db

            prepare_leila_fly_duckdb(
                fly_db,
                vpath,
                user_id=vault_user_id,
                tenant_id=tenant_id,
                acl_db=_fly_acl_db(),
            )
            try:
                cmd_reply = handle_command(
                    fly_db,
                    session_id,
                    message,
                    requester_id=user_id,
                    tenant_id=tenant_id,
                    vault_user_id=vault_user_id,
                    username=username,
                )
            finally:
                _con = getattr(fly_db, "_con", None)
                if _con is not None:
                    try:
                        _con.close()
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
        except Exception as exc:
            _gateway_log.error("fly command failed chat=%s: %s", format_chat_id_for_terminal(session_id), exc)

    try:
        from duckclaw.graphs.graph_server import _get_or_build_graph, _ainvoke
    except Exception as exc:
        _gateway_log.error(
            "graph init failed chat=%s: %s\n%s",
            format_chat_id_for_terminal(session_id),
            exc,
            traceback.format_exc(),
        )
        raise HTTPException(status_code=503, detail=f"Error inicializando el grafo: {exc}")

    # Concurrencia: procesar un solo mensaje por chat_id a la vez.
    async with _chat_lock(session_id):
        try:
            graph = _get_or_build_graph()
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
            result = await _ainvoke(
                graph,
                message,
                history_for_model,
                session_id,
                tenant_id=tenant_id,
                user_id=vault_user_id,
                username=username,
                vault_db_path=vault_db_path,
                shared_db_path=shared_db_path,
                is_system_prompt=is_system_prompt,
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
    # Evitar doble escape Telegram: historial/n8n a veces reinyecta texto ya escapado y el modelo lo copia.
    try:
        from duckclaw.graphs.on_the_fly_commands import unescape_telegram_markdown_v2_layers

        reply_text = unescape_telegram_markdown_v2_layers(reply_text or "")
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
                if token:
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
                else:
                    _gateway_log.warning(
                        "sandbox chart: hay PNG del sandbox pero no hay token Bot API (TELEGRAM_BOT_TOKEN "
                        "en el bloque PM2, o TELEGRAM_BOT_TOKEN_BI_ANALYST / TELEGRAM_BOT_TOKEN_LEILA / "
                        "TELEGRAM_BOT_TOKEN_SIATA según gateway); define uno en .env o en "
                        "config/api_gateways_pm2.json para este proceso."
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
        from duckclaw.graphs.on_the_fly_commands import _telegram_safe

        coarse = _split_plain_text_for_telegram_reply(
            reply_plain_for_storage or "",
            _telegram_reply_plain_chunk_size(),
        )
        plain_parts: list[str] = []
        for piece in coarse:
            plain_parts.extend(_plain_subchunks_for_telegram_budget(piece, _telegram_safe))
        if not plain_parts:
            plain_parts = [""]
        _telegram_response_parts_count = len(plain_parts)
        reply_text = _telegram_safe(plain_parts[0])
        tail_plain = "\n\n".join(plain_parts[1:]) if len(plain_parts) > 1 else ""
        if tail_plain.strip() and (os.getenv("N8N_OUTBOUND_WEBHOOK_URL") or "").strip():
            try:

                async def _send_telegram_tail() -> None:
                    await asyncio.get_running_loop().run_in_executor(
                        None,
                        partial(
                            _push_chat_reply_via_n8n_outbound_sync,
                            chat_id=session_id,
                            user_id=(user_id or "").strip() or session_id,
                            text=tail_plain,
                        ),
                    )

                asyncio.create_task(_send_telegram_tail())
            except Exception as exc:  # noqa: BLE001
                _gateway_log.warning("telegram reply tail: no se pudo programar envío: %s", exc)
        elif tail_plain.strip():
            _gateway_log.warning(
                "telegram reply: respuesta en %s partes; falta N8N_OUTBOUND_WEBHOOK_URL — "
                "solo la 1ª parte la envía n8n (Responder Telegram)",
                len(plain_parts),
            )
    except Exception:
        try:
            from duckclaw.graphs.on_the_fly_commands import _telegram_safe

            reply_text = _telegram_safe(reply_plain_for_storage)
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
        u = normalize_history_item({"role": "user", "content": message})
        a = normalize_history_item({"role": "assistant", "content": reply_plain_for_storage})
        if u and a:
            await redis_save_chat_history(
                redis_client,
                tenant_id,
                session_id,
                history_for_model + [u, a],
            )
    out_resp: dict[str, Any] = {
        "response": reply_text,
        "session_id": session_id,
        "worker_id": effective_worker_id or worker_id,
        "elapsed_ms": elapsed_ms,
    }
    if _telegram_response_parts_count > 1:
        out_resp["response_parts"] = _telegram_response_parts_count
    # Visibilidad en n8n: el nodo Telegram solo envía texto; la imagen la manda el gateway por Bot API.
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
        from duckclaw.shared_db_grants import path_is_under_shared_tree, user_may_access_shared_path
        from duckclaw.graphs.graph_server import get_db

        if path_is_under_shared_tree(db_path) and not user_may_access_shared_path(
            get_db(),
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
            _, db_path = resolve_active_vault(user_id)
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


# ── Quotes router (microservicio: routers en services/api-gateway) ───────────

try:
    from routers.quotes import router as quotes_router
    app.include_router(quotes_router)
except ImportError:
    pass
