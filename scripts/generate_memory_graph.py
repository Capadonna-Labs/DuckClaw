#!/usr/bin/env python3
"""Export DuckDB memory_nodes/memory_edges to standalone PyVis HTML."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

import duckdb

GROUP_COLORS: dict[str, str] = {
    "USER": "#38bdf8",
    "MERCHANT": "#a78bfa",
    "CATEGORY": "#f472b6",
    "PREFERENCE": "#34d399",
    "PLACE": "#fbbf24",
    "PRODUCT": "#fb923c",
    "REGIMEN": "#f87171",
    "SECTOR": "#4ade80",
    "ASSET_CLASS": "#60a5fa",
    "TICKER": "#fbbf24",
    "MACRO_DRIVER": "#c084fc",
}

VIS_OPTIONS: dict[str, Any] = {
    "nodes": {
        "shape": "dot",
        "scaling": {"min": 10, "max": 46, "label": {"min": 11, "max": 22, "drawThreshold": 1}},
        "borderWidth": 2,
        "shadow": {"enabled": True, "size": 12, "color": "rgba(0,0,0,0.45)"},
        "font": {"color": "#e2e8f0", "size": 14, "face": "Inter, system-ui, sans-serif", "strokeWidth": 3, "strokeColor": "#0f172a"},
    },
    "edges": {
        "color": {"color": "rgba(148,163,184,0.35)", "highlight": "#38bdf8", "hover": "#7dd3fc"},
        "width": 1,
        "selectionWidth": 2.5,
        "smooth": {"type": "continuous", "roundness": 0.25},
        "arrows": {"to": {"enabled": True, "scaleFactor": 0.5}},
        "font": {"color": "#94a3b8", "size": 10, "strokeWidth": 3, "strokeColor": "#0f172a", "align": "middle"},
    },
    "physics": {
        "solver": "forceAtlas2Based",
        "forceAtlas2Based": {"gravitationalConstant": -62, "centralGravity": 0.008, "springLength": 130, "springConstant": 0.07, "damping": 0.5, "avoidOverlap": 0.4},
        "stabilization": {"enabled": True, "iterations": 320, "fit": True},
        "minVelocity": 0.6,
    },
    "interaction": {
        "hover": True,
        "hoverConnectedEdges": True,
        "tooltipDelay": 120,
        "navigationButtons": True,
        "keyboard": {"enabled": True},
        "multiselect": True,
    },
}


def _table_exists(con: Any, name: str) -> bool:
    row = con.execute(
        """
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = 'main' AND table_name = ?
        LIMIT 1
        """,
        [name],
    ).fetchone()
    return row is not None


def fetch_graph_rows(
    con: Any,
    *,
    max_nodes: int = 500,
    max_edges: int = 2000,
) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    import sys
    from pathlib import Path

    gw = Path(__file__).resolve().parents[1] / "services" / "api-gateway"
    if str(gw) not in sys.path:
        sys.path.insert(0, str(gw))
    from core.pgq_graph_fetch import fetch_pgq_graph_data

    payload = fetch_pgq_graph_data(con, max_nodes=max_nodes, max_edges=max_edges)
    nodes = payload.get("nodes") or []
    edges = [
        {"source": l["source"], "target": l["target"], "label": l.get("label", "")}
        for l in (payload.get("links") or [])
    ]
    return nodes, edges


def build_memory_graph_html(
    con: Any,
    out_path: Path,
    *,
    max_nodes: int = 500,
    max_edges: int = 2000,
) -> dict[str, int]:
    from pyvis.network import Network

    nodes, edges = fetch_graph_rows(con, max_nodes=max_nodes, max_edges=max_edges)
    net = Network(
        height="100vh",
        width="100%",
        bgcolor="#0f172a",
        font_color="#e2e8f0",
        directed=True,
        cdn_resources="remote",
    )
    net.set_options(json.dumps(VIS_OPTIONS))

    degree: dict[str, int] = {}
    for edge in edges:
        degree[edge["source"]] = degree.get(edge["source"], 0) + 1
        degree[edge["target"]] = degree.get(edge["target"], 0) + 1

    for node in nodes:
        color = GROUP_COLORS.get(node["group"], "#64748b")
        deg = degree.get(node["id"], 0)
        net.add_node(
            node["id"],
            label=node["label"],
            group=node["group"],
            title=f"{node['label']}\n{node['group']} · {deg} conexiones",
            color=color,
            value=deg + 1,
        )

    for edge in edges:
        net.add_edge(
            edge["source"],
            edge["target"],
            label=edge["label"],
            title=edge["label"],
        )

    out_path.parent.mkdir(parents=True, exist_ok=True)
    net.write_html(str(out_path), open_browser=False, notebook=False)
    return {"nodes": len(nodes), "edges": len(edges)}


def _self_check() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        db_path = Path(tmp) / "fixture.duckdb"
        out_path = Path(tmp) / "memory_graph.html"
        con = duckdb.connect(str(db_path))
        try:
            con.execute(
                """
                CREATE TABLE memory_nodes (
                    node_id VARCHAR PRIMARY KEY,
                    label VARCHAR,
                    properties JSON
                )
                """
            )
            con.execute(
                """
                CREATE TABLE memory_edges (
                    edge_id VARCHAR PRIMARY KEY,
                    source_id VARCHAR,
                    target_id VARCHAR,
                    relationship VARCHAR,
                    weight DOUBLE DEFAULT 1.0
                )
                """
            )
            con.execute(
                """
                INSERT INTO memory_nodes VALUES
                ('USER:alice', 'USER', '{"name": "alice"}'),
                ('MERCHANT:shop', 'MERCHANT', '{"name": "shop"}')
                """
            )
            con.execute(
                """
                INSERT INTO memory_edges VALUES
                ('e1', 'USER:alice', 'MERCHANT:shop', 'SPENDS_ON', 1.0)
                """
            )
            stats = build_memory_graph_html(con, out_path)
        finally:
            con.close()

        assert stats["nodes"] == 2, stats
        assert stats["edges"] == 1, stats
        html = out_path.read_text(encoding="utf-8")
        assert len(html) > 200, "HTML export vacío"
        assert "alice" in html.lower() or "USER:alice" in html


def main() -> int:
    parser = argparse.ArgumentParser(description="Export PGQ memory graph to PyVis HTML")
    parser.add_argument("--vault-path", help="Path to .duckdb vault")
    parser.add_argument("--out", help="Output HTML path")
    parser.add_argument("--max-nodes", type=int, default=500)
    parser.add_argument("--max-edges", type=int, default=2000)
    parser.add_argument("--self-check", action="store_true", help="Run fixture self-check")
    args = parser.parse_args()

    if args.self_check:
        _self_check()
        print(json.dumps({"ok": True}))
        return 0

    if not args.vault_path or not args.out:
        parser.error("--vault-path and --out are required unless --self-check")

    con = duckdb.connect(args.vault_path, read_only=True)
    try:
        stats = build_memory_graph_html(
            con,
            Path(args.out),
            max_nodes=args.max_nodes,
            max_edges=args.max_edges,
        )
    finally:
        con.close()

    print(json.dumps({"ok": True, **stats}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
