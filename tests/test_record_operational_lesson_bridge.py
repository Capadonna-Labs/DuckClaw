"""Tests for record_operational_lesson forge skill."""

from __future__ import annotations

import json

from duckclaw.forge.skills.record_operational_lesson_bridge import (
    _record_operational_lesson_impl,
    register_record_operational_lesson_skill,
)


def test_register_record_operational_lesson_skill_adds_tool() -> None:
    tools: list = []
    register_record_operational_lesson_skill(tools, {})
    names = {getattr(t, "name", "") for t in tools}
    assert "record_operational_lesson" in names


def test_record_operational_lesson_persists_with_lesson_type(monkeypatch) -> None:
    calls: list[tuple] = []

    class _Db:
        schema = "finance_worker"

    def _fake_write(db, schema, key, trigger, lesson, conf, **_kw):
        calls.append((schema, key, trigger, lesson, conf))
        return True, ""

    monkeypatch.setattr(
        "duckclaw.forge.skills.record_operational_lesson_bridge.write_field_lesson",
        _fake_write,
    )
    out = json.loads(
        _record_operational_lesson_impl(
            "Nunca citar qty sin snapshot del bróker",
            context_trigger="audit mismatch AAPL",
            lesson_type="broker_position_hallucination",
            confidence_score=0.95,
            db=_Db(),
        )
    )
    assert out["ok"] is True
    assert out["context_trigger"] == "broker_position_hallucination:audit mismatch AAPL"
    assert out["belief_key"].startswith("lesson_")
    assert calls and calls[0][0] == "finance_worker"
    assert calls[0][2] == "broker_position_hallucination:audit mismatch AAPL"


def test_record_operational_lesson_prefers_spec_schema_name(monkeypatch) -> None:
    seen: list[str] = []

    class _Db:  # handle sin atributo schema (DuckClaw real)
        pass

    def _fake_write(db, schema, *_a, **_kw):
        seen.append(schema)
        return True, ""

    monkeypatch.setattr(
        "duckclaw.forge.skills.record_operational_lesson_bridge.write_field_lesson",
        _fake_write,
    )
    out = json.loads(
        _record_operational_lesson_impl("x", context_trigger="t", db=_Db(), schema_name="finance_worker")
    )
    assert out["ok"] is True
    assert out["table"] == "finance_worker.agent_beliefs"
    assert seen == ["finance_worker"]


def test_record_operational_lesson_failed_write_returns_ok_false(monkeypatch) -> None:
    class _Db:
        pass

    monkeypatch.setattr(
        "duckclaw.forge.skills.record_operational_lesson_bridge.write_field_lesson",
        lambda *_a, **_kw: (False, "El DB-Writer rechazó la escritura: Catalog Error"),
    )
    out = json.loads(
        _record_operational_lesson_impl("x", context_trigger="t", db=_Db(), schema_name="finance_worker")
    )
    assert out["ok"] is False
    assert "NO se guardó" in out["error"]
    assert "Catalog Error" in out["error"]
    assert out["belief_key"].startswith("lesson_")


def test_record_operational_lesson_exception_returns_ok_false(monkeypatch) -> None:
    class _Db:
        pass

    def _boom(*_a, **_kw):
        raise RuntimeError("redis caído")

    monkeypatch.setattr(
        "duckclaw.forge.skills.record_operational_lesson_bridge.write_field_lesson",
        _boom,
    )
    out = json.loads(_record_operational_lesson_impl("x", db=_Db(), schema_name="finance_worker"))
    assert out["ok"] is False
    assert "redis caído" in out["error"]


class _RoVaultDb:
    """Simula DuckClaw(read_only=True) sobre un vault en disco: execute() siempre falla."""

    _read_only = True
    _path = "/srv/db/private/u-123/research_vault.duckdb"

    def __init__(self) -> None:
        self.executed: list[str] = []
        self.suspended = 0
        self.resumed = 0

    def execute(self, sql: str, *_a) -> None:
        self.executed.append(sql)
        raise RuntimeError("Cannot execute statement of type INSERT on database opened in read-only mode")

    def suspend_readonly_file_handle(self) -> None:
        self.suspended += 1

    def resume_readonly_file_handle(self) -> None:
        self.resumed += 1


class _Status:
    def __init__(self, status: str, detail: str = "") -> None:
        self.status = status
        self.detail = detail


def _patch_writer(monkeypatch, status):
    enqueued: list[dict] = []

    def _fake_enqueue(cmd, *, db_path, user_id, **_kw):
        enqueued.append({"query": cmd.query, "db_path": db_path, "user_id": user_id})
        return "task-123"

    monkeypatch.setattr("duckclaw.db_write_queue.enqueue_typed_command", _fake_enqueue)
    monkeypatch.setattr(
        "duckclaw.db_write_fire_and_forget.wait_write_task",
        lambda task_id, timeout_sec=0: status,
    )
    return enqueued


def test_read_only_worker_uses_db_writer_with_schema_qualified_table(monkeypatch) -> None:
    enqueued = _patch_writer(monkeypatch, _Status("success"))
    db = _RoVaultDb()
    tools: list = []
    register_record_operational_lesson_skill(tools, {}, db=db, schema_name="finance_worker")
    out = json.loads(tools[0].invoke({"lesson_text": "PRUEBA", "context_trigger": "unit"}))
    assert out["ok"] is True
    assert db.executed == []  # nunca escribe directo sobre el handle RO
    assert len(enqueued) == 1
    q = enqueued[0]["query"]
    assert "INSERT INTO finance_worker.agent_beliefs" in q
    assert "'field_lesson'" in q and "ON CONFLICT (belief_key)" in q
    assert enqueued[0]["user_id"] == "u-123"
    assert enqueued[0]["db_path"].endswith("research_vault.duckdb")
    assert db.suspended == 1 and db.resumed == 1


def test_read_only_worker_writer_failure_returns_ok_false(monkeypatch) -> None:
    _patch_writer(monkeypatch, _Status("failed", "Catalog Error: Table agent_beliefs does not exist"))
    out = json.loads(
        _record_operational_lesson_impl("x", context_trigger="t", db=_RoVaultDb(), schema_name="finance_worker")
    )
    assert out["ok"] is False
    assert "does not exist" in out["error"]


def test_read_only_worker_writer_unconfirmed_returns_ok_false(monkeypatch) -> None:
    _patch_writer(monkeypatch, None)
    out = json.loads(
        _record_operational_lesson_impl("x", context_trigger="t", db=_RoVaultDb(), schema_name="finance_worker")
    )
    assert out["ok"] is False
    assert "Sin confirmación" in out["error"]


class _MemDb:
    """Handle RW en memoria (workers no read_only): escritura directa, comportamiento previo."""

    _read_only = False
    _path = ":memory:"

    def __init__(self) -> None:
        import duckdb

        self.con = duckdb.connect(":memory:")

    def execute(self, sql: str, *_a):
        return self.con.execute(sql).fetchall()


def test_rw_worker_direct_upsert_real_duckdb() -> None:
    from duckclaw.workers.loader import _ensure_agent_beliefs

    db = _MemDb()
    db.execute("CREATE SCHEMA finance_worker")
    _ensure_agent_beliefs(db, "finance_worker")
    for conf in (0.5, 0.9):
        out = json.loads(
            _record_operational_lesson_impl("Regla X", context_trigger="t", confidence_score=conf, db=db, schema_name="finance_worker")
        )
        assert out["ok"] is True
    rows = db.con.execute(
        "SELECT belief_key, belief_kind, context_trigger, lesson_text, confidence_score "
        "FROM finance_worker.agent_beliefs"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][0] == out["belief_key"]
    assert rows[0][1:4] == ("field_lesson", "t", "Regla X")
    assert rows[0][4] == 0.9


def test_rw_worker_missing_table_returns_ok_false() -> None:
    db = _MemDb()
    out = json.loads(_record_operational_lesson_impl("x", db=db, schema_name="finance_worker"))
    assert out["ok"] is False
    assert "finance_worker.agent_beliefs" in out["error"]


def test_register_skips_when_tool_already_present() -> None:
    class _Existing:
        name = "record_operational_lesson"

    tools: list = [_Existing()]
    register_record_operational_lesson_skill(tools, {})
    assert len(tools) == 1


def _catalog_style_record(db, schema_name: str) -> dict:
    """Réplica del skill de catálogo ``skills/record_operational_lesson.py`` (catalog workers)."""
    from duckclaw.workers.field_reflection import lesson_belief_key, persist_field_lesson

    trigger, lesson = "PRUEBA", "lección"
    try:
        key = lesson_belief_key(trigger, lesson)
        persist_field_lesson(db, schema_name, key, trigger, lesson, 0.5)
        return {"ok": True, "belief_key": key}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def test_catalog_skill_read_only_worker_goes_through_db_writer(monkeypatch) -> None:
    enqueued = _patch_writer(monkeypatch, _Status("success"))
    db = _RoVaultDb()
    out = _catalog_style_record(db, "finance_worker")
    assert out["ok"] is True
    assert db.executed == []
    assert "INSERT INTO finance_worker.agent_beliefs" in enqueued[0]["query"]


def test_catalog_skill_failed_write_returns_ok_false(monkeypatch) -> None:
    _patch_writer(monkeypatch, _Status("failed", "Catalog Error: boom"))
    out = _catalog_style_record(_RoVaultDb(), "finance_worker")
    assert out["ok"] is False
    assert "boom" in out["error"]


def test_persist_field_lesson_raise_on_error_false_returns_bool() -> None:
    from duckclaw.workers.field_reflection import persist_field_lesson

    assert persist_field_lesson(_MemDb(), "finance_worker", "lesson_x", "t", "l", 0.5, raise_on_error=False) is False
