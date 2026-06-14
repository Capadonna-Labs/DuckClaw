from __future__ import annotations

import json
from pathlib import Path

from duckclaw import DuckClaw


def test_execute_binds_params_without_sql_interpolation(tmp_path: Path) -> None:
    db = DuckClaw(str(tmp_path / "params.duckdb"))
    payload = "O'Reilly'); DROP TABLE secure_values; --"
    try:
        db.execute("CREATE TABLE secure_values (id INTEGER, value VARCHAR)")
        db.execute("INSERT INTO secure_values VALUES (?, ?)", [1, payload])

        raw = db.query("SELECT id, value FROM secure_values")
        rows = json.loads(raw)

        assert rows == [{"id": "1", "value": payload}]
    finally:
        db.close()
