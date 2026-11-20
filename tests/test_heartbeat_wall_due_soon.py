"""An interval turn must not start right before a clock cron: the cron queues FIFO behind it and runs late."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import services.heartbeat.main as heartbeat
from duckclaw.runtime.scheduling.cron_wall_schedule import dump_wall_items

TZ = "America/Bogota"


def _epoch(h: int, m: int) -> float:
    return datetime(2026, 11, 20, h, m, tzinfo=ZoneInfo(TZ)).timestamp()  # a Friday


def _due(monkeypatch, items, now) -> bool:
    monkeypatch.setattr(heartbeat, "get_chat_state", lambda *_a: dump_wall_items(items))
    return heartbeat._wall_cron_due_soon(None, "c", now)


def test_cron_within_ten_minutes_blocks_the_interval_turn(monkeypatch) -> None:
    every = [{"v": 1, "tz": TZ, "kind": "every", "every_h": 9, "every_mi": 45, "weekdays": [4], "prompt": "x", "id": "c6"}]
    assert _due(monkeypatch, every, _epoch(9, 40))
    assert not _due(monkeypatch, every, _epoch(9, 30))
    assert not _due(monkeypatch, every, _epoch(9, 46))


def test_loop_interval_items_never_block(monkeypatch) -> None:
    loop = [{"v": 1, "kind": "interval", "every_s": 60, "prompt": "x", "id": "c9"}]
    assert not _due(monkeypatch, loop, _epoch(9, 40))
