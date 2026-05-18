"""DuckDB read-only helpers for admin explorer (tabular, PGQ, vector). Spec: ADMIN_DUCKDB_EXPLORER.md."""

from __future__ import annotations

import json
import os
import re
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

_SEMANTIC_MEMORY_TABLE = "main.semantic_memory"
_VECTOR_LIMIT_DEFAULT = 10
_VECTOR_LIMIT_MAX = 40
_SELECT_LIMIT_DEFAULT = 500
_FORBIDDEN_SQL = re.compile(
    r"\b(insert|update|delete|drop|create|alter|attach|detach|copy|truncate|grant|revoke|call|execute)\b",
    re.IGNORECASE,
)
_LIMIT_RE = re.compile(r"\blimit\s+\d+", re.IGNORECASE)


class SemanticMemoryNotInitializedError(Exception):
    """Raised when main.semantic_memory is missing."""

    code = "semantic_memory_not_initialized"


def _repo_root() -> Path:
    raw = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    if raw:
        return Path(raw)
    return Path(__file__).resolve().parent.parent.parent.parent


def resolve_vault_path(vault_path: str | None) -> str:
    from duckclaw.gateway_db import get_gateway_db_path

    raw = (vault_path or "").strip()
    if raw:
        abs_path = raw if os.path.isabs(raw) else str(_repo_root() / raw.lstrip("/"))
        if not os.path.isfile(abs_path):
            raise FileNotFoundError(f"Vault no encontrado: {vault_path}")
        return abs_path
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise FileNotFoundError("Gateway DuckDB no configurada (DUCKCLAW_FINANZ_DB_PATH)")
    return gw


def connect_readonly(path: str) -> Any:
    import duckdb

    return duckdb.connect(path, read_only=True)


class _DuckDbQueryAdapter:
    """Adaptador mínimo `.query()` para reutilizar semantic_memory_hybrid."""

    def __init__(self, con: Any) -> None:
        self._con = con

    def query(self, sql: str) -> str:
        result = self._con.execute(sql)
        rows = result.fetchall()
        names = [d[0] for d in (result.description or [])]
        out = [dict(zip(names, (_json_cell(v) for v in row))) for row in rows]
        return json.dumps(out, ensure_ascii=False)


def _try_load_vss(con: Any) -> None:
    for stmt in (
        "INSTALL vss FROM community",
        "LOAD vss",
    ):
        try:
            con.execute(stmt)
        except Exception:
            pass


def validate_readonly_sql(sql: str) -> None:
    q = (sql or "").strip()
    if not q:
        raise ValueError("Query vacía")
    if ";" in q.rstrip(";"):
        raise ValueError("Solo se permite una sentencia SQL")
    if _FORBIDDEN_SQL.search(q):
        raise ValueError("Solo se permiten consultas SELECT o WITH (read-only)")
    head = q.lstrip()[:12].lower()
    if not (head.startswith("select") or head.startswith("with")):
        raise ValueError("Solo se permiten consultas SELECT o WITH (read-only)")


def enforce_select_limit(sql: str, max_rows: int = _SELECT_LIMIT_DEFAULT) -> tuple[str, bool]:
    q = (sql or "").strip().rstrip(";")
    if _LIMIT_RE.search(q):
        return q, False
    return f"SELECT * FROM ({q}) AS _admin_q LIMIT {max_rows}", True


def _json_cell(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (list, dict)):
        return value
    return str(value)


def fetch_table_catalog(con: Any) -> dict[str, Any]:
    rows = con.execute(
        """
        SELECT table_schema, table_name
        FROM information_schema.tables
        WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
        ORDER BY table_schema, table_name
        """
    ).fetchall()
    schemas: dict[str, list[str]] = {}
    for schema, name in rows:
        sch = str(schema or "main")
        tbl = str(name or "")
        if not tbl:
            continue
        schemas.setdefault(sch, []).append(tbl)
    return {"schemas": schemas}


def execute_select(con: Any, sql: str) -> dict[str, Any]:
    validate_readonly_sql(sql)
    bounded, limit_applied = enforce_select_limit(sql)
    cur = con.execute(bounded)
    cols = [str(d[0]) for d in (cur.description or [])]
    raw_rows = cur.fetchall()
    rows = [[_json_cell(c) for c in row] for row in raw_rows]
    out: dict[str, Any] = {
        "columns": cols,
        "rows": rows,
        "row_count": len(rows),
    }
    if limit_applied:
        out["limit_applied"] = _SELECT_LIMIT_DEFAULT
    return out


def _table_exists(con: Any, name: str) -> bool:
    try:
        row = con.execute(
            """
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_schema || '.' || table_name = ?
               OR table_name = ?
            """,
            [name, name.split(".")[-1]],
        ).fetchone()
        return bool(row and int(row[0]) > 0)
    except Exception:
        return False


def fetch_pgq_graph(
    con: Any,
    *,
    max_nodes: int = 500,
    max_edges: int = 2000,
) -> dict[str, Any]:
    if not _table_exists(con, "memory_nodes") or not _table_exists(con, "memory_edges"):
        return {"nodes": [], "links": [], "warning": "Tablas memory_nodes/memory_edges no encontradas"}

    node_rows = con.execute(
        f"""
        SELECT node_id,
               COALESCE(
                 NULLIF(trim(json_extract_string(CAST(properties AS JSON), '$.name')), ''),
                 node_id
               ) AS label,
               COALESCE(label, 'unknown') AS grp
        FROM memory_nodes
        LIMIT {int(max_nodes)}
        """
    ).fetchall()
    nodes = [
        {"id": str(r[0]), "label": str(r[1] or r[0]), "group": str(r[2] or "unknown")}
        for r in node_rows
    ]
    node_ids = {n["id"] for n in nodes}

    edge_rows = con.execute(
        f"""
        SELECT source_id, target_id, relationship
        FROM memory_edges
        LIMIT {int(max_edges)}
        """
    ).fetchall()
    links = []
    for src, tgt, rel in edge_rows:
        s, t = str(src), str(tgt)
        if s in node_ids and t in node_ids:
            links.append({"source": s, "target": t, "label": str(rel or "")})
    return {"nodes": nodes, "links": links}


def ensure_semantic_memory_table(con: Any) -> None:
    if not _table_exists(con, _SEMANTIC_MEMORY_TABLE):
        raise SemanticMemoryNotInitializedError(
            "La memoria vectorial aún no ha sido inicializada (tabla main.semantic_memory ausente)."
        )


def _row_to_vector_dto(row: dict[str, Any]) -> dict[str, Any]:
    created = row.get("created_at")
    if created is not None and not isinstance(created, str):
        created = _json_cell(created)
    dist = row.get("dist")
    if dist is not None:
        try:
            dist = float(dist)
        except (TypeError, ValueError):
            dist = None
    return {
        "id": str(row.get("id") or ""),
        "text": str(row.get("content") or ""),
        "metadata": {
            "source": str(row.get("source") or ""),
            "created_at": created,
            "embedding_status": str(row.get("embedding_status") or ""),
        },
        "distance": dist,
    }


def fetch_recent_semantic_memory(con: Any, limit: int) -> list[dict[str, Any]]:
    ensure_semantic_memory_table(con)
    lim = max(1, min(int(limit), _VECTOR_LIMIT_MAX))
    rows = con.execute(
        f"""
        SELECT id, content, source, embedding_status, created_at, NULL::DOUBLE AS dist
        FROM {_SEMANTIC_MEMORY_TABLE}
        ORDER BY created_at DESC NULLS LAST
        LIMIT {lim}
        """
    ).fetchall()
    out = []
    for r in rows:
        out.append(
            _row_to_vector_dto(
                {
                    "id": r[0],
                    "content": r[1],
                    "source": r[2],
                    "embedding_status": r[3],
                    "created_at": r[4],
                    "dist": r[5],
                }
            )
        )
    return out


def search_semantic_memory_admin(con: Any, query: str, limit: int) -> tuple[list[dict[str, Any]], str, str | None]:
    ensure_semantic_memory_table(con)
    _try_load_vss(con)
    from duckclaw.forge.atoms.semantic_memory_hybrid import search_semantic_memory_hybrid

    lim = max(1, min(int(limit), _VECTOR_LIMIT_MAX))
    rows, diag = search_semantic_memory_hybrid(_DuckDbQueryAdapter(con), query, lim)
    mode = str(diag.get("mode") or "none")
    warning: str | None = None
    if mode == "lexical":
        warning = "Búsqueda léxica (embeddings no disponibles o sin filas READY con vector)."
    elif mode == "none":
        warning = "Sin coincidencias para la consulta."
    return [_row_to_vector_dto(r) for r in rows], mode, warning


def run_vector_search(con: Any, query: str | None, limit: int) -> dict[str, Any]:
    q = (query or "").strip()
    lim = max(1, min(int(limit or _VECTOR_LIMIT_DEFAULT), _VECTOR_LIMIT_MAX))
    if not q:
        results = fetch_recent_semantic_memory(con, lim)
        return {"results": results, "mode": "recent", "warning": None}
    results, mode, warning = search_semantic_memory_admin(con, q, lim)
    return {"results": results, "mode": mode, "warning": warning}
