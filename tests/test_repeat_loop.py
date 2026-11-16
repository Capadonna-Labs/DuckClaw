"""/loop <interval> <prompt>: several per chat, stored as interval items of the clock-cron list; /aware owns the old cycle."""

import json

import pytest

from duckclaw.commands import repeat_loop as rl
from duckclaw.runtime.scheduling.cron_wall_schedule import wall_schedule_should_fire


@pytest.fixture
def store(monkeypatch):
    state: dict[str, str] = {"goals_cron_wall": json.dumps([{"v": 1, "kind": "every", "every_h": 9, "every_mi": 0, "prompt": "/apertura", "id": "c1"}])}
    monkeypatch.setattr(rl, "get_chat_state", lambda db, chat, key: state.get(key, ""))

    def set_entries(db, chat, entries, tenant_id="default"):
        state.update(entries)
        return True, ""

    monkeypatch.setattr(rl, "_set_chat_state_entries", set_entries)
    monkeypatch.setattr(rl, "_save_wall_items", lambda db, chat, items, tenant_id="default": state.update(goals_cron_wall=json.dumps(items)) or "")
    return state


def items(state):
    return json.loads(state["goals_cron_wall"])


def test_two_loops_coexist_with_clock_crons(store):
    assert "Loop c2 creado" in rl.execute_repeat_loop(None, "x", "30m /datos_alternativos", tenant_id="t")
    assert "Loop c3 creado" in rl.execute_repeat_loop(None, "x", "2h revisa el VIX", tenant_id="t")
    got = items(store)
    assert [i["id"] for i in got] == ["c1", "c2", "c3"]   # the 09:00 clock cron is kept
    assert got[1] == {**got[1], "kind": "interval", "every_s": 1800, "prompt": "/datos_alternativos"}
    listing = rl.execute_repeat_loop(None, "x", "", tenant_id="t")
    assert "c2" in listing and "c3" in listing and "/apertura" not in listing


def test_off_removes_only_loops(store):
    rl.execute_repeat_loop(None, "x", "30m /a", tenant_id="t")
    rl.execute_repeat_loop(None, "x", "1h /b", tenant_id="t")
    assert "c2" in rl.execute_repeat_loop(None, "x", "off c2", tenant_id="t")
    assert [i["id"] for i in items(store)] == ["c1", "c3"]
    rl.execute_repeat_loop(None, "x", "off all", tenant_id="t")
    assert [i["id"] for i in items(store)] == ["c1"]   # clock cron survives "off all"
    assert "No hay un loop `c1`" in rl.execute_repeat_loop(None, "x", "off c1", tenant_id="t")


def test_rejects_short_interval_and_missing_prompt(store):
    assert "mínimo" in rl.execute_repeat_loop(None, "x", "2m /a", tenant_id="t")
    assert "Falta qué repetir" in rl.execute_repeat_loop(None, "x", "30m", tenant_id="t")


def test_old_syntax_points_to_aware():
    assert rl.is_aware_syntax("on 1h") and rl.is_aware_syntax("--status")
    assert not rl.is_aware_syntax("30m /x") and not rl.is_aware_syntax("off c2") and not rl.is_aware_syntax("")


def test_interval_fires_first_poll_then_every_n():
    spec = {"kind": "interval", "every_s": 1800}
    assert wall_schedule_should_fire(10_000.0, spec, 1.0, 45)         # new loop: next poll
    assert not wall_schedule_should_fire(10_000.0, spec, 9_000.0, 45)  # 1000 s since last run
    assert wall_schedule_should_fire(10_800.0, spec, 9_000.0, 45)      # 1800 s
