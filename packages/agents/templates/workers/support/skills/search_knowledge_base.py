"""Skill: search_knowledge_base — búsqueda en la base de conocimiento (read-only)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool


def get_tools(db: Any, schema_name: str, spec: Any = None) -> list:
    schema = schema_name

    def search_knowledge_base(query: str, limit: int = 5) -> str:
        """Busca en la base de conocimiento por texto. Devuelve title, content y raw_evidence. limit: máximo de resultados (default 5)."""
        try:
            esc = str(query).replace("'", "''")[:300]
            r = db.query(
                f"SELECT id, title, content, raw_evidence FROM {schema}.knowledge_base "
                f"WHERE title LIKE '%' || '{esc}' || '%' OR content LIKE '%' || '{esc}' || '%' OR raw_evidence LIKE '%' || '{esc}' || '%' "
                f"ORDER BY id LIMIT {max(1, min(limit, 20))}"
            )
            return r
        except Exception as e:
            return json.dumps({"error": str(e)})

    return [
        StructuredTool.from_function(
            search_knowledge_base,
            name="search_knowledge_base",
            description="Busca en la base de conocimiento. query: texto a buscar; limit: número de resultados (default 5). Devuelve title, content, raw_evidence.",
        )
    ]
