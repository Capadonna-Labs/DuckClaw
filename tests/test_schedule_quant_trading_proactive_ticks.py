"""schedule_quant_trading_proactive_ticks: sesión ACTIVE + vault keys (worker RO)."""

from __future__ import annotations

import json

import pytest

from duckclaw.graphs import on_the_fly_commands as otfc


def test_schedule_quant_trading_proactive_ticks_no_active_row() -> None:
    class _Db:
        def query(self, sql: str) -> str:
            return json.dumps([])

    out = json.loads(
        otfc.schedule_quant_trading_proactive_ticks(
            _Db(), chat_id="1", tenant_id="default", interval_seconds=0
        )
    )
    assert out["status"] == "error"
    assert out.get("error") == "NO_ACTIVE_ROW"


def test_schedule_quant_trading_proactive_ticks_session_not_active() -> None:
    class _Db:
        def query(self, sql: str) -> str:
            return json.dumps([{"session_uid": "su", "status": "PAUSED"}])

    out = json.loads(
        otfc.schedule_quant_trading_proactive_ticks(
            _Db(), chat_id="1", tenant_id="default", interval_seconds=0
        )
    )
    assert out["status"] == "error"
    assert out.get("error") == "SESSION_NOT_ACTIVE"


def test_schedule_quant_trading_proactive_ticks_interval_writes_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault_calls: list[tuple[str, str]] = []

    def _fake_vault(
        db: object,
        chat_id: object,
        suf: str,
        val: str,
        *,
        tenant_id: str = "default",
    ) -> tuple[bool, str]:
        vault_calls.append((suf, val))
        return True, ""

    monkeypatch.setattr(otfc, "set_chat_state_via_vault", _fake_vault)
    monkeypatch.setattr(
        otfc,
        "_ensure_trading_session_goals_delta",
        lambda *_a, **_k: (False, 300),
    )

    class _Db:
        def query(self, sql: str) -> str:
            return json.dumps([{"session_uid": "su-1", "status": "ACTIVE"}])

    out = json.loads(
        otfc.schedule_quant_trading_proactive_ticks(
            _Db(), chat_id="c1", tenant_id="t1", interval_seconds=120
        )
    )
    assert out["status"] == "ok"
    assert out["interval_seconds"] == 120
    assert out["session_uid"] == "su-1"
    keys = {s for s, _ in vault_calls}
    assert otfc._GOALS_DELTA_SECONDS_KEY in keys
    assert any(v == "120" for s, v in vault_calls if s == otfc._GOALS_DELTA_SECONDS_KEY)


def test_schedule_quant_trading_proactive_ticks_bootstrap_interval_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vault_calls: list[tuple[str, str]] = []

    def _fake_vault(
        db: object,
        chat_id: object,
        suf: str,
        val: str,
        *,
        tenant_id: str = "default",
    ) -> tuple[bool, str]:
        vault_calls.append((suf, val))
        return True, ""

    monkeypatch.setattr(otfc, "get_chat_state", lambda *_a, **kw: "0")
    monkeypatch.setattr(otfc, "get_manager_goals", lambda *_a, **_k: [])
    monkeypatch.setattr(otfc, "set_chat_state_via_vault", _fake_vault)

    class _Db:
        def query(self, sql: str) -> str:
            if "session_goal" in sql:
                return json.dumps([{"session_goal": None}])
            return json.dumps([{"session_uid": "su-1", "status": "ACTIVE"}])

    out = json.loads(
        otfc.schedule_quant_trading_proactive_ticks(
            _Db(), chat_id="c1", tenant_id="t1", interval_seconds=0
        )
    )
    assert out["status"] == "ok"
    assert out["session_uid"] == "su-1"
    assert out.get("scheduler_bootstrap_was_needed") is True
    keys = {s for s, _ in vault_calls}
    assert otfc._GOALS_DELTA_META_KEY in keys
