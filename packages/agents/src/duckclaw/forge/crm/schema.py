"""
Schema CRM: memory_nodes, memory_edges, property graph powerseal_crm.

Spec: specs/Sovereign_CRM_Memoria_Bicameral_DuckDB_PGQ.md
"""

from __future__ import annotations

import os
from typing import Any

# Ontología B2B Power Seal
CRM_NODE_LABELS = frozenset({"Lead", "Company", "Product"})
CRM_RELATIONSHIPS = frozenset({"WORKS_AT", "INTERESTED_IN", "PURCHASED"})

_CRM_GRAPH_AVAILABLE: bool | None = None


def _crm_pgq_available(db: Any) -> bool:
    global _CRM_GRAPH_AVAILABLE
    if _CRM_GRAPH_AVAILABLE is not None:
        return _CRM_GRAPH_AVAILABLE
    try:
        db.execute("INSTALL duckpgq FROM community;")
        db.execute("LOAD duckpgq;")
        _CRM_GRAPH_AVAILABLE = True
    except Exception:
        _CRM_GRAPH_AVAILABLE = False
    return _CRM_GRAPH_AVAILABLE


def _json_sql_type(db: Any) -> str:
    home = (os.environ.get("DUCKCLAW_TEST_DUCKDB_HOME") or "").strip()
    if home:
        esc = home.replace("'", "''")
        try:
            db.execute(f"SET home_directory='{esc}'")
        except Exception:
            pass
    for stmt in ("INSTALL json;", "LOAD json;"):
        try:
            db.execute(stmt)
        except Exception:
            pass
    try:
        db.execute("SELECT '{}'::JSON")
        return "JSON"
    except Exception:
        return "VARCHAR"


def ensure_crm_graph_schema(db: Any) -> bool:
    """
    Crea/actualiza memory_nodes, memory_edges (con properties opcional) y property graph powerseal_crm.
    Retorna True si PGQ está disponible.
    """
    json_t = _json_sql_type(db)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS memory_nodes (
            node_id VARCHAR PRIMARY KEY,
            label VARCHAR,
            properties {json_t}
        )
    """)
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS memory_edges (
            edge_id VARCHAR PRIMARY KEY,
            source_id VARCHAR,
            target_id VARCHAR,
            relationship VARCHAR,
            weight DOUBLE DEFAULT 1.0,
            properties {json_t},
            FOREIGN KEY (source_id) REFERENCES memory_nodes(node_id),
            FOREIGN KEY (target_id) REFERENCES memory_nodes(node_id)
        )
    """)
    # Migración: añadir properties a memory_edges si no existe
    try:
        r = db.query(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name='memory_edges' AND column_name='properties' LIMIT 1"
        )
        rows = r if isinstance(r, list) else ([] if not r else [r])
        if not rows:
            db.execute(f"ALTER TABLE memory_edges ADD COLUMN properties {json_t}")
    except Exception:
        pass

    if not _crm_pgq_available(db):
        return False
    try:
        db.execute("DROP PROPERTY GRAPH IF EXISTS powerseal_crm")
        db.execute("""
            CREATE PROPERTY GRAPH powerseal_crm
            VERTEX TABLES (memory_nodes LABEL entity)
            EDGE TABLES (
                memory_edges SOURCE KEY (source_id) REFERENCES memory_nodes (node_id)
                             DESTINATION KEY (target_id) REFERENCES memory_nodes (node_id)
                             LABEL relation
            )
        """)
    except Exception:
        return False
    return True
