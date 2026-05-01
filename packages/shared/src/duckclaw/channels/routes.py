"""Parseo de `DUCKCLAW_CHANNEL_ROUTES` (JSON)."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

_log = logging.getLogger(__name__)

_ENV_ROUTES = "DUCKCLAW_CHANNEL_ROUTES"


@dataclass(frozen=True)
class ChannelRouteBinding:
    channel: str
    match: dict[str, Any]
    worker_id: str
    tenant_id: str
    bot_token_env: str
    vault_db_env: str


def load_channel_route_bindings() -> list[ChannelRouteBinding]:
    raw = (os.environ.get(_ENV_ROUTES) or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        _log.warning("%s JSON inválido: %s", _ENV_ROUTES, exc)
        return []
    if not isinstance(data, list):
        _log.warning("%s debe ser lista JSON", _ENV_ROUTES)
        return []
    out: list[ChannelRouteBinding] = []
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            continue
        d = item
        ch = str(d.get("channel") or "").strip().lower()
        match = d.get("match")
        if not isinstance(match, dict):
            match = {}
        wid = str(d.get("worker_id") or "").strip()
        tenant = str(d.get("tenant_id") or "default").strip() or "default"
        bot_env = str(d.get("bot_token_env") or "").strip()
        vault_env = str(d.get("vault_db_env") or "").strip()
        if not ch or not wid or not bot_env:
            _log.warning("%s[%s]: channel, worker_id y bot_token_env obligatorios", _ENV_ROUTES, i)
            continue
        out.append(
            ChannelRouteBinding(
                channel=ch,
                match=match,
                worker_id=wid,
                tenant_id=tenant,
                bot_token_env=bot_env,
                vault_db_env=vault_env,
            )
        )
    return out


def resolve_discord_route(*, guild_id: str | None) -> ChannelRouteBinding | None:
    gid = (guild_id or "").strip()
    for b in load_channel_route_bindings():
        if b.channel != "discord":
            continue
        m_gid = str(b.match.get("guild_id") or "").strip()
        if m_gid and gid and m_gid == gid:
            return b
    return None
