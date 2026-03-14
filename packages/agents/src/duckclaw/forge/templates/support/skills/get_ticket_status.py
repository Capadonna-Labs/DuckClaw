"""Skill: get_ticket_status — consulta estado de un ticket (read-only)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool


def get_tools(db: Any, schema_name: str, spec: Any = None) -> list:
    schema = schema_name

    def get_ticket_status(ticket_ref: str) -> str:
        """Devuelve el estado y resumen de un ticket por referencia (ticket_ref)."""
        try:
            esc = str(ticket_ref).replace("'", "''")[:100]
            r = db.query(
                f"SELECT id, ticket_ref, status, summary, created_at FROM {schema}.tickets "
                f"WHERE ticket_ref = '{esc}' OR CAST(id AS VARCHAR) = '{esc}' LIMIT 1"
            )
            return r
        except Exception as e:
            return json.dumps({"error": str(e)})

    return [
        StructuredTool.from_function(
            get_ticket_status,
            name="get_ticket_status",
            description="Consulta el estado de un ticket por referencia o id. ticket_ref: número o código del ticket.",
        )
    ]
