"""Messages: direct messages and groups between console users, like any messaging app (Historial > Mensajes).

People write from the admin; a coding agent that works for one of them (Claude Code with the repo cloned) writes with the same admin API,
as that person (``X-Duckclaw-Actor``) and an ``author_label`` such as "Claude (Juan)" — ``scripts/messages_cli.py``.
Reads open the hub read-only and only return channels the actor is a member of; writes are typed commands through the DB-Writer, which
checks membership again. A new message sends a Web Push to the other members' devices only.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key

router = APIRouter(prefix="/messages", tags=["admin-messages"])


class ChannelBody(BaseModel):
    kind: Literal["dm", "group"] = "group"
    name: str = Field(default="", max_length=80)
    members: list[str] = Field(default_factory=list, max_length=50)


class MessageBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=8000)
    author_label: str = Field(default="", max_length=60)


def _me(actor: str) -> str:
    me = (actor or "").strip().lower()
    if "@" not in me:
        raise problem(401, "Sin identidad", "X-Duckclaw-Actor debe ser el correo de la persona")
    return me


async def _read(sql: str, params: list[Any]) -> list[Any]:
    from core.admin_identity import open_gateway_db

    def _sync() -> list[Any]:
        with open_gateway_db(read_only=True) as db:
            res = db.execute(sql, params)
            return list(res.fetchall()) if hasattr(res, "fetchall") else list(res or [])

    return await asyncio.to_thread(_sync)


def _enqueue(command: Any) -> str:
    from duckclaw.gateway_enqueue import enqueue_admin_command

    return enqueue_admin_command(command)


async def _channel(channel_id: str, me: str) -> dict[str, Any]:
    rows = await _read("SELECT channel_id, kind, name, members_json FROM main.admin_channels WHERE channel_id = ?", [channel_id])
    members = json.loads(rows[0][3] or "[]") if rows else []
    if not rows or me not in members:
        raise problem(404, "Canal no encontrado", channel_id)
    return {"id": rows[0][0], "kind": rows[0][1], "name": rows[0][2], "members": members}


@router.get("/people", dependencies=[Depends(require_admin_key)])
async def people(actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    rows = await _read("SELECT lower(email), nombre FROM main.admin_console_users WHERE coalesce(active, true) AND lower(email) <> ? ORDER BY nombre",
                       [_me(actor)])
    return {"people": [{"email": e, "name": n} for e, n in rows]}


@router.get("/channels", dependencies=[Depends(require_admin_key)])
async def list_channels(actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    me = _me(actor)
    # ponytail: membership via LIKE on the JSON list then an exact check; a members table if channels ever number in the thousands.
    rows = await _read(
        "SELECT c.channel_id, c.kind, c.name, c.members_json, c.updated_at, "
        "(SELECT arg_max(coalesce(nullif(m.author_label, ''), m.author_email) || ': ' || left(m.body, 140), m.created_at) "
        " FROM main.admin_channel_messages m WHERE m.channel_id = c.channel_id), "
        "(SELECT count(*) FROM main.admin_channel_messages m WHERE m.channel_id = c.channel_id) "
        "FROM main.admin_channels c WHERE c.members_json LIKE ? ORDER BY c.updated_at DESC LIMIT 200",
        [f'%"{me}"%'],
    )
    names = {e: n for e, n in await _read("SELECT lower(email), nombre FROM main.admin_console_users", [])}
    out = []
    for cid, kind, name, members_json, updated, preview, count in rows:
        members = json.loads(members_json or "[]")
        if me not in members:
            continue
        title = name or ", ".join(names.get(m, m) for m in members if m != me) or "Solo tú"
        out.append({"id": cid, "kind": kind, "name": title, "members": members, "updated_at": str(updated),
                    "last_message_preview": preview or "", "message_count": int(count or 0)})
    return {"channels": out, "me": me}


@router.post("/channels", dependencies=[Depends(require_admin_key)])
async def create_channel(body: ChannelBody, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    from duckclaw.write_commands import CreateChannelCommand

    me = _me(actor)
    members = sorted({m.strip().lower() for m in body.members if m.strip()} | {me})
    if body.kind == "dm":
        if len(members) != 2:
            raise problem(400, "Mensaje directo", "elige exactamente una persona")
        existing = await _read("SELECT channel_id FROM main.admin_channels WHERE kind = 'dm' AND members_json = ?", [json.dumps(members)])
        if existing:   # one DM per pair: reopen it
            return {"ok": True, "channel_id": existing[0][0], "existing": True}
    elif not body.name.strip():
        raise problem(400, "Grupo", "el grupo necesita un nombre")
    try:
        command = CreateChannelCommand(actor_email=me, kind=body.kind, name=body.name.strip(), members=members)
        task_id = _enqueue(command)
    except ValueError as exc:
        raise problem(400, "Canal inválido", str(exc)) from exc
    return {"ok": True, "task_id": task_id, "channel_id": command.channel_id}


@router.get("/channels/{channel_id}", dependencies=[Depends(require_admin_key)])
async def read_channel(
    channel_id: str, since: str = Query(default=""), limit: int = Query(default=200, ge=1, le=500), actor: str = Depends(actor_from_header)
) -> dict[str, Any]:
    me = _me(actor)
    channel = await _channel(channel_id, me)
    rows = await _read(
        "SELECT * FROM (SELECT message_id, author_email, author_label, body, created_at FROM main.admin_channel_messages "
        "WHERE channel_id = ? AND (? = '' OR created_at > TRY_CAST(? AS TIMESTAMP)) ORDER BY created_at DESC LIMIT ?) ORDER BY created_at",
        [channel_id, since, since, limit],
    )
    names = {e: n for e, n in await _read("SELECT lower(email), nombre FROM main.admin_console_users", [])}
    channel["messages"] = [{"id": i, "author_email": a, "author": lbl or names.get(a, a), "agent": bool(lbl), "body": b,
                            "created_at": str(t), "mine": a == me} for i, a, lbl, b, t in rows]
    return channel


@router.post("/channels/{channel_id}", dependencies=[Depends(require_admin_key)])
async def post_message(channel_id: str, body: MessageBody, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    from duckclaw.write_commands import PostChannelMessageCommand

    me = _me(actor)
    channel = await _channel(channel_id, me)
    command = PostChannelMessageCommand(actor_email=me, channel_id=channel_id, body=body.body, author_label=body.author_label.strip())
    task_id = _enqueue(command)
    others = [m for m in channel["members"] if m != me]
    if others:
        asyncio.get_running_loop().run_in_executor(None, _notify, others, channel, me, body)
    return {"ok": True, "task_id": task_id, "message_id": command.message_id}


def _notify(others: list[str], channel: dict[str, Any], me: str, body: MessageBody) -> None:
    import logging

    try:
        from duckclaw.gateway_db import get_gateway_db_path
        from duckclaw.web_push import list_web_push_subscriptions, send_web_push_notifications

        tag = f"duckclaw-messages-{channel['id']}"
        subs = list_web_push_subscriptions(str(get_gateway_db_path()), tag, owners=others)
        who = body.author_label.strip() or me.split("@")[0]
        title = who if channel["kind"] == "dm" else f"{channel['name'] or 'Grupo'} · {who}"
        send_web_push_notifications(subs, title=title, body=body.body[:300], url=f"/playground?channel={channel['id']}", tag=tag)
    except Exception as exc:  # noqa: BLE001 - the message is stored; the push is best effort
        logging.getLogger(__name__).warning("messages: push no enviado canal=%s: %s", channel.get("id"), exc)
