"""Importar FastAPI app del API Gateway sin colisión con services/db-writer/main.py."""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi import FastAPI

_REPO_ROOT = Path(__file__).resolve().parents[1]
_GATEWAY_DIR = _REPO_ROOT / "services" / "api-gateway"

_GATEWAY_MODULES_TO_RELOAD = (
    "main",
    "routers.telegram_inbound_webhook",
    "routers.admin",
    "routers.discord_inbound_webhook",
)


def ensure_gateway_on_sys_path() -> Path:
    """Gateway siempre en sys.path[0] (db-writer también tiene main.py)."""
    gw_s = str(_GATEWAY_DIR)
    while gw_s in sys.path:
        sys.path.remove(gw_s)
    sys.path.insert(0, gw_s)
    return _GATEWAY_DIR


def load_gateway_app() -> FastAPI:
    ensure_gateway_on_sys_path()
    for mod in _GATEWAY_MODULES_TO_RELOAD:
        sys.modules.pop(mod, None)
    from main import app as gateway_app

    return gateway_app
