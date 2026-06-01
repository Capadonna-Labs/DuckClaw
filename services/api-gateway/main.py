# services/api-gateway/main.py
"""
DuckClaw API Gateway — Microservicio unificado.

Punto de entrada único para Telegram (webhook/long polling), clientes HTTP, Angular y escrituras a DuckDB.
Endpoints: /api/v1/agent/chat, /api/v1/db/write, homeostasis, system health.
"""

from __future__ import annotations

import asyncio
import inspect
import hashlib
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
from dataclasses import replace
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
from fastapi.responses import JSONResponse, StreamingResponse
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
    canonical_manifest_worker_id,
    pm2_app_to_worker_map_from_env,
    resolve_telegram_token_for_worker_id,
    telegram_token_from_pm2_env_dict,
    telegram_worker_ids_match_for_compact_route,
)
from duckclaw.forge.team_env import default_tenant_id_from_env, default_worker_id_from_env
from duckclaw.gateway_db import (
    GATEWAY_DB_ENV_KEYS,
    default_pqrsd_assistant_vault_path,
    get_gateway_db_path,
    raw_gateway_db_path_from_mapping,
    resolve_env_duckdb_path,
)
from duckclaw.channels import GatewayDeliveryContext


# Cargar .env desde repo root (fuente de verdad para secretos; PM2 env_file + override abajo).
_repo_root = Path(__file__).resolve().parent.parent.parent
_dotenv_flat: dict[str, str] = {}
if os.environ.get("DUCKCLAW_DISABLE_DOTENV") != "1":
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
                    _dotenv_flat[_ks] = _vs
            break
if _dotenv_flat:
    from duckclaw.env_secrets import DOTENV_OVERRIDE_KEYS, apply_dotenv_overrides_to_os_environ

    for _ks, _vs in _dotenv_flat.items():
        if _ks in DOTENV_OVERRIDE_KEYS:
            continue
        os.environ.setdefault(_ks, _vs)
    apply_dotenv_overrides_to_os_environ(_dotenv_flat)


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
        "DUCKCLAW_QUANT_TRADER_DB_PATH",
        "DUCKCLAW_PQRSD_ASSISTANT_DB_PATH",
    )):
        os.environ.setdefault("DUCKCLAW_FINANZ_DB_PATH", resolve_env_duckdb_path(legacy))
    if not any(os.environ.get(k) for k in GATEWAY_DB_ENV_KEYS):
        dbp = raw_gateway_db_path_from_mapping(env)
        if dbp:
            os.environ["DUCKCLAW_FINANZ_DB_PATH"] = resolve_env_duckdb_path(dbp)
    _matched_app = (matched_name or "").strip()
    _wid = pm2_app_to_worker_map_from_env().get(_matched_app, "")
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
    wid = pm2_app_to_worker_map_from_env().get(proc)
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


def _telegram_token_from_compact_routes_for_worker(worker_id: str) -> str:
    """Fallback: resuelve token por worker desde DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES."""
    try:
        from duckclaw.integrations.telegram.compact_webhook_routes import load_path_webhook_bindings_from_env

        if not (worker_id or "").strip():
            return ""
        for b in load_path_webhook_bindings_from_env():
            if telegram_worker_ids_match_for_compact_route(worker_id, b.worker_id):
                return str(b.bot_token or "").strip()
    except Exception:
        return ""
    return ""


from duckclaw.pm2_gateway_db import dedicated_gateway_db_path_resolved


def _dedicated_gateway_vault_db_path() -> str | None:
    """
    Si este proceso es un gateway listado en api_gateways_pm2.json con rutas multiplex,
    esa DuckDB sustituye al vault activo del usuario (fly commands, manager, workers).
    """
    return dedicated_gateway_db_path_resolved()


def _worker_id_is_pqrsd_assistant(worker_id: str) -> bool:
    """True si la ruta/query de chat apunta al template PQRSD (id forge: pqrsd_assistant)."""
    s = (worker_id or "").strip().lower().replace("-", "_")
    return s == "pqrsd_assistant"

try:
    from core.config import settings
except ImportError:
    class _Settings:
        PROJECT_NAME = "DuckClaw API Gateway"
        VERSION = "0.1.0"

        def __init__(self) -> None:
            from duckclaw.runtime_env import resolve_redis_url

            self.REDIS_URL = resolve_redis_url()

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


def _install_duckdb_connect_probe() -> None:
    pass


_install_duckdb_connect_probe()


_obs_log = get_obs_logger()
_gateway_log.info(
    "Gateway startup: gateway_db_path=%s DUCKCLAW_PM2_MATCHED_APP_NAME=%s "
    "DUCKCLAW_WAR_ROOM_ACL_DB_PATH=%s | diagnóstico WR: pm2 logs … --lines 300 "
    "y grep telegram_inbound_early war_room_gate DROP_NO_MENTION rate_limited",
    get_gateway_db_path() or "(unset)",
    (os.environ.get("DUCKCLAW_PM2_MATCHED_APP_NAME") or "").strip() or "(unset)",
    (os.environ.get("DUCKCLAW_WAR_ROOM_ACL_DB_PATH") or "").strip() or "(unset)",
)
try:
    from duckclaw.integrations.telegram.compact_webhook_routes import load_path_webhook_bindings_from_env

    _compact = load_path_webhook_bindings_from_env()
    if _compact:
        _gateway_log.info(
            "telegram path multiplex: %s ruta(s) cargadas al arranque: %s",
            len(_compact),
            ", ".join(b.webhook_path for b in _compact),
        )
except ValueError as _compact_exc:
    _gateway_log.error(
        "DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES (compacto) inválido al arranque; "
        "rutas por path no montadas hasta corregir .env: %s",
        _compact_exc,
    )
except Exception:
    pass
_pqrsd_startup = (os.environ.get("DUCKCLAW_PQRSD_ASSISTANT_DB_PATH") or "").strip()
if _pqrsd_startup:
    _gateway_log.info(
        "PQRSD-Assistant: bóveda del worker (DUCKCLAW_PQRSD_ASSISTANT_DB_PATH) → %s "
        "(hub ACL/whitelist sigue en gateway_db_path arriba)",
        resolve_env_duckdb_path(_pqrsd_startup),
    )


def _uvicorn_listen_port() -> int:
    try:
        for i, x in enumerate(sys.argv):
            if x == "--port" and i + 1 < len(sys.argv):
                return int(sys.argv[i + 1])
    except (ValueError, IndexError):
        pass
    from duckclaw.gateway_port import resolve_gateway_port

    return resolve_gateway_port()


def _warn_if_loopback_gateway_port_steals_telegram_funnel() -> None:
    """
    Funnel suele hacer proxy a ``127.0.0.1:<DUCKCLAW_GATEWAY_PORT>``. Si otro proceso
    (p.ej. discord_mcp) enlaza ese loopback, Telegram recibe 404 del proceso equivocado.
    """
    port = _uvicorn_listen_port()
    loopback = f"127.0.0.1:{port}"
    lsof_bin = shutil.which("lsof")
    if not lsof_bin:
        return
    try:
        proc = subprocess.run(
            [lsof_bin, "-nP", f"-iTCP:{port}", "-sTCP:LISTEN"],
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return
    out = (proc.stdout or "").strip()
    if loopback not in out:
        return
    low = out.lower()
    condensed = " | ".join(out.splitlines()[:10])
    if "discord_mcp" in low or "-m discord_mcp.main" in low:
        _gateway_log.error(
            "Conflicto Telegram/Funnel: hay LISTEN en %s relacionado con discord_mcp; "
            "las peticiones a %s no llegarán a este gateway. Ejecuta "
            "`bash scripts/telegram/stop_discord_mcp_port_8000.sh` o arranca MCP con HOST=127.0.0.1 "
            "PORT=8010. lsof (recorte): %s",
            loopback,
            loopback,
            condensed,
        )
        return
    listen_hits = [ln for ln in out.splitlines() if "LISTEN" in ln]
    if len(listen_hits) >= 2:
        _gateway_log.warning(
            "Puerto %s: múltiples LISTEN; curl/Funnel a 127.0.0.1 pueden no ser DuckClaw. "
            "lsof (recorte): %s",
            port,
            condensed,
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
    _warn_if_loopback_gateway_port_steals_telegram_funnel()
    app.state.redis = redis.from_url(str(settings.REDIS_URL), decode_responses=True)
    app.state.goals_ticker_task = None
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

    try:
        from duckclaw.forge.skills.reddit_bridge import (
            _reddit_env_ready,
            reddit_mcp_using_prefetch,
            warm_reddit_mcp_pool,
        )

        if _reddit_env_ready():
            if not reddit_mcp_using_prefetch():
                _gateway_log.warning(
                    "Reddit MCP: sin prefetch local (npx puede tardar 2–5 min). "
                    "Ejecuta: bash scripts/prefetch_mcp_reddit.sh"
                )
            else:
                _gateway_log.info("Reddit MCP: usando cache local (.mcp-cache/reddit)")
            import threading

            def _warm_reddit_mcp() -> None:
                warm_reddit_mcp_pool()

            threading.Thread(
                target=_warm_reddit_mcp,
                name="reddit-mcp-warm",
                daemon=True,
            ).start()
            _gateway_log.info("Reddit MCP: warm iniciado en background")
    except Exception as exc:  # noqa: BLE001
        _gateway_log.warning("Reddit MCP: warm no iniciado: %s", exc)

    _embed_goals_ticker = (
        os.environ.get("DUCKCLAW_EMBED_GOALS_TICKER", "true").strip().lower()
        in ("1", "true", "yes", "on")
    )
    if _embed_goals_ticker:
        try:
            from services.heartbeat.main import GOALS_TICKER_POLL_SECONDS, _run_goals_proactive_tick

            _poll_s = max(5, int(GOALS_TICKER_POLL_SECONDS))

            async def _goals_ticker_loop() -> None:
                while True:
                    try:
                        await _run_goals_proactive_tick()
                    except Exception as _loop_exc:  # noqa: BLE001
                        _gateway_log.warning("embedded crons ticker loop error: %s", _loop_exc)
                    await asyncio.sleep(_poll_s)

            app.state.goals_ticker_task = asyncio.create_task(_goals_ticker_loop())
            _gateway_log.info(
                "embedded crons ticker enabled (poll=%ss, source=services.heartbeat._run_goals_proactive_tick)",
                _poll_s,
            )
        except Exception as exc:  # noqa: BLE001
            _gateway_log.warning("embedded crons ticker no disponible: %s", exc)

    try:
        from duckclaw.forge.skills.comfyui_bridge import (
            clear_all_comfy_generations,
            reset_comfyui_runtime,
        )

        stale = clear_all_comfy_generations()
        reset_result = await asyncio.to_thread(reset_comfyui_runtime)
        if stale or reset_result.get("interrupt") or reset_result.get("deleted_pending"):
            _gateway_log.info(
                "ComfyUI startup hygiene: stale_jobs=%s reset=%s",
                len(stale),
                reset_result,
            )
    except Exception as exc:  # noqa: BLE001
        _gateway_log.debug("ComfyUI startup hygiene skipped: %s", exc)

    yield

    _gt = getattr(app.state, "goals_ticker_task", None)
    if _gt is not None:
        _gt.cancel()
        try:
            await _gt
        except BaseException:
            pass
        app.state.goals_ticker_task = None

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
    # noVNC: el usuario abre el enlace en el navegador móvil sin X-Tailscale-Auth-Key; el token sustituye auth.
    if path.startswith("/api/v1/sandbox/novnc/"):
        return await call_next(request)
    # Consola admin (BFF local): autentica con X-Admin-Key, no Tailscale en el browser.
    if path.startswith("/api/v1/admin/"):
        return await call_next(request)
    # Playground u otras herramientas internas: BFF puede enviar X-Admin-Key en rutas /agent/*.
    admin_expected = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    admin_header = (request.headers.get("X-Admin-Key") or "").strip()
    if admin_expected and admin_header == admin_expected and path.startswith("/api/v1/agent/"):
        return await call_next(request)
    header_key = request.headers.get("X-Tailscale-Auth-Key", "").strip()
    if header_key != auth_key:
        return JSONResponse(
            status_code=401,
            content={"detail": "X-Tailscale-Auth-Key inválida o faltante"},
        )
    return await call_next(request)


app.middleware("http")(_tailscale_auth_middleware)


async def _telegram_http_ingress_probe_middleware(request: Request, call_next):
    """
    Registra cualquier POST bajo /api/v1/telegram antes del router.

    Si envías un mensaje al bot y aquí no aparece nada, Telegram no está alcanzando
    este proceso (webhook URL, túnel, otro puerto o bot distinto). Con multiplex
    compacto, ``/api/v1/telegram/webhook`` puede devolver 200 sin ejecutar el agente.
    """
    p = request.url.path or ""
    if request.method.upper() == "POST" and p.startswith("/api/v1/telegram"):
        _gateway_log.info("telegram_http_ingress: path=%s", p)
    return await call_next(request)


# Último registrado = primero en la cadena entrante: ver HTTP antes de auth/CORS internos.
app.middleware("http")(_telegram_http_ingress_probe_middleware)


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

    ``CHAT_PARALLEL_INVOCATIONS`` es alias de ``DUCKCLAW_CHAT_PARALLEL_INVOCATIONS`` (ver ``.env.example``).
    """
    for key in ("DUCKCLAW_CHAT_PARALLEL_INVOCATIONS", "CHAT_PARALLEL_INVOCATIONS"):
        if (os.environ.get(key) or "").strip().lower() in ("1", "true", "yes", "on"):
            return True
    return False


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


def _telegram_path_route_count(app: FastAPI) -> int:
    """Útil cuando ``:8000`` devuelve 404 en multiplex: proceso equivocado suele tener 0 rutas telegram."""
    n = 0
    for r in app.routes:
        p = getattr(r, "path", "") or ""
        if p.startswith("/api/v1/telegram/"):
            n += 1
    return n


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "api-gateway",
        "telegram_path_routes_registered": _telegram_path_route_count(app),
    }


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
        return {"workers": [default_worker_id_from_env()]}


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
    Alert opcional al admin vía Bot API nativa (TELEGRAM_BOT_TOKEN o token del bot activo).
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
            _gateway_log.warning("Telegram Guard: falló alerta nativa Bot API: %s", exc)
    _gateway_log.warning(
        "Telegram Guard: alerta admin no enviada (configure TELEGRAM_BOT_TOKEN o token del bot activo)",
    )


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
    """Parte texto plano para envío por Bot API (límite 4096 por mensaje)."""
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


def _outbound_deliver_chat_text_sync(
    *,
    chat_id: str,
    user_id: str,
    text: str,
    worker_id: str | None = None,
    outbound_telegram_bot_token: str | None = None,
    prefer_native_bot_api: bool = False,
    telegram_mcp: Any = None,
    redis_url: str | None = None,
    tenant_id: str = "default",
) -> bool:
    """Entrega texto largo al usuario: MCP (si hay sesión) y luego Bot API nativa."""
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
        return False

    if telegram_mcp is not None and not prefer_native_bot_api:
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
                return True
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

    token = (outbound_telegram_bot_token or "").strip()
    worker_token = ""
    token_source = "explicit" if token else "none"
    if not token:
        try:
            worker_token = (resolve_telegram_token_for_worker_id((worker_id or "").strip()) or "").strip()
            token = worker_token
            if token:
                token_source = "resolve_telegram_token_for_worker_id"
        except Exception:
            token = ""
    if not token:
        token = _telegram_token_from_compact_routes_for_worker((worker_id or "").strip())
        if token:
            token_source = "compact_webhook_routes"
    if not token:
        token = _effective_telegram_bot_token()
        if token:
            token_source = "effective_telegram_bot_token"
        else:
            _wid = canonical_manifest_worker_id((worker_id or "").strip())
            _gateway_log.warning(
                "outbound deliver: sin token Bot API para worker_id=%r. Defina TELEGRAM_%s_TOKEN, "
                "TELEGRAM_BOT_TOKEN o entrada en DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES.",
                worker_id,
                (_wid or "WORKER").replace("-", "_").upper(),
            )
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
                return True
            _gateway_log.warning(
                "outbound deliver: Bot API no envió partes (chat_id=%s)",
                format_chat_id_for_terminal(cid),
            )
        except Exception as exc:  # noqa: BLE001
            _gateway_log.warning(
                "outbound deliver: error Bot API chat_id=%s: %s",
                format_chat_id_for_terminal(cid),
                exc,
            )

    return False


def _deliver_outbound_by_channel(
    dc: GatewayDeliveryContext,
    *,
    chat_id: str,
    user_id: str,
    text: str,
    worker_id: str | None,
    tenant_id: str,
    redis_url: str | None,
    prefer_native_bot_api: bool = False,
) -> bool:
    """Entrega best-effort según canal (Telegram: MCP/Bot API; Discord: PATCH @original)."""
    ch = (dc.channel or "telegram").strip().lower()
    if ch == "telegram":
        return _outbound_deliver_chat_text_sync(
            chat_id=chat_id,
            user_id=user_id,
            text=text,
            worker_id=worker_id,
            outbound_telegram_bot_token=dc.outbound_bot_token,
            prefer_native_bot_api=prefer_native_bot_api or dc.prefer_native_bot_api,
            telegram_mcp=dc.telegram_mcp,
            redis_url=redis_url,
            tenant_id=tenant_id,
        )
    if ch == "discord":
        from core.discord_interactions import discord_followup_edit_original_sync

        return discord_followup_edit_original_sync(
            application_id=(dc.discord_application_id or "").strip(),
            interaction_token=(dc.discord_interaction_token or "").strip(),
            bot_token=(dc.outbound_bot_token or "").strip(),
            content=text or "",
        )
    _gateway_log.warning("deliver outbound: canal desconocido %r", dc.channel)
    return False


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
        Bóveda forzada por multiplex Telegram (p. ej. Quant → ``DUCKCLAW_QUANT_TRADER_DB_PATH``).
        Se usa en otras comprobaciones del request (p. ej. grants / vault); la whitelist
        ``main.authorized_users`` del Telegram Guard **siempre** se lee del hub
        ``get_gateway_db_path()`` (mismo archivo que comandos fly ``/team``) para no desalinear
        altas con rutas por bot.
    """
    # Check 1 (Bypass): owner bypass no DB/Redis access.
    if is_owner:
        _langsmith_auth_log(auth_status="authorized", user_id=user_id, tenant_id=tenant_id)
        return

    redis_client = getattr(app.state, "redis", None)
    from core.gateway_acl_db import get_gateway_acl_duckdb, get_war_room_acl_duckdb

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

    # PM2 visibility: ruido en logs, pero respuesta silenciosa en Telegram.
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

    Si solo llega ``default`` u omisión, aplica ``DUCKCLAW_GATEWAY_TENANT_ID`` o ``default``.
    """
    rt = (request_tenant or "").strip()
    if rt and rt.lower() != "default":
        return rt
    return default_tenant_id_from_env()


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
    _dc_http = GatewayDeliveryContext.from_legacy_telegram(
        telegram_multipart_tail_delivery=None,
        telegram_mcp=_tg_mcp,
        telegram_forced_vault_db_path=None,
        outbound_telegram_bot_token=None,
    )
    _deliver_outbound_raw = (http_request.query_params.get("deliver_outbound") or "").strip().lower()
    _deliver_outbound = _deliver_outbound_raw in ("1", "true", "yes", "on")
    _stream = bool(body.stream) or (
        (http_request.query_params.get("stream") or "").strip().lower() in ("1", "true", "yes", "on")
    )
    _invoke_kw = {
        "redis_client": redis_client,
        "telegram_mcp": _tg_mcp,
    }
    if _stream:
        from core.sse_stream import SSE_HEADERS

        return StreamingResponse(
            _invoke_chat_sse_body(
                body,
                worker_id or default_worker_id_from_env(),
                session_id,
                tenant_id,
                **_invoke_kw,
            ),
            media_type="text/event-stream",
            headers=dict(SSE_HEADERS),
        )
    result = await _invoke_chat(
        body,
        worker_id or default_worker_id_from_env(),
        session_id=session_id,
        tenant_id=tenant_id,
        **_invoke_kw,
    )
    if _deliver_outbound:
        try:
            resp_text = (result.get("response") or "").strip() if isinstance(result, dict) else ""
            if resp_text:
                uid_out = (body.user_id or "").strip() or session_id
                loop = asyncio.get_running_loop()
                _redis_url = str(settings.REDIS_URL)
                _dc_deliver = GatewayDeliveryContext(
                    channel=_dc_http.channel,
                    telegram_multipart_tail_delivery=_dc_http.telegram_multipart_tail_delivery,
                    telegram_mcp=_dc_http.telegram_mcp,
                    telegram_forced_vault_db_path=_dc_http.telegram_forced_vault_db_path,
                    outbound_bot_token=_dc_http.outbound_bot_token,
                    prefer_native_bot_api=True,
                )
                await loop.run_in_executor(
                    None,
                    lambda: _deliver_outbound_by_channel(
                        _dc_deliver,
                        chat_id=session_id,
                        user_id=uid_out,
                        text=resp_text,
                        worker_id=(worker_id or ""),
                        tenant_id=tenant_id,
                        redis_url=_redis_url,
                        prefer_native_bot_api=True,
                    ),
                )
        except Exception as exc:  # noqa: BLE001
            _gateway_log.warning("agent_chat forced outbound failed: %s", exc)
    # Cliente HTTP puede cerrar antes (timeout ~300s, proxy, etc.): reenvío best-effort
    # a Telegram por Bot API nativa o webhook opcional.
    _fb = (os.getenv("DUCKCLAW_CHAT_OUTBOUND_ON_CLIENT_DISCONNECT", "true").strip().lower())
    if _fb in ("1", "true", "yes", ""):
        try:
            if await http_request.is_disconnected():
                resp_text = (result.get("response") or "").strip() if isinstance(result, dict) else ""
                if resp_text:
                    uid_fb = (body.user_id or "").strip() or session_id
                    _gateway_log.info(
                        "outbound fallback: cliente desconectado; entrega async a Telegram "
                        "(nativo o webhook) chat_id=%s len=%s",
                        format_chat_id_for_terminal(session_id),
                        len(resp_text),
                    )
                    loop = asyncio.get_running_loop()
                    _mcp_snap = _tg_mcp
                    _redis_url = str(settings.REDIS_URL)
                    _dc_fb = GatewayDeliveryContext.from_legacy_telegram(
                        telegram_multipart_tail_delivery=None,
                        telegram_mcp=_mcp_snap,
                        telegram_forced_vault_db_path=None,
                        outbound_telegram_bot_token=None,
                    )
                    await loop.run_in_executor(
                        None,
                        lambda: _deliver_outbound_by_channel(
                            _dc_fb,
                            chat_id=session_id,
                            user_id=uid_fb,
                            text=resp_text,
                            worker_id=(worker_id or ""),
                            tenant_id=tenant_id,
                            redis_url=_redis_url,
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


def _visual_artifact_id_from_messages(messages: Any) -> str:
    """Fallback: artifact_id del último generate_visual_asset OK en mensajes del turno."""
    import json

    try:
        from langchain_core.messages import ToolMessage
    except ImportError:
        return ""
    if not isinstance(messages, list):
        return ""
    for msg in reversed(messages):
        if not isinstance(msg, ToolMessage):
            continue
        if (msg.name or "") not in ("generate_visual_asset", "edit_visual_asset"):
            continue
        try:
            payload = json.loads(str(msg.content or ""))
        except (TypeError, json.JSONDecodeError):
            continue
        if not isinstance(payload, dict) or not payload.get("ok"):
            continue
        aid = str(payload.get("artifact_id") or "").strip()
        if aid:
            return aid
    return ""


def _admin_visual_fields_from_invoke_result(
    session_id: str,
    result: dict[str, Any],
    tenant_id: str,
) -> dict[str, str]:
    """Metadatos de imagen para SSE/JSON del playground admin (ComfyUI → artifacts/)."""
    from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

    if not is_admin_ui_chat_session(session_id):
        return {}
    out: dict[str, str] = {}
    b64 = (result.get("sandbox_photo_base64") or result.get("figure_base64") or "").strip()
    if b64:
        out["figure_base64"] = b64
    aid = (result.get("visual_artifact_id") or result.get("artifact_id") or "").strip()
    if not aid:
        aid = _visual_artifact_id_from_messages(result.get("messages"))
    if aid:
        out["artifact_id"] = aid
        out["artifact_tenant_id"] = (tenant_id or "default").strip() or "default"
    return out


async def _invoke_chat_sse_body(
    payload: ChatRequest,
    worker_id: str,
    session_id: str,
    tenant_id: str,
    **invoke_kwargs: Any,
):
    """Generador SSE: invoca el grafo, heartbeats admin en vivo y tokens + [DONE]."""
    import asyncio

    from core.admin_chat_heartbeat import iter_admin_heartbeats
    from core.sse_stream import (
        emit_chat_reply_sse,
        friendly_chat_error_message,
        sse_error,
        sse_heartbeat,
        sse_terminal_done,
    )
    from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

    redis_client = invoke_kwargs.get("redis_client")
    admin_session = is_admin_ui_chat_session(session_id)
    stop = asyncio.Event()
    heartbeat_task: asyncio.Task | None = None
    heartbeat_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

    async def _pump_admin_heartbeats() -> None:
        try:
            async for item in iter_admin_heartbeats(redis_client, session_id, stop=stop):
                await heartbeat_queue.put(item)
        except asyncio.CancelledError:
            raise

    if admin_session and redis_client is not None:
        heartbeat_task = asyncio.create_task(_pump_admin_heartbeats())

    invoke_task = asyncio.create_task(
        _invoke_chat(
            payload,
            worker_id,
            session_id,
            tenant_id,
            **invoke_kwargs,
        )
    )

    try:
        while not invoke_task.done():
            try:
                hb = await asyncio.wait_for(heartbeat_queue.get(), timeout=0.2)
                yield sse_heartbeat(
                    str(hb.get("text") or ""),
                    kind=str(hb.get("kind") or "status"),
                    worker_id=str(hb.get("worker_id") or "") or None,
                    swarm_slot=hb.get("swarm_slot"),
                    artifact_id=str(hb.get("artifact_id") or "").strip() or None,
                    artifact_tenant_id=str(hb.get("artifact_tenant_id") or "").strip() or None,
                    tool_name=str(hb.get("tool_name") or "").strip() or None,
                    tool_phase=str(hb.get("tool_phase") or "").strip().lower() or None,
                    elapsed_ms=hb.get("elapsed_ms"),
                )
            except asyncio.TimeoutError:
                continue

        while not heartbeat_queue.empty():
            hb = heartbeat_queue.get_nowait()
            yield sse_heartbeat(
                str(hb.get("text") or ""),
                kind=str(hb.get("kind") or "status"),
                worker_id=str(hb.get("worker_id") or "") or None,
                swarm_slot=hb.get("swarm_slot"),
                artifact_id=str(hb.get("artifact_id") or "").strip() or None,
                artifact_tenant_id=str(hb.get("artifact_tenant_id") or "").strip() or None,
                tool_name=str(hb.get("tool_name") or "").strip() or None,
                tool_phase=str(hb.get("tool_phase") or "").strip().lower() or None,
                elapsed_ms=hb.get("elapsed_ms"),
            )

        result = await invoke_task
        reply = ""
        assigned: str | None = None
        usage: dict[str, Any] | None = None
        elapsed_ms: int | None = None
        sse_extra: dict[str, Any] | None = None
        if isinstance(result, dict):
            reply = str(result.get("response") or result.get("reply") or "")
            assigned = result.get("assigned_worker_id")
            usage = result.get("usage_tokens")
            raw_elapsed = result.get("elapsed_ms")
            if raw_elapsed is not None:
                try:
                    elapsed_ms = int(raw_elapsed)
                except (TypeError, ValueError):
                    elapsed_ms = None
            admin_visual = _admin_visual_fields_from_invoke_result(session_id, result, tenant_id)
            if admin_visual:
                sse_extra = dict(admin_visual)
        else:
            reply = str(result or "")
        async for event in emit_chat_reply_sse(
            reply,
            assigned_worker_id=assigned,
            usage_tokens=usage,
            worker_id=worker_id,
            elapsed_ms=elapsed_ms,
            extra=sse_extra,
        ):
            yield event
    except HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
        yield sse_error(detail, status_hint=exc.status_code)
        yield sse_terminal_done()
    except Exception as exc:
        yield sse_error(friendly_chat_error_message(exc))
        yield sse_terminal_done()
    finally:
        stop.set()
        if heartbeat_task is not None:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass
        if not invoke_task.done():
            try:
                from duckclaw.forge.skills.comfyui_bridge import cancel_comfy_generation_for_chat

                cancel_comfy_generation_for_chat(session_id)
            except Exception:
                pass
            invoke_task.cancel()
            try:
                await invoke_task
            except Exception:
                pass


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
    delivery_context: GatewayDeliveryContext | None = None,
):
    """
    Orquesta la llamada al grafo LangGraph a partir de un ChatRequest.

    - session_id: ya resuelto (body + query + headers); debe ser el mismo en todos los POST del hilo.
    - telegram_multipart_tail_delivery: ignorado (siempre entrega nativa) para partes 2..N del mensaje.
    - delivery_context: si se omite, se reconstruye desde kwargs ``telegram_*`` (compatibilidad).
    """
    if delivery_context is not None:
        dc = delivery_context
    else:
        dc = GatewayDeliveryContext.from_legacy_telegram(
            telegram_multipart_tail_delivery=telegram_multipart_tail_delivery,
            telegram_mcp=telegram_mcp,
            telegram_forced_vault_db_path=telegram_forced_vault_db_path,
            outbound_telegram_bot_token=outbound_telegram_bot_token,
        )
    # Telegram: si llegan kwargs legacy junto a ``delivery_context`` (p. ej. webhook),
    # los valores explícitos no-None tienen prioridad para evitar desalinear MCP/token/bóveda.
    _ch_eff = (dc.channel or "telegram").strip().lower()
    if _ch_eff == "telegram":
        _patch: dict[str, Any] = {}
        if telegram_multipart_tail_delivery is not None:
            _patch["telegram_multipart_tail_delivery"] = telegram_multipart_tail_delivery
        if telegram_mcp is not None:
            _patch["telegram_mcp"] = telegram_mcp
        if telegram_forced_vault_db_path is not None:
            _patch["telegram_forced_vault_db_path"] = telegram_forced_vault_db_path
        if outbound_telegram_bot_token is not None:
            _patch["outbound_bot_token"] = (outbound_telegram_bot_token or "").strip() or None
        if _patch:
            dc = replace(dc, **_patch)

    message = (payload.message or "").strip()
    session_id = (session_id or "default").strip() or "default"
    tenant_id = _effective_tenant_id(tenant_id)
    # Campos opcionales: defaults resilientes
    chat_type = (payload.chat_type or "private").strip().lower() or "private"
    username = (payload.username or "Usuario").strip() or "Usuario"
    user_id = (payload.user_id or "").strip()
    # Telegram DM: algunos clientes mandan solo chat_id; para el Guard, user_id == chat_id.
    if not user_id and chat_type == "private":
        user_id = (session_id or "").strip()
    vault_user_id = user_id or session_id
    vault_scope = vault_scope_id_for_tenant(tenant_id)
    _, vault_db_path = resolve_active_vault(vault_user_id, vault_scope)
    _forced_v = (dc.telegram_forced_vault_db_path or "").strip()
    _payload_vault = (getattr(payload, "vault_db_path", None) or "").strip()
    _telegram_acl_for_guard: str | None = None
    if _forced_v:
        vault_db_path = resolve_env_duckdb_path(_forced_v)
        _telegram_acl_for_guard = vault_db_path
    elif _payload_vault:
        vault_db_path = resolve_env_duckdb_path(_payload_vault)
        _telegram_acl_for_guard = vault_db_path
    else:
        # Hub Finanz + env PQRSD: get_gateway_db_path() prioriza FINANZ; el worker PQRSD debe
        # usar DUCKCLAW_PQRSD_ASSISTANT_DB_PATH o, si no está definida, db/private/<user>/pqrsd-assistantdb1.duckdb.
        _pqrsd_raw = (os.environ.get("DUCKCLAW_PQRSD_ASSISTANT_DB_PATH") or "").strip()
        if _worker_id_is_pqrsd_assistant(worker_id):
            if _pqrsd_raw:
                vault_db_path = resolve_env_duckdb_path(_pqrsd_raw)
            else:
                vault_db_path = default_pqrsd_assistant_vault_path(vault_user_id)
        else:
            _ded_vault = _dedicated_gateway_vault_db_path()
            if _ded_vault:
                vault_db_path = _ded_vault
    if not _forced_v and not _payload_vault:
        _route_wid = (worker_id or "").strip()
        if _route_wid and not _worker_id_is_pqrsd_assistant(_route_wid):
            try:
                from duckclaw.vaults import resolve_template_vault_path
                from duckclaw.workers.manifest import load_manifest

                _spec_route = load_manifest(_route_wid)
                _tpl_path = resolve_template_vault_path(
                    _spec_route.forge_vault_binding, vault_user_id
                )
                if _tpl_path:
                    vault_db_path = _tpl_path
            except Exception:
                pass
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

    # Observabilidad 2.1: fase orquestación HTTP → worker lógico "manager" (no el worker_id de ruta).
    chat_ident = _chat_identity_label(session_id, username)
    set_log_context(tenant_id=tenant_id, worker_id="manager", chat_id=chat_ident)
    log_req(_obs_log, "%s", _truncate_log(message), source="body")

    # Telegram Guard: autoriza antes de ejecutar comandos (/team, /sandbox, etc.)
    # y antes de invocar cualquier lógica LangGraph.
    owner_user_id = (os.getenv("DUCKCLAW_OWNER_ID") or os.getenv("DUCKCLAW_ADMIN_CHAT_ID") or "").strip()
    is_owner = bool(owner_user_id and user_id and str(user_id).strip() == str(owner_user_id).strip())
    auth_policy = (dc.auth_policy or "telegram_guard").strip()
    guard_required = auth_policy not in {"trusted_admin_console", "trusted_channel_route"}
    if not is_system_prompt and guard_required:
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
                from duckclaw.graphs.on_the_fly_commands import handle_command

                vpath = (vault_db_path or "").strip()
                Path(vpath).parent.mkdir(parents=True, exist_ok=True)
                # Siempre motor Python RW para fly: el worker puede haber abierto el mismo .duckdb
                # con el bridge nativo; mezclar nativo + Python o RO + RW en un PID provoca
                # «different configuration» en DuckDB.
                _fly_engine: Literal["auto", "python"] = "python"
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
                # Libera handles DuckDB del worker cacheado (misma bóveda) antes de abrir fly RW.
                try:
                    from duckclaw.graphs.manager_graph import (
                        clear_worker_graph_cache,
                        worker_graph_cache_entry_count,
                    )

                    _fly_cache_n = worker_graph_cache_entry_count()
                    clear_worker_graph_cache()
                    import gc as _gc

                    _gc.collect()
                except Exception:
                    _fly_cache_n = -1
                fly_db = DuckClaw(vpath, read_only=False, engine=_fly_engine)
                cmd_reply = handle_command(
                    fly_db,
                    session_id,
                    message,
                    requester_id=user_id,
                    tenant_id=tenant_id,
                    vault_user_id=vault_user_id,
                    username=username,
                    entry_worker_id=worker_id,
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
                chart_sent = False
                try:
                    from duckclaw.graphs.on_the_fly_commands import pop_all_fly_outbound_charts_b64

                    loop = asyncio.get_running_loop()
                    token = (
                        ((dc.outbound_bot_token or "").strip() or _effective_telegram_bot_token()).strip()
                        if (dc.channel or "telegram").strip().lower() == "telegram"
                        else ""
                    )
                    if token:
                        for photo_b64 in pop_all_fly_outbound_charts_b64(session_id):
                            png_bytes = decode_valid_sandbox_image_bytes(photo_b64)
                            if not png_bytes:
                                png_bytes = decode_sandbox_figure_base64(photo_b64)
                            if not png_bytes:
                                continue
                            ok = await loop.run_in_executor(
                                None,
                                lambda b=png_bytes: send_sandbox_chart_to_telegram_sync(
                                    bot_token=token,
                                    chat_id=str(session_id),
                                    image_bytes=b,
                                ),
                            )
                            chart_sent = chart_sent or bool(ok)
                except Exception as exc:
                    if _gateway_log.isEnabledFor(logging.DEBUG):
                        _gateway_log.debug("fly chart attach failed: %s", exc)
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
                outbound_telegram_bot_token=(dc.outbound_bot_token or "").strip() or None,
                entry_worker_id=(worker_id or "").strip() or None,
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
    # Evitar doble escape Telegram: historial a veces reinyecta texto ya escapado y el modelo lo copia.
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
            if png_bytes and (dc.channel or "telegram").strip().lower() == "telegram":
                token = (dc.outbound_bot_token or "").strip() or _effective_telegram_bot_token()
                # Evitar cruce de bot al enviar imágenes: para charts del sandbox usar
                # Bot API del token efectivo de la ruta actual (no MCP global).
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
                if not chart_sent and not token:
                    _gateway_log.warning(
                        "sandbox chart: hay PNG del sandbox pero no hay token de salida para este request "
                        "(outbound_bot_token ni token efectivo del contexto)."
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
    telegram_reply_head_plain: str | None = None
    telegram_multipart_tail_plain_for_client: str | None = None
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
        tail_plain = "\n\n".join(plain_parts[1:]) if len(plain_parts) > 1 else ""
        if tail_plain.strip():
            # Cola 2..N: el webhook (o el cliente) debe enviar la cabeza primero y luego hacer await
            # del tail. Un asyncio.create_task aquí compite con sendMessage de la cabeza y Telegram
            # muestra los bubbles en orden invertido.
            telegram_reply_head_plain = plain_parts[0]
            telegram_multipart_tail_plain_for_client = tail_plain
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
            saved_items = history_for_model + [u, a]
            await redis_save_chat_history(
                redis_client,
                tenant_id,
                session_id,
                saved_items,
            )
            try:
                from core.admin_conversations import (
                    get_conversation_meta,
                    upsert_conversation_meta,
                )

                existing_conv = await get_conversation_meta(redis_client, tenant_id, session_id)
                conv_section = existing_conv.section if existing_conv else None
                await upsert_conversation_meta(
                    redis_client,
                    tenant_id=tenant_id,
                    session_id=session_id,
                    actor=(username or "").strip(),
                    section=conv_section,
                    last_worker_id=(effective_worker_id or worker_id or "").strip(),
                    user_message=message,
                    assistant_message=reply_plain_for_storage or "",
                    message_count=len(saved_items),
                )
            except Exception:
                pass
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
    if isinstance(usage, dict) and usage:
        out_resp["usage_tokens"] = usage
    if _telegram_response_parts_count > 1:
        out_resp["response_parts"] = _telegram_response_parts_count
    if telegram_reply_head_plain is not None and (telegram_multipart_tail_plain_for_client or "").strip():
        out_resp["telegram_reply_head_plain"] = telegram_reply_head_plain
        out_resp["telegram_multipart_tail_plain"] = telegram_multipart_tail_plain_for_client
    # Texto en JSON; PNG del sandbox lo envía el gateway por Bot API (sendPhoto).
    if (
        not is_system_prompt
        and isinstance(result, dict)
        and (result.get("sandbox_photo_base64") or "").strip()
    ):
        out_resp["sandbox_chart_delivered"] = chart_sent
    if isinstance(result, dict):
        out_resp.update(_admin_visual_fields_from_invoke_result(session_id, result, tenant_id))
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


class ReadRequest(BaseModel):
    query: str = Field(..., description="Consulta SQL SELECT parametrizada")
    params: list = Field(default_factory=list, description="Parámetros para la consulta")
    tenant_id: str = Field(default="default", description="ID del tenant")
    user_id: str | None = Field(default=None, description="ID del usuario dueño de la bóveda")
    db_path: str | None = Field(default=None, description="Ruta DuckDB (solo lectura)")


def _resolve_db_path_for_vault(req: WriteRequest | ReadRequest) -> str:
    """Resuelve db_path con la misma lógica que enqueue_write (sin encolar)."""
    user_id = (req.user_id or "").strip() or "default"
    db_path = (req.db_path or "").strip()
    tid = (req.tenant_id or "").strip() or None
    if not db_path:
        _ded = _dedicated_gateway_vault_db_path()
        if _ded:
            db_path = _ded
        else:
            _t_eff = str(tid or "default").strip() or "default"
            _, db_path = resolve_active_vault(user_id, vault_scope_id_for_tenant(_t_eff))
    return db_path


@app.post("/api/v1/db/read")
async def db_read(req: ReadRequest) -> dict[str, Any]:
    """Ejecuta SELECT en DuckDB en solo lectura (CRM y clientes internos)."""
    q = (req.query or "").strip()
    if not q.upper().startswith("SELECT"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se permiten consultas SELECT.",
        )
    user_id = (req.user_id or "").strip() or "default"
    tid = (req.tenant_id or "").strip() or None
    db_path = _resolve_db_path_for_vault(req)
    if not validate_user_db_path(user_id, db_path, tenant_id=tid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="db_path inválido para el usuario.",
        )
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
            detail="Sin permiso para leer esta base de datos compartida.",
        )

    def _exec_read() -> list[dict[str, Any]]:
        from duckclaw.duckdb_read_compat import duckdb_connect_read_with_rw_fallback

        con = duckdb_connect_read_with_rw_fallback(db_path)
        try:
            cur = con.execute(q, req.params or [])
            desc = cur.description
            cols = [d[0] for d in desc] if desc else []
            rows_raw = cur.fetchall()
            out: list[dict[str, Any]] = []
            for row in rows_raw:
                out.append({cols[i]: row[i] for i in range(len(cols))})
            return out
        finally:
            con.close()

    try:
        rows = await asyncio.to_thread(_exec_read)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    return {"rows": rows}


# ── Telegram inbound webhook (integración nativa) ────────────────────────────

try:
    from routers.telegram_inbound_webhook import build_telegram_inbound_webhook_router

    app.include_router(
        build_telegram_inbound_webhook_router(
            invoke_agent_chat=_invoke_chat,
            resolve_effective_telegram_bot_token=_effective_telegram_bot_token,
        )
    )
except ImportError as _tg_imp_err:
    _gateway_log.error(
        "Telegram webhook router omitido (import falló). Los POST /api/v1/telegram/* devolverán 404: %s",
        _tg_imp_err,
        exc_info=True,
    )

try:
    from routers.discord_inbound_webhook import build_discord_interactions_router

    app.include_router(
        build_discord_interactions_router(
            invoke_agent_chat=_invoke_chat,
            app_state_holder=app.state,
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

try:
    from routers.admin import router as admin_router
    app.include_router(admin_router)
except ImportError as _admin_imp_err:
    _gateway_log.error("Admin router omitido: %s", _admin_imp_err)

try:
    from duckclaw.graphs.novnc_routes import build_novnc_router

    app.include_router(
        build_novnc_router(),
        prefix="/api/v1/sandbox/novnc",
        tags=["sandbox-novnc"],
    )
except ImportError:
    pass
