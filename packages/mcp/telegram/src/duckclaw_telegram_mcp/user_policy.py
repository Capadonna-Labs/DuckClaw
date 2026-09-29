"""Access policy for the Telegram *user-account* MCP (Telethon).

Enforced inside the MCP server, so no agent prompt or tool argument can widen
it. Configured by env (the server's process, not the agent's):

  TELEGRAM_USER_READ_ALLOW   comma list of chats the tools may list/read.
  TELEGRAM_USER_SEND_ALLOW   comma list of chats the tools may write to.
                             Empty (default) = sending disabled.
  TELEGRAM_USER_SEND_MODE    "draft" (default): the text is saved as a Telegram
                             draft in that chat — you review and press send on
                             your phone. "direct": sent immediately.
  TELEGRAM_USER_SEND_PER_HOUR  cap on send/draft calls per rolling hour (20).
  TELEGRAM_USER_MAX_READ     cap on messages per read call (50).

Chat entries: numeric peer id as printed by ``login`` (e.g. -1001234567890),
a username with or without "@", "me" (Saved Messages), or "*" for all.
"""

from __future__ import annotations

import os
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable, Literal, Mapping


def _norm(entry: str) -> str:
    return entry.strip().lstrip("@").lower()


def parse_allowlist(raw: str | None) -> tuple[bool, frozenset[str]]:
    entries = {_norm(x) for x in (raw or "").split(",") if _norm(x)}
    return ("*" in entries, frozenset(entries - {"*"}))


def _int_env(env: Mapping[str, str], name: str, default: int, lo: int, hi: int) -> int:
    try:
        value = int(str(env.get(name) or default).strip())
    except ValueError:
        value = default
    return max(lo, min(hi, value))


@dataclass(frozen=True)
class UserPolicy:
    read_all: bool = False
    read: frozenset[str] = frozenset()
    send_all: bool = False
    send: frozenset[str] = frozenset()
    send_mode: Literal["draft", "direct"] = "draft"
    send_per_hour: int = 20
    max_read: int = 50

    def can_read(self, keys: Iterable[str]) -> bool:
        return self.read_all or bool(self.read & {_norm(k) for k in keys})

    def can_send(self, keys: Iterable[str]) -> bool:
        return self.send_all or bool(self.send & {_norm(k) for k in keys})


def load_policy(env: Mapping[str, str] | None = None) -> UserPolicy:
    env = os.environ if env is None else env
    read_all, read = parse_allowlist(env.get("TELEGRAM_USER_READ_ALLOW"))
    send_all, send = parse_allowlist(env.get("TELEGRAM_USER_SEND_ALLOW"))
    mode = str(env.get("TELEGRAM_USER_SEND_MODE") or "draft").strip().lower()
    return UserPolicy(
        read_all=read_all,
        read=read,
        send_all=send_all,
        send=send,
        send_mode="direct" if mode == "direct" else "draft",
        send_per_hour=_int_env(env, "TELEGRAM_USER_SEND_PER_HOUR", 20, 0, 500),
        max_read=_int_env(env, "TELEGRAM_USER_MAX_READ", 50, 1, 200),
    )


def entity_keys(peer_id: int | str, username: str | None = None, is_self: bool = False) -> set[str]:
    """Every allowlist spelling that identifies one chat."""
    keys = {str(peer_id)}
    if username:
        keys.add(_norm(username))
    if is_self:
        keys.add("me")
    return keys


@dataclass
class HourlyRateLimiter:
    """ponytail: in-process counter — resets on restart; fine for one PM2 process."""

    limit: int
    _stamps: deque = field(default_factory=deque)

    def allow(self, now: float | None = None) -> bool:
        now = time.monotonic() if now is None else now
        while self._stamps and now - self._stamps[0] >= 3600:
            self._stamps.popleft()
        if len(self._stamps) >= self.limit:
            return False
        self._stamps.append(now)
        return True
