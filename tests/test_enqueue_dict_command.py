"""Dict payloads on db write queue (report engine bridge)."""

from __future__ import annotations

import duckdb

from duckclaw.db_write_queue import enqueue_dict_command


def test_enqueue_dict_command_upsert_report_template(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "hub.duckdb"
    duckdb.connect(str(db_path)).close()

    monkeypatch.setattr("duckclaw.db_write_queue.spawn_inline_writes_enabled", lambda: True)
    monkeypatch.setattr(
        "duckclaw.db_write_queue._validate_write_target",
        lambda **_: None,
    )

    task_id = enqueue_dict_command(
        {
            "command_type": "upsert_report_template",
            "template_id": "tpl_dict",
            "tenant_id": "default",
            "actor_email": "user@example.com",
            "name": "Dict template",
            "template_uri": "/vault/d.docx",
            "section_schema": [{"id": "body", "label": "Body"}],
            "analyzer_mode": "jinja",
        },
        db_path=str(db_path),
        user_id="user@example.com",
    )
    assert task_id

    con = duckdb.connect(str(db_path), read_only=True)
    row = con.execute(
        "SELECT name FROM main.admin_report_templates WHERE template_id = 'tpl_dict'"
    ).fetchone()
    assert row is not None
    assert row[0] == "Dict template"
