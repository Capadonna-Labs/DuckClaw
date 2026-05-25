"""insert_transaction asigna id secuencial (DuckDB sin autoincrement)."""

from __future__ import annotations

from pathlib import Path

import pytest

from duckclaw import DuckClaw


@pytest.fixture
def finanz_db(tmp_path):
    path = str(tmp_path / "insert_tx.duckdb")
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    db = DuckClaw(path)
    db.execute(
        """
        CREATE SCHEMA IF NOT EXISTS finance_worker;
        CREATE TABLE IF NOT EXISTS finance_worker.transactions (
          id INTEGER PRIMARY KEY,
          amount REAL NOT NULL,
          description VARCHAR,
          category_id INTEGER,
          tx_date DATE DEFAULT CURRENT_DATE,
          created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        INSERT INTO finance_worker.transactions (id, amount, description, category_id)
        VALUES (89, -10.0, 'seed-a', 1), (90, -20.0, 'seed-b', 1);
        """
    )
    return db


def test_insert_transaction_assigns_next_id(finanz_db) -> None:
    from duckclaw.forge.templates.finanz.skills.insert_transaction import get_tools

    tool = get_tools(finanz_db, "finance_worker")[0]
    raw = tool.invoke(
        {"amount": -5600, "description": "Jugo Hit", "category_id": 9, "tx_date": "2026-05-24"}
    )
    assert '"status": "ok"' in raw or '"status":"ok"' in raw.replace(" ", "")
    assert '"id": 91' in raw.replace(" ", "") or '"id":91' in raw.replace(" ", "")

    rows = finanz_db.query(
        "SELECT id, description FROM finance_worker.transactions WHERE id = 91"
    )
    import json

    parsed = json.loads(rows) if isinstance(rows, str) else rows
    assert parsed and parsed[0].get("description") == "Jugo Hit"
