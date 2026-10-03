"""MCP server: controlled access to a Telegram *user* account (MTProto / Telethon).

Unlike ``server.py`` (Bot API, spawned per turn over stdio), a user session is
a single login that can't be opened by concurrent processes, so this runs as
one long-lived streamable-HTTP service bound to localhost and the gateway
reaches it as an MCP connector (preset ``telegram_user``).

Setup (on the host that runs it):
  1. my.telegram.org → API development tools → TELEGRAM_API_ID / TELEGRAM_API_HASH in .env
  2. python -m duckclaw_telegram_mcp.user login   (phone code + 2FA; lists chat ids)
  3. set TELEGRAM_USER_READ_ALLOW / TELEGRAM_USER_SEND_ALLOW (see user_policy.py)
  4. pm2 start config/ecosystem.mcp.config.cjs --only DuckClaw-Telegram-User-MCP
  5. Admin → MCP → preset "Telegram (cuenta)" → grant to the workers that need it

The session file (TELEGRAM_USER_SESSION, default ~/.duckclaw/telegram/user.session)
is full access to the account: it stays on disk with mode 600, never in the DB.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any

from duckclaw_telegram_mcp.user_policy import (
    HourlyRateLimiter,
    UserPolicy,
    entity_keys,
    load_policy,
)

_log = logging.getLogger("duckclaw.telegram_user_mcp")

_MAX_TEXT_OUT = 2000
_MAX_SEND_CHARS = 4096


class NotAuthorized(RuntimeError):
    pass


def session_path() -> Path:
    raw = (os.environ.get("TELEGRAM_USER_SESSION") or "").strip()
    return Path(raw).expanduser() if raw else Path.home() / ".duckclaw" / "telegram" / "user.session"


def _api_credentials() -> tuple[int, str]:
    api_id = (os.environ.get("TELEGRAM_API_ID") or "").strip()
    api_hash = (os.environ.get("TELEGRAM_API_HASH") or "").strip()
    if not api_id.isdigit() or not api_hash:
        raise RuntimeError("TELEGRAM_API_ID (numérico) y TELEGRAM_API_HASH son obligatorios")
    return int(api_id), api_hash


def _new_client() -> Any:
    from telethon import TelegramClient

    path = session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    api_id, api_hash = _api_credentials()
    return TelegramClient(str(path), api_id, api_hash)


def _secure_session_file() -> None:
    for candidate in (session_path(), Path(str(session_path()) + ".session")):
        if candidate.exists():
            try:
                candidate.chmod(0o600)
            except OSError:
                pass


def _ok(**payload: Any) -> str:
    return json.dumps({"ok": True, **payload}, ensure_ascii=False, default=str)


def _err(message: str) -> str:
    return json.dumps({"ok": False, "error": message}, ensure_ascii=False)


def _parse_chat_ref(chat: str) -> Any:
    ref = (chat or "").strip()
    if not ref:
        raise ValueError("chat vacío")
    if ref.lower() == "me":
        return "me"
    if ref.lstrip("-").isdigit():
        return int(ref)
    return ref if ref.startswith("@") else f"@{ref}"


class TelegramUserService:
    """One Telethon client for the process; every tool call goes through the policy."""

    def __init__(self, policy: UserPolicy) -> None:
        self.policy = policy
        self.rate = HourlyRateLimiter(policy.send_per_hour)
        self._client: Any = None
        self._self_id: int | None = None
        self._lock = asyncio.Lock()

    async def client(self) -> Any:
        async with self._lock:
            if self._client is None:
                self._client = _new_client()
            if not self._client.is_connected():
                await self._client.connect()
            if not await self._client.is_user_authorized():
                raise NotAuthorized(
                    "Sin sesión de Telegram: ejecuta `python -m duckclaw_telegram_mcp.user login` en el host"
                )
            if self._self_id is None:
                me = await self._client.get_me()
                self._self_id = int(me.id)
                # Warm the entity cache so numeric ids from the allowlist resolve.
                await self._client.get_dialogs(limit=200)
            return self._client

    def _keys(self, entity: Any) -> set[str]:
        from telethon.utils import get_peer_id

        return entity_keys(
            get_peer_id(entity),
            getattr(entity, "username", None),
            is_self=bool(getattr(entity, "is_self", False)),
        )

    async def _resolve(self, chat: str) -> Any:
        client = await self.client()
        return await client.get_entity(_parse_chat_ref(chat))

    async def list_chats(self, limit: int = 50) -> str:
        from telethon.utils import get_display_name, get_peer_id

        client = await self.client()
        out = []
        async for dialog in client.iter_dialogs(limit=200):
            entity = dialog.entity
            if not self.policy.can_read(self._keys(entity)):
                continue
            out.append(
                {
                    "chat": str(get_peer_id(entity)),
                    "name": get_display_name(entity),
                    "username": getattr(entity, "username", None),
                    "type": "user" if dialog.is_user else "group" if dialog.is_group else "channel",
                    "unread": dialog.unread_count,
                    "can_send": self.policy.can_send(self._keys(entity)),
                }
            )
            if len(out) >= max(1, min(int(limit or 50), 200)):
                break
        _log.info("telegram_user action=list_chats returned=%d", len(out))
        return _ok(chats=out, send_mode=self.policy.send_mode)

    async def read_messages(self, chat: str, limit: int = 20, before_id: int = 0) -> str:
        from telethon.utils import get_display_name, get_peer_id

        entity = await self._resolve(chat)
        if not self.policy.can_read(self._keys(entity)):
            _log.warning("telegram_user action=read DENIED chat=%s", get_peer_id(entity))
            return _err("Chat fuera de TELEGRAM_USER_READ_ALLOW")
        client = await self.client()
        n = max(1, min(int(limit or 20), self.policy.max_read))
        messages = []
        async for msg in client.iter_messages(entity, limit=n, offset_id=int(before_id or 0)):
            sender = await msg.get_sender() if msg.sender_id else None
            text = msg.message or ""
            messages.append(
                {
                    "id": msg.id,
                    "date": msg.date.isoformat() if msg.date else None,
                    "sender": get_display_name(sender) if sender else None,
                    "sender_username": getattr(sender, "username", None),
                    "out": bool(msg.out),
                    "text": text[:_MAX_TEXT_OUT] + ("…" if len(text) > _MAX_TEXT_OUT else ""),
                    "reply_to": getattr(msg.reply_to, "reply_to_msg_id", None),
                    "has_media": msg.media is not None,
                }
            )
        _log.info("telegram_user action=read chat=%s returned=%d", get_peer_id(entity), len(messages))
        return _ok(chat=str(get_peer_id(entity)), name=get_display_name(entity), messages=messages)

    async def mark_read(self, chat: str, max_id: int = 0) -> str:
        """Mark a readable chat as read (up to ``max_id``, or everything when 0).

        Only changes the user's own read state, so it follows the read allowlist.
        """
        from telethon.utils import get_peer_id

        entity = await self._resolve(chat)
        if not self.policy.can_read(self._keys(entity)):
            _log.warning("telegram_user action=mark_read DENIED chat=%s", get_peer_id(entity))
            return _err("Chat fuera de TELEGRAM_USER_READ_ALLOW")
        client = await self.client()
        mid = int(max_id or 0)
        await client.send_read_acknowledge(entity, max_id=mid or None)
        _log.info("telegram_user action=mark_read chat=%s max_id=%s", get_peer_id(entity), mid or "all")
        return _ok(chat=str(get_peer_id(entity)), marked_read_up_to=mid or "all")

    async def send_message(self, chat: str, text: str) -> str:
        from telethon import functions
        from telethon.utils import get_peer_id

        body = (text or "").strip()
        if not body:
            return _err("text vacío")
        if len(body) > _MAX_SEND_CHARS:
            return _err(f"text supera {_MAX_SEND_CHARS} caracteres")
        entity = await self._resolve(chat)
        peer = get_peer_id(entity)
        if not self.policy.can_send(self._keys(entity)):
            _log.warning("telegram_user action=send DENIED chat=%s", peer)
            return _err("Chat fuera de TELEGRAM_USER_SEND_ALLOW (enviar está deshabilitado por defecto)")
        if not self.rate.allow():
            return _err(f"Límite de {self.policy.send_per_hour} envíos/hora alcanzado")
        client = await self.client()
        if self.policy.send_mode == "direct":
            sent = await client.send_message(entity, body)
            _log.info("telegram_user action=send mode=direct chat=%s chars=%d", peer, len(body))
            return _ok(mode="direct", chat=str(peer), message_id=sent.id)
        await client(
            functions.messages.SaveDraftRequest(peer=await client.get_input_entity(entity), message=body)
        )
        _log.info("telegram_user action=send mode=draft chat=%s chars=%d", peer, len(body))
        return _ok(
            mode="draft",
            chat=str(peer),
            message="Guardado como borrador en ese chat: el usuario lo revisa y lo envía desde Telegram.",
        )


def build_user_mcp_app(service: TelegramUserService | None = None) -> Any:
    from mcp.server.fastmcp import FastMCP

    svc = service or TelegramUserService(load_policy())
    host = (os.environ.get("TELEGRAM_USER_MCP_HOST") or "127.0.0.1").strip()
    port = int((os.environ.get("TELEGRAM_USER_MCP_PORT") or "8765").strip())
    mcp = FastMCP("duckclaw-telegram-user", host=host, port=port)

    async def _guard(coro: Any) -> str:
        try:
            return await coro
        except NotAuthorized as exc:
            return _err(str(exc))
        except ValueError as exc:
            return _err(str(exc))
        except Exception as exc:  # Telethon RPC errors (unknown username, flood wait, …)
            _log.warning("telegram_user tool error: %s", exc)
            return _err(f"{type(exc).__name__}: {str(exc)[:300]}")

    @mcp.tool()
    async def telegram_list_chats(limit: int = 50) -> str:
        """Lista los chats de Telegram a los que tienes acceso de lectura (id, nombre, no leídos, can_send)."""
        return await _guard(svc.list_chats(limit))

    @mcp.tool()
    async def telegram_read_messages(chat: str, limit: int = 20, before_id: int = 0) -> str:
        """Lee los mensajes más recientes de un chat permitido. chat = id de telegram_list_chats, @usuario o 'me'. before_id pagina hacia atrás."""
        return await _guard(svc.read_messages(chat, limit, before_id))

    @mcp.tool()
    async def telegram_mark_read(chat: str, max_id: int = 0) -> str:
        """Marca como leídos los mensajes de un chat permitido (hasta max_id; 0 = todos). Solo cambia tu estado de lectura."""
        return await _guard(svc.mark_read(chat, max_id))

    @mcp.tool()
    async def telegram_send_message(chat: str, text: str) -> str:
        """Escribe en un chat permitido para envío. Por defecto queda como BORRADOR en Telegram para que el usuario lo revise y lo envíe; no asumas que se envió si mode='draft'."""
        return await _guard(svc.send_message(chat, text))

    return mcp


def _login() -> int:
    """Interactive one-time login; prints readable chat ids for the allowlists."""
    from telethon.utils import get_display_name, get_peer_id

    client = _new_client()

    async def _run() -> None:
        await client.start()  # prompts for phone, code and 2FA password
        me = await client.get_me()
        print(f"\nSesión iniciada como {get_display_name(me)} (@{me.username}). Chats recientes:\n")
        async for dialog in client.iter_dialogs(limit=60):
            ent = dialog.entity
            handle = f"@{ent.username}" if getattr(ent, "username", None) else ""
            print(f"  {get_peer_id(ent):>16}  {handle:<24} {get_display_name(ent)}")
        print("\nUsa estos ids en TELEGRAM_USER_READ_ALLOW / TELEGRAM_USER_SEND_ALLOW (.env).")
        await client.disconnect()

    asyncio.run(_run())
    _secure_session_file()
    print(f"Sesión guardada en {session_path()} (permisos 600).")
    return 0


def main(argv: list[str] | None = None) -> None:
    args = sys.argv[1:] if argv is None else argv
    level = (os.getenv("DUCKCLAW_TELEGRAM_MCP_LOG_LEVEL") or "INFO").strip().upper()
    logging.basicConfig(level=getattr(logging, level, logging.INFO), format="%(message)s")
    if args and args[0] == "login":
        raise SystemExit(_login())
    _secure_session_file()
    build_user_mcp_app().run(transport="streamable-http")
