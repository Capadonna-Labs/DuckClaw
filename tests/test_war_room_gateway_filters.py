from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
API_GATEWAY_DIR = REPO_ROOT / "services" / "api-gateway"
if str(API_GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(API_GATEWAY_DIR))

from core.war_rooms import (
    hit_rate_limit,
    is_explicit_wr_invocation,
    parse_mentions,
    war_room_evaluate_mention_gate,
)
from routers import telegram_inbound_webhook as wr_webhook


class _FakeRedis:
    def __init__(self) -> None:
        self._values: dict[str, str] = {}
        self._expiry: dict[str, float] = {}

    def _purge_if_expired(self, key: str) -> None:
        exp = self._expiry.get(key)
        if exp is not None and exp <= time.monotonic():
            self._values.pop(key, None)
            self._expiry.pop(key, None)

    async def incr(self, key: str) -> int:
        self._purge_if_expired(key)
        current = int(self._values.get(key, "0"))
        current += 1
        self._values[key] = str(current)
        return current

    async def expire(self, key: str, seconds: int) -> bool:
        self._expiry[key] = time.monotonic() + int(seconds)
        return True

    async def ttl(self, key: str) -> int:
        self._purge_if_expired(key)
        exp = self._expiry.get(key)
        if exp is None:
            return -1
        return max(0, int(exp - time.monotonic()))

    async def get(self, key: str) -> str | None:
        self._purge_if_expired(key)
        return self._values.get(key)

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool:
        self._purge_if_expired(key)
        if nx and key in self._values:
            return False
        self._values[key] = value
        if ex is not None:
            self._expiry[key] = time.monotonic() + int(ex)
        return True


def test_wr_rate_limit_notifies_only_once_per_window() -> None:
    redis = _FakeRedis()
    kwargs = {"tenant_id": "wr_-100", "user_id": "42", "cooldown_seconds": 30, "max_messages": 2}

    allowed, notify, ttl = asyncio.run(hit_rate_limit(redis, **kwargs))
    assert allowed is True and notify is False and ttl > 0

    allowed, notify, ttl = asyncio.run(hit_rate_limit(redis, **kwargs))
    assert allowed is True and notify is False and ttl > 0

    allowed, notify, ttl = asyncio.run(hit_rate_limit(redis, **kwargs))
    assert allowed is False and notify is True and ttl > 0

    allowed, notify, ttl = asyncio.run(hit_rate_limit(redis, **kwargs))
    assert allowed is False and notify is False and ttl > 0


def test_wr_dynamic_alias_resolution_from_manifests(monkeypatch: pytest.MonkeyPatch) -> None:
    wr_webhook._worker_alias_cache = set()
    wr_webhook._worker_alias_cache_ts = 0.0

    monkeypatch.setattr("duckclaw.workers.factory.list_workers", lambda: ["finanz01", "job_hunter"])

    def _fake_manifest(worker_id: str):
        if worker_id == "finanz01":
            return SimpleNamespace(worker_id="finanz01", logical_worker_id="finanz", name="Finanz Agent")
        return SimpleNamespace(worker_id="job_hunter", logical_worker_id="jobhunter", name="Job Hunter")

    monkeypatch.setattr("duckclaw.workers.manifest.load_manifest", _fake_manifest)

    aliases = wr_webhook._resolve_dynamic_worker_aliases()
    assert "finanz01" in aliases
    assert "finanz" in aliases
    assert "job_hunter" in aliases
    assert "jobhunter" in aliases

    assert is_explicit_wr_invocation(
        "@jobhunter revisa vacantes",
        bot_aliases={"duckclaw"},
        worker_aliases=aliases,
    )


def test_parse_mentions_text_mention_uses_user_username() -> None:
    text = "revisa esta captura"
    entities = [
        {
            "type": "text_mention",
            "offset": 0,
            "length": 1,
            "user": {"id": 1, "is_bot": True, "username": "finanz01_bot"},
        }
    ]
    m = parse_mentions(text, entities)
    assert "finanz01_bot" in m
    assert is_explicit_wr_invocation(
        text,
        entities=entities,
        bot_aliases={"finanz01_bot"},
        worker_aliases=set(),
    )


def test_war_room_gate_visual_caption_with_at_username() -> None:
    g = war_room_evaluate_mention_gate(
        combined_text="@finanz01_bot",
        entities=[],
        has_visual_media=True,
        current_bot_username="finanz01_bot",
        bootstrap_mode=False,
    )
    assert g.allowed is True
    assert g.decision == "ALLOWED_VISUAL_CAPTION"


def test_war_room_gate_typo_finanz1_bot_drops_visual_caption() -> None:
    """@finanz1_bot ≠ @finanz01_bot: typo común en caption con imagen → DROP_NO_MENTION."""
    g = war_room_evaluate_mention_gate(
        combined_text="@finanz1_bot",
        entities=[],
        has_visual_media=True,
        current_bot_username="finanz01_bot",
        bootstrap_mode=False,
    )
    assert g.allowed is False
    assert g.decision == "DROP_NO_MENTION"


def test_war_room_gate_visual_without_caption_drops() -> None:
    g = war_room_evaluate_mention_gate(
        combined_text="",
        entities=[],
        has_visual_media=True,
        current_bot_username="finanz01_bot",
        bootstrap_mode=False,
    )
    assert g.allowed is False
    assert g.decision == "DROP_NO_MENTION"


def test_war_room_gate_fly_command_with_visual() -> None:
    g = war_room_evaluate_mention_gate(
        combined_text="/team",
        entities=[],
        has_visual_media=True,
        current_bot_username="finanz01_bot",
        bootstrap_mode=False,
    )
    assert g.allowed is True
    assert g.decision == "ALLOWED_COMMAND"


def test_war_room_gate_text_mention_current_bot() -> None:
    g = war_room_evaluate_mention_gate(
        combined_text="Hola @finanz01_bot",
        entities=[],
        has_visual_media=False,
        current_bot_username="finanz01_bot",
        bootstrap_mode=False,
    )
    assert g.allowed is True
    assert g.decision == "ALLOWED_MENTION"


def test_parse_mentions_mention_entity_respects_utf16_offsets() -> None:
    """Telegram cuenta offset en unidades UTF-16 (emoji = 2 unidades antes del @)."""
    text = "👀 @finanz01_bot ok"
    entities = [{"type": "mention", "offset": 2, "length": 13}]
    m = parse_mentions(text, entities)
    assert "finanz01_bot" in m
