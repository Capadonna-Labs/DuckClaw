"""Router compartido del dominio admin playground."""

from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(tags=["admin-playground-chat"])

from routers.admin_domains.playground import (  # noqa: E402, F401
    chat_routes,
    config_routes,
    conversations_routes,
)
