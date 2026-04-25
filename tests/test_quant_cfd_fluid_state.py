"""quant_core.fluid_state se crea on-demand si la bóveda no tenía la tabla."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from duckclaw.forge.skills.quant_cfd_bridge import _record_fluid_state_impl


def test_record_fluid_state_ensures_table(tmp_path: Path) -> None:
    path = tmp_path / "vault.duckdb"
    con = duckdb.connect(str(path))

    class _Db:
        def execute(self, sql: str, params: object | None = None) -> None:
            if params is not None:
                con.execute(sql, params)
            else:
                con.execute(sql)

    raw = _record_fluid_state_impl(
        _Db(),
        ticker="SPY",
        phase="SOLID",
        temperature=0.001,
    )
    assert json.loads(raw).get("status") == "ok"
    n = con.execute("SELECT COUNT(*) FROM quant_core.fluid_state").fetchone()[0]
    assert int(n) == 1
