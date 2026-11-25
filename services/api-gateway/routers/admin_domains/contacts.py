"""Contacts: people of other DuckClaw instances, added by invitation (see routers/federation.py for the instance-to-instance side).

``POST /contacts/invite`` returns a code (this instance's URL + a single-use secret, 7 days) that the person pastes in their DuckClaw;
``POST /contacts/accept`` redeems a code received from someone else. ``DUCKCLAW_FEDERATION_URL`` is how the other instance reaches this
one (e.g. the Tailscale address of the gateway); without it this instance can accept invitations but not send them.
"""

from __future__ import annotations

import base64
import json
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key
from routers.admin_domains.messages import _enqueue, _me, _read
from routers.federation import sha

router = APIRouter(prefix="/contacts", tags=["admin-contacts"])

INVITE_DAYS = 7


class AcceptBody(BaseModel):
    code: str = Field(..., min_length=20, max_length=1000)


@router.get("", dependencies=[Depends(require_admin_key)])
async def list_contacts(actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    me = _me(actor)
    rows = await _read("SELECT contact_id, role, remote_url, remote_email, remote_name, created_at FROM main.admin_contacts "
                       "WHERE owner_email = ? ORDER BY remote_name", [me])
    agents: dict[str, list[str]] = {}
    for email, label in await _read("SELECT DISTINCT author_email, author_label FROM main.admin_channel_messages WHERE author_label <> ''", []):
        agents.setdefault(email, []).append(label)
    return {"contacts": [{"id": c, "role": r, "instance": u or "esta instancia (tú la hospedas)", "email": e, "name": n or e,
                          "created_at": str(t), "agents": sorted(agents.get(e, []))} for c, r, u, e, n, t in rows],
            "can_invite": bool((os.environ.get("DUCKCLAW_FEDERATION_URL") or "").strip())}


@router.post("/invite", dependencies=[Depends(require_admin_key)])
async def invite(actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    from duckclaw.write_commands import CreateContactInviteCommand

    me = _me(actor)
    url = (os.environ.get("DUCKCLAW_FEDERATION_URL") or "").strip().rstrip("/")
    if not url:
        raise problem(400, "Federación sin configurar", "define DUCKCLAW_FEDERATION_URL (la dirección con la que otra instancia llega a esta)")
    secret = secrets.token_urlsafe(24)
    expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(days=INVITE_DAYS)
    cmd = CreateContactInviteCommand(actor_email=me, secret_hash=sha(secret), expires_at=expires.isoformat(sep=" ", timespec="seconds"))
    _enqueue(cmd)
    code = base64.urlsafe_b64encode(json.dumps({"u": url, "i": cmd.invite_id, "s": secret}).encode()).decode().rstrip("=")
    return {"ok": True, "code": code, "expires_at": cmd.expires_at}


@router.post("/accept", dependencies=[Depends(require_admin_key)])
async def accept(body: AcceptBody, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    import httpx

    from duckclaw.write_commands import AddGuestContactCommand

    me = _me(actor)
    try:
        raw = body.code.strip()
        data = json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))
        url, invite_id, secret = str(data["u"]).rstrip("/"), str(data["i"]), str(data["s"])
    except (ValueError, KeyError, TypeError) as exc:
        raise problem(400, "Código inválido", "no es un código de invitación de DuckClaw") from exc
    names = await _read("SELECT nombre FROM main.admin_console_users WHERE lower(email) = ?", [me])
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(f"{url}/api/v1/federation/accept",
                                  json={"invite_id": invite_id, "secret": secret, "email": me, "name": names[0][0] if names else ""})
    except httpx.HTTPError as exc:
        raise problem(502, "No se pudo llegar a la otra instancia", f"{url}: {type(exc).__name__}") from exc
    if r.status_code != 200:
        raise problem(400, "La otra instancia rechazó el código", f"HTTP {r.status_code}: {r.text[:200]}")
    host = r.json()
    cmd = AddGuestContactCommand(actor_email=me, remote_url=url, remote_email=host["host_email"], remote_name=host.get("host_name") or "",
                                 token=host["token"])
    _enqueue(cmd)
    return {"ok": True, "contact_id": cmd.contact_id, "name": host.get("host_name") or host["host_email"]}


@router.delete("/{contact_id}", dependencies=[Depends(require_admin_key)])
async def delete_contact(contact_id: str, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    from duckclaw.write_commands import DeleteContactCommand

    return {"ok": True, "task_id": _enqueue(DeleteContactCommand(actor_email=_me(actor), contact_id=contact_id))}
