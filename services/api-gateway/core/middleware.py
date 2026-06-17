"""HTTP middleware del gateway: observabilidad, Tailscale auth, probe Telegram."""

from __future__ import annotations

import logging
import os
import re

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from duckclaw.utils.logger import reset_log_context, set_log_context

_gateway_log = logging.getLogger("duckclaw.gateway")


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
    # Último registrado = primero en la cadena entrante: ver HTTP antes de auth/CORS internos.
    app.middleware("http")(telegram_http_ingress_probe_middleware)
