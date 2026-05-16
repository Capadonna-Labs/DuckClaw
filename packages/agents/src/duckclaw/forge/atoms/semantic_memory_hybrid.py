"""Búsqueda híbrida en main.semantic_memory: vector si hay embeddings disponibles; si no, léxico.

El Gateway suele ejecutarse sin PyTorch ni DUCKCLAW_MLX_EMBEDDINGS_URL; sin esto embed_text=None
y la VSS “silenciosa”. El fallback permite buscar contenido persisted (READY, PENDING o FAILED).

Spec alineación: specs/features/quant/QUANT_MOC_MACRO_PGQ_VSS.md + specs/features/finanz/FINANZ_CONTEXT_INJECTION_TELEGRAM.md.
"""

from __future__ import annotations

import json
import re
from typing import Any

_LEX_SKIP = frozenset(
    {
        "el",
        "la",
        "los",
        "las",
        "de",
        "del",
        "que",
        "con",
        "por",
        "para",
        "una",
        "uno",
        "the",
        "and",
        "for",
        "with",
        "busca",
        "buscar",
        "insights",
        "search",
        "semantic",
        "context",
        "con",
        "sin",
        "del",
        "los",
        "las",
        "por",
        "sobre",
    }
)


def lexical_tokens(query: str, *, max_tokens: int = 8) -> list[str]:
    blob = (query or "").strip().lower()
    if not blob:
        return []
    toks = re.findall(r"\w+", blob, flags=re.UNICODE)
    out: list[str] = []
    for raw in toks:
        w = raw.strip().lower()[:48]
        if len(w) < 2:
            continue
        if w in _LEX_SKIP:
            continue
        out.append(w)
        if len(out) >= max_tokens:
            break
    if out:
        return out
    condensed = "".join(c for c in blob if c.isalnum())
    return [condensed[:48]] if len(condensed) >= 3 else []


def _query_json_rows(db: Any, sql: str) -> list[dict[str, Any]]:
    raw = db.query(sql)
    rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    return [r for r in rows if isinstance(r, dict)]


def fetch_semantic_rows_vector(db: Any, *, query: str, limit: int) -> list[dict[str, Any]]:
    """Vecinos por coseno; sólo filas READY con embedding."""
    from duckclaw.forge.rag.embeddings import embed_text

    q = (query or "").strip()
    if not q:
        return []
    emb = embed_text(q)
    if emb is None or len(emb) != 384:
        return []
    vec_str = "[" + ",".join(str(float(x)) for x in emb) + "]"
    lim = max(1, min(int(limit), 40))
    sql = (
        "SELECT id, content, source, embedding_status,"
        "       array_cosine_distance(embedding, "
        + vec_str
        + "::FLOAT[384]) AS dist "
        + "FROM main.semantic_memory "
        "WHERE embedding IS NOT NULL "
        "  AND lower(trim(COALESCE(embedding_status, ''))) = 'ready' "
        "ORDER BY dist ASC "
        f"LIMIT {lim}"
    )
    return _query_json_rows(db, sql)


def fetch_semantic_rows_lexical(
    db: Any, *, query: str, limit: int
) -> list[dict[str, Any]]:
    """Substring seguro sobre cualquier chunk con contenido (incluye PENDING sin vector)."""
    toks = lexical_tokens(query)
    if not toks:
        return []
    lim = max(1, min(int(limit), 40))
    predicates: list[str] = []
    for t in toks:
        safe = (t or "").strip()[:96]
        if not safe:
            continue
        slit = safe.replace("'", "''")
        escaped = f"'{slit}'"
        predicates.append(
            f"strpos(lower(COALESCE(content,'')), lower({escaped})) >= 1"
        )
    where_body = "\n OR ".join(predicates) if predicates else "FALSE"
    sql = (
        "SELECT id, content, source, embedding_status, "
        "       NULL AS dist "
        "FROM main.semantic_memory "
        f"WHERE length(trim(COALESCE(content,''))) >= 12\n AND ({where_body}) "
        "ORDER BY "
        "  CASE WHEN lower(trim(COALESCE(embedding_status,''))) = 'ready' "
        "       AND embedding IS NOT NULL THEN 0 ELSE 1 END, "
        "  created_at DESC "
        f"LIMIT {lim}"
    )
    return _query_json_rows(db, sql)


def search_semantic_memory_hybrid(
    db: Any,
    query: str,
    limit: int,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """
    Devuelve (filas, diagnóstico). Prioridad: vector READY; si no hay embedding runtime o viene
    vacío, lexical sobre texto crudo (incluye filas sólo texto / embed pendiente).
    """
    q = (query or "").strip()
    diag: dict[str, Any] = {"vector_attempted": False, "mode": "none"}
    if not q:
        return [], diag
    vec_rows = fetch_semantic_rows_vector(db, query=q, limit=limit)
    diag["vector_attempted"] = True
    if vec_rows:
        diag["mode"] = "vector"
        return vec_rows[:limit], diag
    lx = fetch_semantic_rows_lexical(db, query=q, limit=limit)
    if lx:
        diag["mode"] = "lexical"
        diag["tokens"] = lexical_tokens(q)[:6]
        return lx[:limit], diag
    diag["tokens"] = lexical_tokens(q)[:6]
    return [], diag


def semantic_rows_for_chunks(db: Any, query: str, limit: int) -> list[dict[str, Any]]:
    """API única para MOC/perfil — misma política que el skill."""
    rows, _diag = search_semantic_memory_hybrid(db, query, limit)
    return rows
