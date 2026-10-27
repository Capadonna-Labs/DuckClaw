"""HTTP middleware del gateway: observabilidad, Tailscale auth, probe Telegram."""

from __future__ import annotations

import ipaddress
import logging
import os
import re
import time

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from duckclaw.utils.logger import reset_log_context, set_log_context

_gateway_log = logging.getLogger("duckclaw.gateway")


# Browsers on this machine only: the admin BFF calls the gateway server-side (no CORS), so the usual case needs no entry.
# The desktop shell (Tauri) is the other legitimate browser origin.
DEFAULT_CORS_ORIGINS = [
    "http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:3001", "http://127.0.0.1:3001",
    "http://localhost:8000", "http://127.0.0.1:8000", "tauri://localhost", "http://tauri.localhost", "https://tauri.localhost",
]


def cors_settings() -> dict:
    """CORSMiddleware kwargs from ``DUCKCLAW_CORS_ORIGINS`` (comma-separated origins; unset = local defaults above).

    An explicit ``*`` opens every origin but drops credentials: browsers refuse that pair, and Starlette would otherwise echo any Origin back with cookies allowed.
    """
    origins = [o.strip().rstrip("/") for o in (os.environ.get("DUCKCLAW_CORS_ORIGINS") or "").split(",") if o.strip()] or list(DEFAULT_CORS_ORIGINS)
    wildcard = "*" in origins
    return {
        "allow_origins": ["*"] if wildcard else origins,
        "allow_credentials": not wildcard,
        "allow_methods": ["*"],
        "allow_headers": ["*"],
    }


def _env_int(name: str, default: int) -> int:
    try:
        return int((os.environ.get(name) or "").strip() or default)
    except ValueError:
        return default


# ponytail: one fixed window per public IP, in this process's memory (resets on restart, not shared between workers).
# Upgrade path: a Redis INCR like core.admin_auth.check_ip_rate_limit if the gateway ever runs several workers.
_RATE_WINDOWS: dict[str, tuple[float, int]] = {}


def _public_client_ip(request: Request) -> str | None:
    """The caller's IP when it is a public address; None for loopback, private networks, Tailscale (CGNAT) and unparsable hosts, which are trusted (the BFF and the tailnet)."""
    host = request.client.host if request.client else ""
    try:
        return host if ipaddress.ip_address(host).is_global else None
    except ValueError:
        return None


async def request_limits_middleware(request: Request, call_next):
    """Two cheap guards for a gateway that is reachable from the internet: a body-size cap (413) and a per-IP request rate (429), both only for public callers.

    ``DUCKCLAW_MAX_BODY_MB`` (default 50) and ``DUCKCLAW_RATE_LIMIT_PER_MIN`` (default 300); 0 turns each off.
    The size check reads Content-Length, so a chunked body is not caught here (the reverse proxy or uvicorn limits it).
    """
    ip = _public_client_ip(request)
    if ip is None or request.url.path == "/health":
        return await call_next(request)
    max_mb = _env_int("DUCKCLAW_MAX_BODY_MB", 50)
    declared = (request.headers.get("content-length") or "").strip()
    if max_mb > 0 and declared.isdigit() and int(declared) > max_mb * 1024 * 1024:
        return JSONResponse(status_code=413, content={"detail": f"Cuerpo mayor a {max_mb} MB"})
    limit = _env_int("DUCKCLAW_RATE_LIMIT_PER_MIN", 300)
    if limit > 0:
        now = time.monotonic()
        start, count = _RATE_WINDOWS.get(ip, (now, 0))
        if now - start >= 60:
            start, count = now, 0
            if len(_RATE_WINDOWS) > 10_000:   # bounded memory under a spread-out scan
                _RATE_WINDOWS.clear()
        _RATE_WINDOWS[ip] = (start, count + 1)
        if count + 1 > limit:
            return JSONResponse(status_code=429, content={"detail": "Demasiadas solicitudes"}, headers={"Retry-After": "60"})
    return await call_next(request)


async def observability_context_middleware(request: Request, call_next):
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


async def tailscale_auth_middleware(request: Request, call_next):
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


async def telegram_http_ingress_probe_middleware(request: Request, call_next):
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


def register_gateway_middleware(app: FastAPI) -> None:
    """Monta middleware HTTP en el orden de cadena esperado por main legacy."""
    app.middleware("http")(observability_context_middleware)
    app.middleware("http")(tailscale_auth_middleware)
    app.middleware("http")(request_limits_middleware)
    # Último registrado = primero en la cadena entrante: ver HTTP antes de auth/CORS internos.
    app.middleware("http")(telegram_http_ingress_probe_middleware)
