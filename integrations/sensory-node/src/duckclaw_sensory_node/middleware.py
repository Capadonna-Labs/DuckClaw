"""Tailnet-only access middleware (defense in depth)."""

from __future__ import annotations

import ipaddress
import logging
import os

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

_log = logging.getLogger("duckclaw.sensory.middleware")

_TAILSCALE_NET = ipaddress.ip_network("100.64.0.0/10")


def _tailscale_only_enabled() -> bool:
    return (os.environ.get("DUCKCLAW_SENSORY_TAILSCALE_ONLY") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _client_in_tailnet(request: Request) -> bool:
    if request.client is None:
        return False
    host = (request.client.host or "").strip()
    if not host:
        return False
    if host in ("127.0.0.1", "::1", "localhost"):
        return False
    try:
        return ipaddress.ip_address(host) in _TAILSCALE_NET
    except ValueError:
        return False


class TailscaleOnlyMiddleware(BaseHTTPMiddleware):
    """Reject requests whose source IP is outside the Tailscale CGNAT range."""

    async def dispatch(self, request: Request, call_next) -> Response:
        if not _tailscale_only_enabled():
            return await call_next(request)
        if request.url.path == "/health":
            return await call_next(request)
        if not _client_in_tailnet(request):
            _log.warning("rejected non-tailnet client host=%s path=%s", request.client.host if request.client else "-", request.url.path)
            return JSONResponse(status_code=403, content={"detail": "Tailscale-only access"})
        return await call_next(request)
