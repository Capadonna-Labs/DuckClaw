from __future__ import annotations

import pytest

from duckclaw.graphs import sandbox as sb


@pytest.mark.parametrize("injected", ["", "Error exportando datos: Catalog Error: table x does not exist"])
def test_failed_data_sql_stops_the_run_with_the_reason(monkeypatch: pytest.MonkeyPatch, injected: str) -> None:
    monkeypatch.setattr(sb, "_docker_available", lambda: True)
    monkeypatch.setattr(sb, "_get_manager", lambda: object())
    monkeypatch.setattr(sb, "_touch_session", lambda sid: None)
    monkeypatch.setattr(sb, "reap_idle_sandboxes", lambda keep=None: None)
    monkeypatch.setattr(sb, "data_inject", lambda db, sql, sid: injected)
    res = sb.run_in_sandbox(db=None, llm=None, code="print(1)", data_sql="SELECT 1", session_id="t")
    assert res.exit_code == 1 and "data_sql no generó data.csv" in res.stderr
    assert (injected.split(": ", 1)[-1] if injected else "no devolvió filas") in res.stderr
