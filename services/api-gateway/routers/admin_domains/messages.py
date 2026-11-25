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


# ---------------------------------------------------------------------------
# Shared by the admin routes below and by routers/federation.py (a contact of another instance).
# ---------------------------------------------------------------------------


async def _names() -> dict[str, str]:
    rows = await _read("SELECT lower(email), nombre FROM main.admin_console_users", [])
    rows += await _read("SELECT remote_email, remote_name FROM main.admin_contacts WHERE remote_name <> ''", [])
    return {e: n for e, n in rows}


async def _channel(channel_id: str, me: str) -> dict[str, Any]:
    rows = await _read("SELECT channel_id, kind, name, members_json FROM main.admin_channels WHERE channel_id = ?", [channel_id])
    members = json.loads(rows[0][3] or "[]") if rows else []
    if not rows or me not in members:
        raise problem(404, "Canal no encontrado", channel_id)
    return {"id": rows[0][0], "kind": rows[0][1], "name": rows[0][2], "members": members}


async def channels_for(me: str) -> list[dict[str, Any]]:
    # ponytail: membership via LIKE on the JSON list then an exact check; a members table if channels ever number in the thousands.
    rows = await _read(
        "SELECT c.channel_id, c.kind, c.name, c.members_json, c.updated_at, "
        "(SELECT arg_max(coalesce(nullif(m.author_label, ''), m.author_email) || ': ' || left(m.body, 140), m.created_at) "
        " FROM main.admin_channel_messages m WHERE m.channel_id = c.channel_id), "
        "(SELECT count(*) FROM main.admin_channel_messages m WHERE m.channel_id = c.channel_id) "
        "FROM main.admin_channels c WHERE c.members_json LIKE ? ORDER BY c.updated_at DESC LIMIT 200",
        [f'%"{me}"%'],
    )
    names = await _names()
    out = []
    for cid, kind, name, members_json, updated, preview, count in rows:
        members = json.loads(members_json or "[]")
        if me not in members:
            continue
        title = name or ", ".join(names.get(m, m) for m in members if m != me) or "Solo tú"
        out.append({"id": cid, "kind": kind, "name": title, "members": members, "updated_at": str(updated),
                    "last_message_preview": preview or "", "message_count": int(count or 0)})
    return out


async def channel_with_messages(channel_id: str, me: str, since: str = "", limit: int = 200) -> dict[str, Any]:
    channel = await _channel(channel_id, me)
    rows = await _read(
        "SELECT * FROM (SELECT message_id, author_email, author_label, body, created_at FROM main.admin_channel_messages "
        "WHERE channel_id = ? AND (? = '' OR created_at > TRY_CAST(? AS TIMESTAMP)) ORDER BY created_at DESC LIMIT ?) ORDER BY created_at",
        [channel_id, since, since, limit],
    )
    names = await _names()
    if not channel["name"]:
        channel["name"] = ", ".join(names.get(m, m) for m in channel["members"] if m != me)
    channel["messages"] = [{"id": i, "author_email": a, "author": lbl or names.get(a, a), "agent": bool(lbl), "body": b,
                            "created_at": str(t), "mine": a == me} for i, a, lbl, b, t in rows]
    return channel


async def post_as(channel_id: str, me: str, text: str, label: str = "") -> dict[str, Any]:
    from duckclaw.write_commands import PostChannelMessageCommand

    channel = await _channel(channel_id, me)
    command = PostChannelMessageCommand(actor_email=me, channel_id=channel_id, body=text, author_label=label.strip())
    task_id = _enqueue(command)
    others = [m for m in channel["members"] if m != me]
    if others:
        asyncio.get_running_loop().run_in_executor(None, _notify, others, channel, me, text, label)
    return {"ok": True, "task_id": task_id, "message_id": command.message_id}


def _notify(others: list[str], channel: dict[str, Any], me: str, text: str, label: str) -> None:
    import logging

    try:
        from duckclaw.gateway_db import get_gateway_db_path
        from duckclaw.web_push import list_web_push_subscriptions, send_web_push_notifications

        tag = f"duckclaw-messages-{channel['id']}"
        subs = list_web_push_subscriptions(str(get_gateway_db_path()), tag, owners=others)   # only local members have devices here
        who = label.strip() or me.split("@")[0]
        title = who if channel["kind"] == "dm" else f"{channel['name'] or 'Grupo'} · {who}"
        send_web_push_notifications(subs, title=title, body=text[:300], url=f"/playground?channel={channel['id']}", tag=tag)
    except Exception as exc:  # noqa: BLE001 - the message is stored; the push is best effort
        logging.getLogger(__name__).warning("messages: push no enviado canal=%s: %s", channel.get("id"), exc)


# ---------------------------------------------------------------------------
# Channels hosted by another instance (a "guest" contact): ids "fed~<contact_id>~<channel_id>", proxied with the contact token.
# ---------------------------------------------------------------------------

_FED = "fed~"


async def _guest_contacts(me: str) -> list[dict[str, Any]]:
    rows = await _read("SELECT contact_id, remote_url, token, remote_email, remote_name FROM main.admin_contacts "
                       "WHERE role = 'guest' AND owner_email = ?", [me])
    return [{"id": r[0], "url": r[1], "token": r[2], "email": r[3], "name": r[4]} for r in rows]


async def _remote(contact: dict[str, Any], method: str, path: str, body: dict | None = None) -> dict[str, Any]:
    import httpx

    async with httpx.AsyncClient(timeout=8.0) as client:
        r = await client.request(method, f"{contact['url']}/api/v1/federation{path}", json=body,
                                 headers={"Authorization": f"Bearer {contact['token']}"})
    if r.status_code >= 400:
        raise problem(502 if r.status_code >= 500 else r.status_code, "Instancia remota",
                      f"{contact['name'] or contact['url']}: HTTP {r.status_code}")
    return r.json()


async def _fed_target(channel_id: str, me: str) -> tuple[dict[str, Any], str]:
    _, contact_id, remote_id = (channel_id.split("~", 2) + ["", ""])[:3]
    contact = next((c for c in await _guest_contacts(me) if c["id"] == contact_id), None)
    if not contact or not remote_id:
        raise problem(404, "Canal no encontrado", channel_id)
    return contact, remote_id


def _fed_id(contact: dict[str, Any], channel_id: str) -> str:
    return f"{_FED}{contact['id']}~{channel_id}"


# ---------------------------------------------------------------------------
# Admin routes (the BFF passes the console user as X-Duckclaw-Actor)
# ---------------------------------------------------------------------------


@router.get("/people", dependencies=[Depends(require_admin_key)])
async def people(actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    me = _me(actor)
    rows = await _read("SELECT lower(email), nombre FROM main.admin_console_users WHERE coalesce(active, true) AND lower(email) <> ? ORDER BY nombre",
                       [me])
    out = [{"email": e, "name": n, "remote": False} for e, n in rows]
    for e, n in await _read("SELECT remote_email, remote_name FROM main.admin_contacts WHERE owner_email = ? ORDER BY remote_name", [me]):
        out.append({"email": e, "name": n or e, "remote": True})
    return {"people": out}


@router.get("/channels", dependencies=[Depends(require_admin_key)])
async def list_channels(actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    me = _me(actor)
    out = await channels_for(me)
    for contact in await _guest_contacts(me):   # channels the other instance hosts; one unreachable contact does not hide the rest
        try:
            remote = await _remote(contact, "GET", "/channels")
        except Exception:  # noqa: BLE001
            continue
        for c in remote.get("channels", []):
            out.append({**c, "id": _fed_id(contact, c["id"]), "remote": contact["name"] or contact["url"]})
    out.sort(key=lambda c: str(c.get("updated_at") or ""), reverse=True)
    return {"channels": out, "me": me}


@router.post("/channels", dependencies=[Depends(require_admin_key)])
async def create_channel(body: ChannelBody, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    from duckclaw.write_commands import CreateChannelCommand

    me = _me(actor)
    members = sorted({m.strip().lower() for m in body.members if m.strip()} | {me})
    guests = {c["email"]: c for c in await _guest_contacts(me)}
    remote = [m for m in members if m in guests]
    if remote:   # a contact of another instance: its instance hosts the DM
        if body.kind != "dm" or len(members) != 2:
            raise problem(400, "Contacto de otra instancia", "con un contacto de otra instancia solo se abre un mensaje directo")
        contact = guests[remote[0]]
        r = await _remote(contact, "POST", "/channels", {"kind": "dm"})
        return {"ok": True, "channel_id": _fed_id(contact, r["channel_id"]), "existing": r.get("existing", False)}
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
    if channel_id.startswith(_FED):
        contact, remote_id = await _fed_target(channel_id, me)
        ch = await _remote(contact, "GET", f"/channels/{remote_id}?since={since}")
        return {**ch, "id": channel_id}
    return await channel_with_messages(channel_id, me, since, limit)


@router.post("/channels/{channel_id}", dependencies=[Depends(require_admin_key)])
async def post_message(channel_id: str, body: MessageBody, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    me = _me(actor)
    if channel_id.startswith(_FED):
        contact, remote_id = await _fed_target(channel_id, me)
        return await _remote(contact, "POST", f"/channels/{remote_id}", {"body": body.body, "author_label": body.author_label})
    return await post_as(channel_id, me, body.body, body.author_label)


