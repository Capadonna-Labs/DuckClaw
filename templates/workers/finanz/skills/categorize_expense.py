"""Skill: categorize_expense — lista categorías o sugiere/asigna categoría a una descripción."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool


def get_tools(db: Any, schema_name: str, spec: Any = None) -> list:
    schema = schema_name

    def list_categories() -> str:
        """Lista todas las categorías disponibles (id, name)."""
        try:
            return db.query(f"SELECT id, name FROM {schema}.categories ORDER BY id")
        except Exception as e:
            return json.dumps({"error": str(e)})

    def categorize_expense(description: str, category_id: int) -> str:
        """Asocia una categoría a una transacción por descripción: actualiza category_id de la última transacción que coincida."""
        try:
            esc = str(description).replace("'", "''")[:200]
            db.execute(
                f"UPDATE {schema}.transactions SET category_id = {int(category_id)} "
                f"WHERE id = (SELECT id FROM {schema}.transactions WHERE description LIKE '%' || '{esc}' || '%' ORDER BY created_at DESC LIMIT 1)"
            )
            return json.dumps({"status": "ok"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    return [
        StructuredTool.from_function(
            list_categories,
            name="list_categories",
            description="Lista las categorías disponibles (id, name). Úsalo antes de insert_transaction o categorize_expense.",
        ),
        StructuredTool.from_function(
            categorize_expense,
            name="categorize_expense",
            description="Asigna una categoría (category_id) a una transacción existente por descripción. Usa list_categories para ver los id.",
        ),
    ]
