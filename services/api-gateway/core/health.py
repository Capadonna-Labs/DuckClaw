"""Gateway root and health endpoints: service index, liveness, system probes."""

from __future__ import annotations

import os
import shutil
import subprocess

from fastapi import APIRouter, FastAPI, Request

from core.config import settings
from duckclaw.ops.gateway_health_metrics import collect_gateway_health_metrics

router = APIRouter(tags=["health"])


def telegram_path_route_count(app: FastAPI) -> int:
    """Útil cuando ``:8000`` devuelve 404 en multiplex: proceso equivocado suele tener 0 rutas telegram."""
    n = 0
    for r in app.routes:
        p = getattr(r, "path", "") or ""
        if p.startswith("/api/v1/telegram/"):
            n += 1
    return n


@router.get("/")
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


@router.get("/health")
async def health(request: Request):
    return {
        "status": "ok",
        "service": "api-gateway",
        "telegram_path_routes_registered": telegram_path_route_count(request.app),
        "metrics": collect_gateway_health_metrics(),
    }


@router.get("/api/v1/system/health")
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
