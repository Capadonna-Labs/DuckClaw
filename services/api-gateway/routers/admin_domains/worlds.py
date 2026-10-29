"""Worlds: self-hosted worlds (a game server, say) and their bots.

DuckClaw does not host a world or start a bot: it stores what the person who runs the extension configures here and shows the status that the runner
reports. The runner (an extension process, anywhere) reads ``GET /worlds``, reports with ``POST /worlds/bots/status`` and may send deliberate turns to the bot's
worker with ``POST /worlds/think`` (``worlds_think.py``), with the admin key or with its own limited ``X-Worlds-Runner-Key`` (``DUCKCLAW_WORLDS_RUNNER_KEY``), which
opens only those three calls.
Every mutation is a typed command through the DB-Writer queue; reads open the hub read-only, scoped to tenant + actor.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import os
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key

router = APIRouter(prefix="/worlds", tags=["admin-worlds"])


def require_admin_or_runner_key(
    x_admin_key: str | None = Header(None, alias="X-Admin-Key"),
    x_runner_key: str | None = Header(None, alias="X-Worlds-Runner-Key"),
) -> None:
    """A runner holds a key that opens only the two calls it needs (read its config, report status), never the whole admin API.
    ``DUCKCLAW_WORLDS_RUNNER_KEY`` unset disables it: only the admin key works."""
    runner = (os.environ.get("DUCKCLAW_WORLDS_RUNNER_KEY") or "").strip()
    if runner and x_runner_key and hmac.compare_digest(x_runner_key.strip().encode(), runner.encode()):
        return
    require_admin_key(x_admin_key)


def _stale_after_s() -> int:
    try:
        return max(10, int(os.environ.get("DUCKCLAW_WORLD_BOT_STALE_S") or "90"))
    except ValueError:
        return 90


class WorldBody(BaseModel):
    id: str | None = None
    name: str | None = Field(default=None, max_length=80)
    kind: str | None = None
    host: str | None = None
    port: int | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None


class BotBody(BaseModel):
    id: str | None = None
    world_id: str | None = None
    name: str | None = Field(default=None, max_length=48)
    worker_id: str | None = None
    settings: dict[str, Any] | None = None
    enabled: bool | None = None


class StatusBody(BaseModel):
    bot_id: str = Field(..., min_length=1)
    status: Literal["starting", "online", "offline", "error"]
    detail: str = Field(default="", max_length=300)


def _json_obj(raw: Any) -> dict[str, Any]:
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}


def _rows(result: Any) -> list[Any]:
    if hasattr(result, "fetchall"):
        return list(result.fetchall())
    return list(result) if isinstance(result, list) else []


def _world(row: tuple[Any, ...]) -> dict[str, Any]:
    world_id, name, kind, host, port, config_json, enabled, created_at, updated_at = row
    return {"id": str(world_id), "name": str(name), "kind": str(kind), "host": str(host or ""), "port": int(port) if port is not None else None,
            "config": _json_obj(config_json), "enabled": bool(enabled), "created_at": str(created_at), "updated_at": str(updated_at), "bots": []}


def _bot(row: tuple[Any, ...], stale_after_s: int) -> dict[str, Any]:
    bot_id, world_id, name, worker_id, settings_json, enabled, status, detail, last_seen, age_s, created_at, updated_at = row
    reported = str(status or "unknown")
    # A runner that stopped reporting is offline whatever it last said: the status is only as fresh as its last report.
    effective = "offline" if reported in ("online", "starting") and (age_s is None or int(age_s) > stale_after_s) else reported
    return {"id": str(bot_id), "world_id": str(world_id), "name": str(name), "worker_id": str(worker_id or ""), "settings": _json_obj(settings_json),
            "enabled": bool(enabled), "status": effective, "reported_status": reported, "status_detail": str(detail or ""),
            "last_seen_at": str(last_seen) if last_seen is not None else None, "seconds_since_report": int(age_s) if age_s is not None else None,
            "created_at": str(created_at), "updated_at": str(updated_at)}


async def _profile(actor: str) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    def _sync() -> dict[str, Any]:
        with open_gateway_db(read_only=True) as db:
            return ensure_profile_for_user(db, email=actor)

    return await asyncio.to_thread(_sync)


def _enqueue(command: Any) -> str:
    from duckclaw.gateway_enqueue import enqueue_admin_command

    return enqueue_admin_command(command)


async def _read(sql: str, params: list[Any]) -> list[Any]:
    from core.admin_identity import open_gateway_db

    def _sync() -> list[Any]:
        with open_gateway_db(read_only=True) as db:
            return _rows(db.execute(sql, params))

    return await asyncio.to_thread(_sync)


_WORLD_COLS = "world_id, name, kind, host, port, config_json, enabled, created_at, updated_at"
_BOT_COLS = ("bot_id, world_id, name, worker_id, settings_json, enabled, status, status_detail, last_seen_at, "
             "date_diff('second', last_seen_at, CAST(CURRENT_TIMESTAMP AS TIMESTAMP)) AS age_s, created_at, updated_at")


async def _existing_world(profile: dict[str, Any], world_id: str) -> dict[str, Any] | None:
    rows = await _read(f"SELECT {_WORLD_COLS} FROM main.admin_worlds WHERE world_id = ? AND tenant_id = ? AND actor_email = ?",
                       [world_id, profile["tenant_id"], profile["email"]])
    return _world(rows[0]) if rows else None


async def _existing_bot(profile: dict[str, Any], bot_id: str) -> dict[str, Any] | None:
    rows = await _read(f"SELECT {_BOT_COLS} FROM main.admin_world_bots WHERE bot_id = ? AND tenant_id = ? AND actor_email = ?",
                       [bot_id, profile["tenant_id"], profile["email"]])
    return _bot(rows[0], _stale_after_s()) if rows else None


@router.get("", dependencies=[Depends(require_admin_or_runner_key)])
async def list_worlds(actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    profile = await _profile(actor)
    scope = [profile["tenant_id"], profile["email"]]
    worlds = [_world(r) for r in await _read(f"SELECT {_WORLD_COLS} FROM main.admin_worlds WHERE tenant_id = ? AND actor_email = ? ORDER BY created_at", scope)]
    by_id = {w["id"]: w for w in worlds}
    for row in await _read(f"SELECT {_BOT_COLS} FROM main.admin_world_bots WHERE tenant_id = ? AND actor_email = ? ORDER BY created_at", scope):
        bot = _bot(row, _stale_after_s())
        if bot["world_id"] in by_id:
            by_id[bot["world_id"]]["bots"].append(bot)
    return {"worlds": worlds, "stale_after_s": _stale_after_s()}


@router.post("", dependencies=[Depends(require_admin_key)])
async def create_world(body: WorldBody, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    from duckclaw.write_commands import UpsertWorldCommand

    profile = await _profile(actor)
    if not (body.name or "").strip():
        raise problem(400, "name requerido", "worlds")
    try:
        command = UpsertWorldCommand(tenant_id=profile["tenant_id"], actor_email=profile["email"], name=body.name.strip(),
                                     **{k: v for k, v in body.model_dump(exclude={"id", "name"}).items() if v is not None})
        task_id = _enqueue(command)
    except ValueError as exc:
        raise problem(400, "Mundo inválido", str(exc)) from exc
    return {"ok": True, "task_id": task_id, "world_id": command.world_id}


@router.patch("", dependencies=[Depends(require_admin_key)])
async def update_world(body: WorldBody, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    from duckclaw.write_commands import UpsertWorldCommand

    profile = await _profile(actor)
    existing = await _existing_world(profile, body.id or "")
    if not existing:
        raise problem(404, "Mundo no encontrado", body.id or "")
    merged = {k: existing[k] for k in ("name", "kind", "host", "port", "config", "enabled")}
    merged.update({k: v for k, v in body.model_dump(exclude={"id"}).items() if k in body.model_fields_set and (v is not None or k == "port")})
    try:
        command = UpsertWorldCommand(tenant_id=profile["tenant_id"], actor_email=profile["email"], world_id=existing["id"], **merged)
        task_id = _enqueue(command)
    except ValueError as exc:
        raise problem(400, "Mundo inválido", str(exc)) from exc
    return {"ok": True, "task_id": task_id, "world_id": existing["id"]}


@router.delete("", dependencies=[Depends(require_admin_key)])
async def delete_world(id: str = Query(..., min_length=1), actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    from duckclaw.write_commands import DeleteWorldCommand

    profile = await _profile(actor)
    if not await _existing_world(profile, id):
        raise problem(404, "Mundo no encontrado", id)
    return {"ok": True, "task_id": _enqueue(DeleteWorldCommand(tenant_id=profile["tenant_id"], actor_email=profile["email"], world_id=id))}


@router.post("/bots", dependencies=[Depends(require_admin_key)])
async def create_bot(body: BotBody, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    from duckclaw.write_commands import UpsertWorldBotCommand

    profile = await _profile(actor)
    if not (body.world_id or "").strip() or not (body.name or "").strip():
        raise problem(400, "world_id y name requeridos", "worlds")
    if not await _existing_world(profile, body.world_id):
        raise problem(404, "Mundo no encontrado", body.world_id)
    try:
        command = UpsertWorldBotCommand(tenant_id=profile["tenant_id"], actor_email=profile["email"], world_id=body.world_id, name=body.name.strip(),
                                        **{k: v for k, v in body.model_dump(exclude={"id", "world_id", "name"}).items() if v is not None})
        task_id = _enqueue(command)
    except ValueError as exc:
        raise problem(400, "Bot inválido", str(exc)) from exc
    return {"ok": True, "task_id": task_id, "bot_id": command.bot_id}


@router.patch("/bots", dependencies=[Depends(require_admin_key)])
async def update_bot(body: BotBody, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    from duckclaw.write_commands import UpsertWorldBotCommand

    profile = await _profile(actor)
    existing = await _existing_bot(profile, body.id or "")
    if not existing:
        raise problem(404, "Bot no encontrado", body.id or "")
    merged = {k: existing[k] for k in ("world_id", "name", "worker_id", "settings", "enabled")}
    merged.update({k: v for k, v in body.model_dump(exclude={"id"}).items() if k in body.model_fields_set and v is not None})
    if merged["world_id"] != existing["world_id"] and not await _existing_world(profile, merged["world_id"]):
        raise problem(404, "Mundo no encontrado", merged["world_id"])
    try:
        command = UpsertWorldBotCommand(tenant_id=profile["tenant_id"], actor_email=profile["email"], bot_id=existing["id"], **merged)
        task_id = _enqueue(command)
    except ValueError as exc:
        raise problem(400, "Bot inválido", str(exc)) from exc
    return {"ok": True, "task_id": task_id, "bot_id": existing["id"]}


@router.delete("/bots", dependencies=[Depends(require_admin_key)])
async def delete_bot(id: str = Query(..., min_length=1), actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    from duckclaw.write_commands import DeleteWorldBotCommand

    profile = await _profile(actor)
    if not await _existing_bot(profile, id):
        raise problem(404, "Bot no encontrado", id)
    return {"ok": True, "task_id": _enqueue(DeleteWorldBotCommand(tenant_id=profile["tenant_id"], actor_email=profile["email"], bot_id=id))}


@router.post("/bots/status", dependencies=[Depends(require_admin_or_runner_key)])
async def report_bot_status(body: StatusBody, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    """The runner's report (server to server, with the admin key and the owner's actor header). Fire-and-forget like every write."""
    from duckclaw.write_commands import ReportWorldBotStatusCommand

    profile = await _profile(actor)
    if not await _existing_bot(profile, body.bot_id):
        raise problem(404, "Bot no encontrado", body.bot_id)
    return {"ok": True, "task_id": _enqueue(ReportWorldBotStatusCommand(tenant_id=profile["tenant_id"], actor_email=profile["email"],
                                                                         bot_id=body.bot_id, status=body.status, detail=body.detail))}
