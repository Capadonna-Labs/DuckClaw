"""HITL validation for /meditate homeostasis."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from duckclaw.commands.hitl import execute_meditate_approve, execute_meditate_reject
from duckclaw.commands.meditate import build_meditate_self_system_event_message
from duckclaw.hitl.meditate_validation_service import (
    approve_validation,
    create_pending_validation,
    get_pending_validation,
    reject_validation,
)


class _FakeDb:
    def __init__(self) -> None:
        self._rows: dict[str, str] = {}

    def execute(self, sql: str) -> None:
        if "INSERT INTO agent_config" in sql:
            parts = sql.split("VALUES ('", 1)[1]
            key, rest = parts.split("', '", 1)
            val = rest.split("')", 1)[0]
            self._rows[key] = val.replace("''", "'")

    def query(self, sql: str):
        if "SELECT value FROM agent_config" in sql:
            key = sql.split("key = '", 1)[1].split("'", 1)[0]
            val = self._rows.get(key, "")
            return json.dumps([{"value": val}]) if val else json.dumps([])
        return json.dumps([])


@pytest.fixture
def mock_manifest(monkeypatch: pytest.MonkeyPatch) -> None:
    class _Manifest:
        goals = []

        def model_dump(self):
            return {"goals": [], "infra": {}}

    monkeypatch.setattr(
        "harness_core.targets.load_homeostasis_manifest",
        lambda *_a, **_k: _Manifest(),
    )
    monkeypatch.setattr(
        "harness_core.targets.manifest_goals_as_dicts",
        lambda _m: [],
    )


def _make_db(path: Path) -> _FakeDb:
    _ = path
    return _FakeDb()


def test_create_pending_validation() -> None:
    db = _make_db(Path("pending.duckdb"))
    created = create_pending_validation(
        db,
        "chat-1",
        tenant_id="t1",
        snapshot={"current_metrics": {"x": 1}},
        goals_summary="goal A ok",
    )
    assert created["ok"] is True
    vid = created["validation_id"]
    pending = get_pending_validation(db, "chat-1")
    assert pending is not None
    assert pending["validation_id"] == vid
    assert pending["status"] == "PENDING_HITL"


def test_create_pending_idempotent_error() -> None:
    db = _make_db(Path("dup.duckdb"))
    first = create_pending_validation(db, "c2", tenant_id="t1", snapshot={})
    second = create_pending_validation(db, "c2", tenant_id="t1", snapshot={})
    assert first["ok"] is True
    assert second["ok"] is False
    assert second["error"] == "pending_validation_exists"
    assert second["validation_id"] == first["validation_id"]


def test_approve_validation_clears_pending() -> None:
    db = _make_db(Path("approve.duckdb"))
    created = create_pending_validation(db, "c3", tenant_id="t1", snapshot={})
    vid = created["validation_id"]
    result = approve_validation(db, "c3", vid)
    assert result["ok"] is True
    assert result["status"] == "APPROVED"
    assert get_pending_validation(db, "c3") is None


def test_approve_without_pending_errors() -> None:
    db = _make_db(Path("no_pending.duckdb"))
    out = execute_meditate_approve(db, "c4", "")
    assert "no hay validación" in out.lower()


def test_reject_validation_with_rationale() -> None:
    db = _make_db(Path("reject.duckdb"))
    created = create_pending_validation(db, "c5", tenant_id="t1", snapshot={})
    vid = created["validation_id"]
    result = reject_validation(db, "c5", vid, rationale="metas desactualizadas")
    assert result["ok"] is True
    assert result["status"] == "REJECTED"
    assert result["rationale"] == "metas desactualizadas"
    out = execute_meditate_reject(db, "c5", f"{vid} otra vez")
    assert "no hay validación" in out.lower()


def test_fly_meditate_approve_success() -> None:
    from duckclaw.commands.chat_state import get_chat_state, set_chat_state

    db = _make_db(Path("fly_ok.duckdb"))
    set_chat_state(db, "c6", "meditate_active", "1")
    set_chat_state(db, "c6", "meditate_delta_seconds", "900")
    created = create_pending_validation(db, "c6", tenant_id="t1", snapshot={})
    vid = created["validation_id"]
    out = execute_meditate_approve(db, "c6", vid, tenant_id="t1")
    assert "homeostasis confirmada" in out.lower() or "modo `/meditate` detenido" in out.lower()
    assert vid in out
    assert get_chat_state(db, "c6", "meditate_active") == "0"
    assert get_chat_state(db, "c6", "meditate_delta_seconds") == "0"


def test_build_meditate_system_event_includes_hitl_step(mock_manifest: None) -> None:
    db = _FakeDb()
    msg = build_meditate_self_system_event_message(db, "1", "default", scheduled=False)
    assert "request_homeostasis_validation" in msg
    assert "/meditate-approve" in msg


def test_build_meditate_system_event_pending_prefix(mock_manifest: None) -> None:
    db = _FakeDb()
    created = create_pending_validation(
        db,
        "7",
        tenant_id="default",
        snapshot={},
        goals_summary="x",
    )
    vid = created["validation_id"]
    msg = build_meditate_self_system_event_message(db, "7", "default", scheduled=True)
    assert "HITL pendiente" in msg
    assert vid in msg
    assert "/meditate-approve" in msg
