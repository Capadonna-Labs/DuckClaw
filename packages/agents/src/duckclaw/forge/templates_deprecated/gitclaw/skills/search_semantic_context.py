"""Skill: búsqueda semántica sobre main.semantic_memory (CONTEXT_INJECTION)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool


def get_tools(db: Any, schema_name: str, spec: Any = None) -> list:
    _ = schema_name
    _ = spec

    def search_semantic_context(query: str, limit: int = 3) -> str:
        """
        Recupera fragmentos de contexto inyectado (/context --add) más similares a la consulta.
        Usa embeddings locales; si no hay servicio de embeddings, devuelve cadena vacía.
        """
        q = (query or "").strip()
        if not q:
            return ""
        try:
            from duckclaw.forge.rag.embeddings import embed_text

            emb = embed_text(q)
            if emb is None or len(emb) != 384:
                return ""
            vec_str = "[" + ",".join(str(float(x)) for x in emb) + "]"
            lim = max(1, min(int(limit), 20))
            raw = db.query(
                f"""
                SELECT id, content, source,
                       array_cosine_distance(embedding, {vec_str}::FLOAT[384]) AS dist
                FROM main.semantic_memory
                WHERE embedding IS NOT NULL
                  AND lower(trim(COALESCE(embedding_status, ''))) = 'ready'
                ORDER BY dist ASC
                LIMIT {lim}
                """
            )
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
            if not rows:
                return ""
            lines: list[str] = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                cid = str(row.get("id") or "")
                content = str(row.get("content") or "").strip()
                src = str(row.get("source") or "")
                dist = row.get("dist")
                lines.append(f"- [{cid[:8]}…] ({src}) dist={dist}\n  {content[:500]}")
            return "\n".join(lines) if lines else ""
        except Exception:  # noqa: BLE001
            return ""

    return [
        StructuredTool.from_function(
            search_semantic_context,
            name="search_semantic_context",
            description=(
                "Busca en memoria semántica del usuario (contexto inyectado con /context --add). "
                "query: pregunta o términos; limit: máximo de fragmentos (default 3). "
                "Devuelve texto para el LLM o vacío si no hay embeddings."
            ),
        )
    ]
