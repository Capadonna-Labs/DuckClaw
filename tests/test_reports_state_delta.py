"""db-writer reports state delta handler + DTO."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

_REPO = Path(__file__).resolve().parent.parent
_WRITER = _REPO / "services" / "db-writer"
if str(_WRITER) not in sys.path:
    sys.path.append(str(_WRITER))

from models.reports_state_delta import CustomReportMutation, ReportsStateDelta  # noqa: E402
from reports_state_delta_handler import (  # noqa: E402
    _sync_handle_reports_state_delta,
    report_update_channel,
)


def test_reports_state_delta_roundtrip() -> None:
    delta = ReportsStateDelta(
        tenant_id="default",
        user_id="u1",
        target_db_path="/tmp/vault.duckdb",
        mutation=CustomReportMutation(
            report_id="chat-abc",
            title="Uso LLM",
            html_content="<!DOCTYPE html><html><body><h1>OK</h1></body></html>",
            created_by="admin@test",
        ),
    )
    raw = delta.model_dump_json()
    back = ReportsStateDelta.model_validate(json.loads(raw))
    assert back.delta_type == "CUSTOM_REPORT_UPSERT"
    assert back.mutation.report_id == "chat-abc"


def test_apply_custom_report_upsert(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "vault.duckdb"
    duckdb.connect(str(db_path)).close()

    published: list[str] = []

    def _fake_publish(report_id: str) -> None:
        published.append(report_id)

    monkeypatch.setattr(
        "reports_state_delta_handler.validate_user_db_path",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr("reports_state_delta_handler._publish_report_reload", _fake_publish)

    html = "<!DOCTYPE html><html><head></head><body><p>v1</p></body></html>"
    payload = {
        "delta_type": "CUSTOM_REPORT_UPSERT",
        "tenant_id": "default",
        "user_id": "u1",
        "target_db_path": str(db_path),
        "mutation": {
            "report_id": "chat-abc",
            "title": "Dashboard",
            "html_content": html,
            "created_by": "admin",
        },
    }
    _sync_handle_reports_state_delta(json.dumps(payload))

    con = duckdb.connect(str(db_path))
    row = con.execute(
        "SELECT title, html_content, version FROM main.custom_reports WHERE report_id = 'chat-abc'"
    ).fetchone()
    con.close()
    assert row is not None
    assert row[0] == "Dashboard"
    assert "v1" in row[1]
    assert row[2] == 1
    assert published == ["chat-abc"]

    payload["mutation"]["html_content"] = "<!DOCTYPE html><html><body><p>v2</p></body></html>"
    _sync_handle_reports_state_delta(json.dumps(payload))
    con2 = duckdb.connect(str(db_path))
    row2 = con2.execute(
        "SELECT version FROM main.custom_reports WHERE report_id = 'chat-abc'"
    ).fetchone()
    con2.close()
    assert row2 is not None
    assert row2[0] == 2


def test_report_update_channel() -> None:
    assert report_update_channel("r1") == "duckclaw:report-update:r1"


def test_validate_html_content_rejects_incomplete() -> None:
    from duckclaw.forge.skills.custom_reports_bridge import _validate_html_content

    assert _validate_html_content("<div>sin html</div>") is not None
    assert _validate_html_content("<!DOCTYPE html><html><body></body></html>") is None
