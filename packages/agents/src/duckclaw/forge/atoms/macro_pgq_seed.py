"""Seed idempotente grafo macro MOC — specs/features/quant/QUANT_MOC_MACRO_PGQ_VSS.md."""

from __future__ import annotations

import json
from typing import Any

import duckdb

_REGIME_NODES: list[tuple[str, str, dict[str, Any]]] = [
    (
        "REGIMEN",
        "REGIMEN_HAWKISH",
        {"fed_stance": "hawkish", "yield_curve": "inverted", "growth": "contraction"},
    ),
    ("REGIMEN", "REGIMEN_DOVISH", {"fed_stance": "dovish", "yield_curve": "normal", "growth": "expansion"}),
    (
        "REGIMEN",
        "REGIMEN_STAGFLATION",
        {"inflation": "high", "growth": "contraction"},
    ),
    ("REGIMEN", "REGIMEN_RISK_OFF", {"vix_regime": "high", "risk": "flight_to_quality"}),
    ("REGIMEN", "REGIMEN_RISK_ON", {"vix_regime": "low", "momentum": "active"}),
    ("REGIMEN", "REGIMEN_NEUTRAL", {"vix_regime": "medium"}),
]

_ASSET_NODES: list[tuple[str, str, dict[str, Any]]] = [
    ("ACTIVO", "SPY", {"sector": "equities"}),
    ("ACTIVO", "META", {"sector": "tech"}),
    ("ACTIVO", "GLD", {"sector": "commodities"}),
    ("ACTIVO", "TLT", {"sector": "bonds", "duration": "long"}),
    ("ACTIVO", "SHY", {"sector": "bonds", "duration": "short"}),
    ("ACTIVO", "IEF", {"sector": "bonds", "duration": "medium"}),
    ("ACTIVO", "XLU", {"sector": "utilities"}),
    ("ACTIVO", "QCOM", {"sector": "tech"}),
]

# (src_asset, dst_regime, edge_type, weight, evidence)
_EDGE_SEEDS: list[tuple[str, str, str, float, str]] = [
    ("SHY", "REGIMEN_RISK_OFF", "REFUGIO_DURANTE", 0.9, "Refugio en duration corta ante risk-off"),
    ("GLD", "REGIMEN_STAGFLATION", "REFUGIO_DURANTE", 0.85, "Commodity refugio en stagflation"),
    ("TLT", "REGIMEN_HAWKISH", "PRESIONADO_POR", 0.8, "Duration largo bajo ciclo hawkish"),
    ("META", "REGIMEN_RISK_OFF", "CONTRAINDICADO_EN", 0.7, "Growth tech presionado en risk-off fuerte"),
    ("XLU", "REGIMEN_RISK_OFF", "BENEFICIADO_POR", 0.75, "Defensivos en flight to quality"),
    ("SPY", "REGIMEN_RISK_ON", "CORRELACIONADO_EN", 0.6, "Equity broad en risk-on"),
]


def _node_id(con: duckdb.DuckDBPyConnection, name: str) -> str | None:
    row = con.execute(
        "SELECT CAST(id AS VARCHAR) FROM quant_core.macro_nodes WHERE name = ? LIMIT 1",
        [name],
    ).fetchone()
    if not row:
        return None
    return str(row[0])


def ensure_macro_pgq_seed(con: duckdb.DuckDBPyConnection) -> None:
    """Crea nodos/aristas macro si no existen (todas las bóvedas bootstrap)."""
    con.execute("CREATE SCHEMA IF NOT EXISTS quant_core;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS quant_core.macro_nodes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            node_type VARCHAR(50) NOT NULL,
            name VARCHAR(100) NOT NULL UNIQUE,
            properties JSON,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS quant_core.macro_edges (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            src_node_id UUID REFERENCES quant_core.macro_nodes(id),
            dst_node_id UUID REFERENCES quant_core.macro_nodes(id),
            edge_type VARCHAR(60) NOT NULL,
            weight DECIMAL(8,4),
            valid_from TIMESTAMP,
            valid_until TIMESTAMP,
            evidence TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    try:
        con.execute("CREATE INDEX IF NOT EXISTS idx_macro_edges_src ON quant_core.macro_edges(src_node_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_macro_edges_dst ON quant_core.macro_edges(dst_node_id);")
        con.execute("CREATE INDEX IF NOT EXISTS idx_macro_edges_type ON quant_core.macro_edges(edge_type);")
    except Exception:
        pass
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS quant_core.macro_manual_state (
            id VARCHAR PRIMARY KEY,
            regime_override VARCHAR,
            confidence DOUBLE,
            evidence TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """
    )

    for ntype, name, props in _REGIME_NODES + _ASSET_NODES:
        pj = json.dumps(props, ensure_ascii=False)
        con.execute(
            """
            INSERT INTO quant_core.macro_nodes (node_type, name, properties)
            SELECT ?, ?, CAST(? AS JSON)
            WHERE NOT EXISTS (SELECT 1 FROM quant_core.macro_nodes mn WHERE mn.name = ?)
            """,
            [ntype, name, pj, name],
        )

    for src_n, dst_n, etype, weight, evid in _EDGE_SEEDS:
        sid = _node_id(con, src_n)
        did = _node_id(con, dst_n)
        if not sid or not did:
            continue
        con.execute(
            """
            INSERT INTO quant_core.macro_edges (src_node_id, dst_node_id, edge_type, weight, evidence)
            SELECT ?::UUID, ?::UUID, ?, ?, ?
            WHERE NOT EXISTS (
              SELECT 1 FROM quant_core.macro_edges e
              WHERE e.src_node_id = ?::UUID AND e.dst_node_id = ?::UUID AND e.edge_type = ?
            )
            """,
            [sid, did, etype, weight, evid, sid, did, etype],
        )
