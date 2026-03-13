"""Skill: catalog_retriever — búsqueda semántica RAG sobre catálogo (DuckDB VSS).

Spec: specs/DuckDB_Native_RAG_Vector_Search.md
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool


def get_tools(db: Any, schema_name: str, spec: Any = None) -> list:
    from duckclaw.forge.rag import ensure_catalog_schema, search_catalog_semantic, embed_text

    def catalog_retriever(user_query: str, limit: int = 5) -> str:
        """
        Búsqueda semántica en el catálogo de productos. Usa embeddings locales (RAG).
        Si el catálogo vectorial está vacío, sugiere usar el pipeline de ingesta.
        """
        query = (user_query or "").strip()
        if not query:
            return json.dumps({"message": "Query vacía.", "results": []})

        # Asegurar esquema
        ensure_catalog_schema(db, schema_name)

        # Vectorizar query
        embedding = embed_text(query)
        if embedding is None:
            # Fallback: búsqueda por LIKE en products (sin embeddings)
            try:
                esc = query.replace("'", "''")[:300]
                r = db.query(
                    f"SELECT id as sku, name, description, category as stock_status, price "
                    f"FROM {schema_name}.products "
                    f"WHERE name LIKE '%' || '{esc}' || '%' OR description LIKE '%' || '{esc}' || '%' "
                    f"LIMIT {max(1, min(limit, 20))}"
                )
                rows = json.loads(r) if isinstance(r, str) else (r or [])
                return json.dumps({
                    "message": "Búsqueda por texto (embeddings no disponibles).",
                    "results": rows,
                })
            except Exception as e:
                return json.dumps({"error": str(e), "results": []})

        # Búsqueda semántica
        results = search_catalog_semantic(db, schema_name, embedding, limit=limit)
        if not results:
            # Fallback: búsqueda por LIKE en products
            try:
                esc = query.replace("'", "''")[:300]
                r = db.query(
                    f"SELECT id as sku, name, description, category as stock_status, price "
                    f"FROM {schema_name}.products "
                    f"WHERE name LIKE '%' || '{esc}' || '%' OR description LIKE '%' || '{esc}' || '%' "
                    f"LIMIT {max(1, min(limit, 20))}"
                )
                rows = json.loads(r) if isinstance(r, str) else (r or [])
                if rows:
                    return json.dumps({"message": "Búsqueda por texto (catálogo vectorial vacío).", "results": rows})
            except Exception:
                pass
            return json.dumps({
                "message": "No hay productos coincidentes. Ejecuta el pipeline de ingesta: python -m duckclaw.forge.rag.knowledge_loader catalogo.csv",
                "results": [],
            })
        # Quitar dist del output para el LLM
        for r in results:
            r.pop("dist", None)
        return json.dumps({"results": results})

    return [
        StructuredTool.from_function(
            catalog_retriever,
            name="catalog_retriever",
            description="Búsqueda semántica en el catálogo de productos. Usa SIEMPRE para consultas de producto, precio o disponibilidad. user_query: pregunta del cliente; limit: máx resultados (default 5).",
        )
    ]
