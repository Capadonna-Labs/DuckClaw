"""Shared PGQ graph fetch from memory_nodes/memory_edges."""

from __future__ import annotations

from typing import Any


def _table_exists(con: Any, schema: str, name: str) -> bool:
    row = con.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = ? AND table_name = ?
        LIMIT 1
        """,
        [schema, name],
    ).fetchone()
    return row is not None


def fetch_pgq_graph_data(
    con: Any,
    *,
    max_nodes: int = 500,
    max_edges: int = 2000,
) -> dict[str, Any]:
    if not _table_exists(con, "main", "memory_nodes") or not _table_exists(con, "main", "memory_edges"):
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
