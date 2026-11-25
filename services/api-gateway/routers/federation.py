"""Federation between DuckClaw instances: contacts and the messages they share.

The instance that sends an invitation hosts the shared channels. The invited instance redeems the code at ``POST /federation/accept``
(authenticated by the invitation secret, single use, expires) and gets a contact token; every later call carries it as
``Authorization: Bearer``. The host keeps only its sha256 and resolves it to the contact's email, which can only see and write the
channels it is a member of. No admin key is involved: a contact never reaches anything but these routes.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import secrets
from typing import Any, Literal

from fastapi import APIRouter, Depends, Header, Query
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import problem

router = APIRouter(prefix="/api/v1/federation", tags=["federation"])


def sha(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


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


class AcceptBody(BaseModel):
    invite_id: str = Field(..., min_length=1, max_length=64)
    secret: str = Field(..., min_length=16, max_length=128)
    email: str = Field(..., min_length=3, max_length=200)
    name: str = Field(default="", max_length=80)


@router.post("/accept")
async def accept(body: AcceptBody) -> dict[str, Any]:
    from duckclaw.write_commands import AcceptContactInviteCommand

    rows = await _read(
        "SELECT i.owner_email, coalesce(u.nombre, i.owner_email) FROM main.admin_contact_invites i "
        "LEFT JOIN main.admin_console_users u ON lower(u.email) = lower(i.owner_email) "
        "WHERE i.invite_id = ? AND i.secret_hash = ? AND i.used_at IS NULL AND i.expires_at > CAST(CURRENT_TIMESTAMP AS TIMESTAMP)",
        [body.invite_id, sha(body.secret)],
    )
    if not rows:
        raise problem(403, "Invitación inválida", "el código no existe, ya se usó o venció")
    token = secrets.token_urlsafe(32)
    try:
        cmd = AcceptContactInviteCommand(actor_email=rows[0][0], invite_id=body.invite_id, secret_hash=sha(body.secret),
                                         remote_email=body.email.strip().lower(), remote_name=body.name.strip(), token_hash=sha(token))
    except ValueError as exc:
        raise problem(400, "Contacto inválido", str(exc)) from exc
    _enqueue(cmd)   # the writer re-checks the invite (single use) and refuses an email of a local user
    return {"ok": True, "token": token, "host_email": rows[0][0], "host_name": rows[0][1]}


async def contact_from_token(authorization: str | None = Header(None)) -> dict[str, Any]:
    raw = (authorization or "").removeprefix("Bearer ").strip()
    if len(raw) < 32:
        raise problem(401, "Sin token de contacto", "Authorization: Bearer <token>")
    rows = await _read("SELECT contact_id, owner_email, remote_email, remote_name FROM main.admin_contacts WHERE role = 'host' AND token_hash = ?",
                       [sha(raw)])
    if not rows:
        raise problem(401, "Token de contacto inválido", "revocado o desconocido")
    return {"contact_id": rows[0][0], "owner": rows[0][1], "email": rows[0][2], "name": rows[0][3]}


class ChannelBody(BaseModel):
    kind: Literal["dm"] = "dm"   # a contact opens a DM with its host person; groups are created on the host


class MessageBody(BaseModel):
    body: str = Field(..., min_length=1, max_length=8000)
    author_label: str = Field(default="", max_length=60)


@router.get("/channels")
async def list_channels(contact: dict = Depends(contact_from_token)) -> dict[str, Any]:
    from routers.admin_domains.messages import channels_for

    return {"channels": await channels_for(contact["email"]), "me": contact["email"]}


@router.post("/channels")
async def create_channel(body: ChannelBody, contact: dict = Depends(contact_from_token)) -> dict[str, Any]:
    from duckclaw.write_commands import CreateChannelCommand

    members = sorted({contact["owner"].lower(), contact["email"]})
    existing = await _read("SELECT channel_id FROM main.admin_channels WHERE kind = 'dm' AND members_json = ?", [json.dumps(members)])
    if existing:
        return {"ok": True, "channel_id": existing[0][0], "existing": True}
    cmd = CreateChannelCommand(actor_email=contact["email"], kind="dm", members=members)
    _enqueue(cmd)
    return {"ok": True, "channel_id": cmd.channel_id}


@router.get("/channels/{channel_id}")
async def read_channel(channel_id: str, since: str = Query(default=""), contact: dict = Depends(contact_from_token)) -> dict[str, Any]:
    from routers.admin_domains.messages import channel_with_messages

    return await channel_with_messages(channel_id, contact["email"], since)


@router.post("/channels/{channel_id}")
async def post_message(channel_id: str, body: MessageBody, contact: dict = Depends(contact_from_token)) -> dict[str, Any]:
    from routers.admin_domains.messages import post_as

    return await post_as(channel_id, contact["email"], body.body, body.author_label)
