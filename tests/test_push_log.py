"""push_log: one row per push sent, as a typed command for the DB-Writer, recorded fire-and-forget from the single send function."""
from __future__ import annotations

import json

import duckdb

from duckclaw.write_commands import AppendPushLogCommand


def test_command_roundtrip() -> None:
    raw = json.loads(AppendPushLogCommand(id="PUSH-1", title="CEG sube", body="detalle", tag="alert", sent=2).to_redis_payload())
    assert raw["command_type"] == "append_push_log" and raw["sent"] == 2 and raw["title"] == "CEG sube"


def test_handler_inserts_and_clamps() -> None:
    from duckclaw.write_handlers.usage_logs import _apply_append_push_log

    con = duckdb.connect(":memory:")
    _apply_append_push_log(con, {"id": "PUSH-1", "title": "t" * 300, "body": "b" * 900, "sent": -1, "failed": 3})
    assert con.execute("SELECT length(title), length(body), sent, failed, tenant_id FROM push_log").fetchone() == (120, 512, 0, 3, "default")


def test_send_records_the_push_and_never_fails_on_a_logging_error(monkeypatch) -> None:
    import sys
    import types

    from duckclaw import db_write_fire_and_forget, gateway_db, web_push

    sent: list = []
    monkeypatch.setenv("WEB_PUSH_VAPID_PUBLIC_KEY", "pub")
    monkeypatch.setenv("WEB_PUSH_VAPID_PRIVATE_KEY", "priv")
    monkeypatch.setattr(gateway_db, "get_gateway_db_path", lambda: "/tmp/hub.duckdb")
    monkeypatch.setattr(db_write_fire_and_forget, "enqueue_write_command", lambda command, db_path, user_id: sent.append(command) or "t")
    fake = types.ModuleType("pywebpush")
    fake.WebPushException = RuntimeError
    fake.webpush = lambda **_k: None
    monkeypatch.setitem(sys.modules, "pywebpush", fake)

    result = web_push.send_web_push_notifications([{"endpoint": "e"}], title="x" * 50, body="cuerpo", tag="alert")
    assert result.sent == 1
    (command,) = sent
    assert command.tag == "alert" and command.sent == 1 and command.title.endswith("…") and "x" * 50 in command.body   # as the device shows it

    def boom(*_a, **_k):
        raise RuntimeError("redis down")

    monkeypatch.setattr(db_write_fire_and_forget, "enqueue_write_command", boom)
    assert web_push.send_web_push_notifications([{"endpoint": "e"}], title="t", body="b").sent == 1
