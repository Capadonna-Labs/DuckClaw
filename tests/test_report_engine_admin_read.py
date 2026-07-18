"""Report Engine read-model — compat DuckClaw.execute vs duckdb cursor."""

from __future__ import annotations

import duckdb

from duckclaw.report_engine.admin_report_read import list_report_templates


class _DuckClawLikeDb:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params: list | None = None):
        if params is not None:
            self._con.execute(sql, params)
        else:
            self._con.execute(sql)
        return self._con.fetchall()


def test_list_report_templates_with_duckclaw_like_execute(tmp_path) -> None:
    from duckclaw.schema_migrations import run_pending_migrations
    from duckclaw.write_command_handlers import dispatch_command

    db_path = tmp_path / "hub.duckdb"
    con = duckdb.connect(str(db_path))
    run_pending_migrations(con)
    dispatch_command(
        con,
        {
            "command_type": "upsert_report_template",
            "template_id": "tpl_ro",
            "tenant_id": "default",
            "actor_email": "user@example.com",
            "name": "Informe RO",
            "template_uri": "/vault/t.docx",
            "section_schema": [{"id": "intro", "label": "Intro"}],
            "analyzer_mode": "jinja",
        },
    )
    con.close()

    wrapper = _DuckClawLikeDb(duckdb.connect(str(db_path), read_only=True))
    rows = list_report_templates(
        wrapper,
        tenant_id="default",
        actor_email="user@example.com",
        limit=10,
    )
    assert len(rows) == 1
    assert rows[0]["template_id"] == "tpl_ro"


def test_list_report_instances_lean_omits_preview_html_payload(tmp_path) -> None:
    from duckclaw.report_engine.admin_report_read import list_report_instances
    from duckclaw.schema_migrations import run_pending_migrations
    from duckclaw.write_command_handlers import dispatch_command

    db_path = tmp_path / "hub.duckdb"
    con = duckdb.connect(str(db_path))
    run_pending_migrations(con)
    dispatch_command(
        con,
        {
            "command_type": "upsert_report_template",
            "template_id": "tpl_lean",
            "tenant_id": "default",
            "actor_email": "user@example.com",
            "name": "Lean",
            "template_uri": "/vault/t.docx",
            "section_schema": [{"id": "intro", "label": "Intro", "required": True}],
            "analyzer_mode": "jinja",
        },
    )
    dispatch_command(
        con,
        {
            "command_type": "create_report_instance",
            "instance_id": "rpt_lean",
            "template_id": "tpl_lean",
            "tenant_id": "default",
            "actor_email": "user@example.com",
            "title": "Doc lean",
        },
    )
    huge = "<html>" + ("x" * 50_000) + "</html>"
    con.execute(
        "UPDATE main.admin_report_instances SET preview_html = ? WHERE instance_id = ?",
        [huge, "rpt_lean"],
    )
    con.close()

    wrapper = _DuckClawLikeDb(duckdb.connect(str(db_path), read_only=True))
    lean = list_report_instances(
        wrapper,
        tenant_id="default",
        actor_email="user@example.com",
        lean=True,
    )
    full = list_report_instances(
        wrapper,
        tenant_id="default",
        actor_email="user@example.com",
        lean=False,
    )
    assert len(lean) == 1
    assert lean[0]["preview_html"] == ""
    assert "progress" in lean[0]
    assert full[0]["preview_html"] == huge
