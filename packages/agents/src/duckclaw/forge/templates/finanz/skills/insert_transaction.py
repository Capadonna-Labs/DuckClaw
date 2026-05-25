"""Skill: insert_transaction — registra un movimiento en finance_worker.transactions."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool


def get_tools(db: Any, schema_name: str, spec: Any = None) -> list:
    schema = schema_name

    def insert_transaction(amount: float, description: str, category_id: int = 1, tx_date: str = "") -> str:
        """Inserta una transacción. amount: número; description: texto; category_id: id de categoría (default 1); tx_date: opcional YYYY-MM-DD."""
        try:
            date_val = f"DATE '{tx_date}'" if tx_date else "CURRENT_DATE"
            esc_desc = str(description).replace("'", "''")[:500]
            next_row = db.query(
                f"SELECT COALESCE(MAX(id), 0) + 1 AS next_id FROM {schema}.transactions"
            )
            rows = json.loads(next_row) if isinstance(next_row, str) else (next_row or [])
            next_id = int(rows[0].get("next_id", 1)) if rows and isinstance(rows[0], dict) else 1
            db.execute(
                f"INSERT INTO {schema}.transactions (id, amount, description, category_id, tx_date) "
                f"VALUES ({next_id}, {float(amount)}, '{esc_desc}', {int(category_id)}, {date_val})"
            )
            return json.dumps(
                {"status": "ok", "message": "Transacción registrada.", "id": next_id}
            )
        except Exception as e:
            return json.dumps({"error": str(e)})

    return [
        StructuredTool.from_function(
            insert_transaction,
            name="insert_transaction",
            description="Registra un gasto o ingreso. amount (número), description (texto), category_id (opcional, default 1), tx_date (opcional YYYY-MM-DD).",
        )
    ]
