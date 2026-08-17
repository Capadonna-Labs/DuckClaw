"""In-process Redis shim for spawn/lite desktop when Redis is omitted."""

from __future__ import annotations

import asyncio
import fnmatch
import queue
import threading
import time
from typing import Any

_lock = threading.Lock()
_strings: dict[str, tuple[float, str]] = {}
_counters: dict[str, tuple[float, int]] = {}
_zsets: dict[str, tuple[float, dict[str, float]]] = {}
_async_locks: dict[str, asyncio.Lock] = {}
_pubsub_subs: dict[str, set["LitePubSub"]] = {}
_DEFAULT_STRING_TTL = 604800


class LiteLock:
    """In-process mutex compatible with ``redis.asyncio.lock.Lock`` used by chat_locks."""

    def __init__(self, key: str, *, timeout: float = 10, blocking_timeout: float = 15) -> None:
        self._key = key
        self._timeout = max(0.0, float(timeout))
        self._blocking_timeout = max(0.0, float(blocking_timeout))

    async def acquire(self) -> bool:
        lock = _async_locks.setdefault(self._key, asyncio.Lock())
        try:
            await asyncio.wait_for(lock.acquire(), timeout=self._blocking_timeout or None)
            return True
        except TimeoutError:
            return False

    async def release(self) -> None:
        lock = _async_locks.get(self._key)
        if lock is None or not lock.locked():
            return
        lock.release()


class LitePubSub:
    """Minimal async pub/sub surface for admin chat heartbeats in lite mode."""

    def __init__(self, store: "LiteSessionStore") -> None:
        self._store = store
        self._channels: set[str] = set()
        self._queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self._closed = False

    def _enqueue(self, message: dict[str, Any]) -> None:
        if self._closed:
            return
        self._queue.put(message)

    async def subscribe(self, *channels: str) -> None:
        for channel in channels:
            ch = str(channel or "").strip()
            if not ch:
                continue
            self._channels.add(ch)
            self._store._subscribe(ch, self)
            self._enqueue({"type": "subscribe", "channel": ch, "data": 1})

    async def unsubscribe(self, *channels: str) -> None:
        targets = [str(c).strip() for c in channels if str(c).strip()] or list(self._channels)
        for ch in targets:
            self._channels.discard(ch)
            self._store._unsubscribe(ch, self)

    async def get_message(
        self,
        ignore_subscribe_messages: bool = True,
        timeout: float | None = 0.0,
    ) -> dict[str, Any] | None:
        deadline = None if timeout is None else time.monotonic() + max(0.0, float(timeout))
        while True:
            remaining = None if deadline is None else max(0.0, deadline - time.monotonic())
            wait = 0.05 if remaining is None else min(0.05, remaining)

            def _poll() -> dict[str, Any] | None:
                try:
                    return self._queue.get(timeout=wait)
                except queue.Empty:
                    return None

            msg = await asyncio.to_thread(_poll)
            if msg is None:
                if deadline is not None and time.monotonic() >= deadline:
                    return None
                continue
            if ignore_subscribe_messages and msg.get("type") in {"subscribe", "unsubscribe"}:
                if deadline is not None and time.monotonic() >= deadline:
                    return None
                continue
            return msg

    async def aclose(self) -> None:
        self._closed = True
        await self.unsubscribe()
        while True:
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break


def _purge(now: float) -> None:
    for store in (_strings, _counters, _zsets):
        dead = [k for k, (exp, _) in store.items() if exp <= now]
        for key in dead:
            store.pop(key, None)


class LiteSessionStore:
    async def get(self, key: str) -> str | None:
        return await asyncio.to_thread(self._get, key)

    def _get(self, key: str) -> str | None:
        now = time.time()
        with _lock:
            _purge(now)
            row = _strings.get(key)
            if not row or row[0] <= now:
                _strings.pop(key, None)
                return None
            return row[1]

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        ttl = int(ex) if ex is not None else _DEFAULT_STRING_TTL
        await self.setex(key, ttl, value)

    async def setex(self, key: str, ttl: int, value: str) -> None:
        await asyncio.to_thread(self._setex, key, ttl, value)

    def _setex(self, key: str, ttl: int, value: str) -> None:
        now = time.time()
        with _lock:
            _purge(now)
            _strings[key] = (now + max(1, int(ttl)), value)

    async def delete(self, key: str) -> None:
        await asyncio.to_thread(self._delete, key)

    def _delete(self, key: str) -> None:
        with _lock:
            _strings.pop(key, None)
            _counters.pop(key, None)
            _zsets.pop(key, None)

    async def incr(self, key: str) -> int:
        return await asyncio.to_thread(self._incr, key)

    def _incr(self, key: str) -> int:
        now = time.time()
        with _lock:
            _purge(now)
            exp, count = _counters.get(key, (now + 86400, 0))
            count += 1
            _counters[key] = (exp, count)
            return count

    async def expire(self, key: str, ttl: int) -> None:
        await asyncio.to_thread(self._expire, key, ttl)

    def _expire(self, key: str, ttl: int) -> None:
        now = time.time()
        exp = now + max(1, int(ttl))
        with _lock:
            if key in _counters:
                _, count = _counters[key]
                _counters[key] = (exp, count)
            if key in _strings:
                _strings[key] = (exp, _strings[key][1])
            if key in _zsets:
                _zsets[key] = (exp, _zsets[key][1])

    async def zadd(self, key: str, mapping: dict[str, float]) -> None:
        await asyncio.to_thread(self._zadd, key, mapping)

    def _zadd(self, key: str, mapping: dict[str, float]) -> None:
        now = time.time()
        with _lock:
            _purge(now)
            exp, members = _zsets.get(key, (now + _DEFAULT_STRING_TTL, {}))
            merged = dict(members)
            for member, score in mapping.items():
                merged[str(member)] = float(score)
            _zsets[key] = (exp, merged)

    async def zrevrange(self, key: str, start: int, end: int) -> list[str]:
        return await asyncio.to_thread(self._zrevrange, key, start, end)

    def _zrevrange(self, key: str, start: int, end: int) -> list[str]:
        now = time.time()
        with _lock:
            _purge(now)
            row = _zsets.get(key)
            if not row or row[0] <= now:
                _zsets.pop(key, None)
                return []
            ordered = sorted(row[1].items(), key=lambda item: item[1], reverse=True)
            members = [member for member, _ in ordered]
            if end < 0:
                end = len(members) + end
            return members[start : end + 1]

    async def zrem(self, key: str, member: str) -> None:
        await asyncio.to_thread(self._zrem, key, member)

    def _zrem(self, key: str, member: str) -> None:
        with _lock:
            row = _zsets.get(key)
            if not row:
                return
            exp, members = row
            members = dict(members)
            members.pop(str(member), None)
            if members:
                _zsets[key] = (exp, members)
            else:
                _zsets.pop(key, None)

    async def scan(
        self,
        cursor: int = 0,
        match: str | None = None,
        count: int = 100,
    ) -> tuple[int, list[str]]:
        return await asyncio.to_thread(self._scan, cursor, match, count)

    def _scan(self, cursor: int, match: str | None, count: int) -> tuple[int, list[str]]:
        with _lock:
            keys = sorted(_strings.keys())
        if match:
            keys = [k for k in keys if fnmatch.fnmatch(k, match)]
        start = max(0, int(cursor))
        chunk = keys[start : start + max(1, int(count))]
        next_cursor = 0 if start + len(chunk) >= len(keys) else start + len(chunk)
        return next_cursor, chunk

    def pubsub(self) -> LitePubSub:
        return LitePubSub(self)

    def publish(self, channel: str, message: str) -> int:
        """Sync publish (compatible with redis-py ``client.publish``)."""
        ch = str(channel or "").strip()
        if not ch:
            return 0
        payload = str(message)
        with _lock:
            subscribers = list(_pubsub_subs.get(ch, ()))
        for sub in subscribers:
            sub._enqueue({"type": "message", "channel": ch, "data": payload})
        return len(subscribers)

    def _subscribe(self, channel: str, subscriber: LitePubSub) -> None:
        with _lock:
            _pubsub_subs.setdefault(channel, set()).add(subscriber)

    def _unsubscribe(self, channel: str, subscriber: LitePubSub) -> None:
        with _lock:
            subs = _pubsub_subs.get(channel)
            if not subs:
                return
            subs.discard(subscriber)
            if not subs:
                _pubsub_subs.pop(channel, None)

    async def aclose(self) -> None:
        return None

    def lock(
        self,
        name: str,
        timeout: float = 10,
        blocking_timeout: float = 15,
        **_: Any,
    ) -> LiteLock:
        # ponytail: single-process desktop; no cross-process lease expiry needed
        return LiteLock(name, timeout=timeout, blocking_timeout=blocking_timeout)


LITE_SESSION_STORE = LiteSessionStore()


def admin_session_backend(app_state: Any) -> Any | None:
    redis = getattr(app_state, "redis", None)
    if redis is not None:
        return redis
    from duckclaw.spawn_profile import spawn_inline_writes_enabled

    if spawn_inline_writes_enabled():
        return LITE_SESSION_STORE
    return None
