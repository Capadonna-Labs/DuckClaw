"""Skill: get_schema_info — DDL / columnas del esquema del worker (analytics_core)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool


def _safe_ident(name: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in (name or "").strip())


def get_tools(db: Any, schema_name: str, spec: Any = None) -> list:
    schema = _safe_ident(schema_name)
    allowed = [_safe_ident(t) for t in (getattr(spec, "allowed_tables", None) or []) if t]

    def get_schema_info() -> str:
        """Devuelve definición estructurada (estilo DDL) solo para el esquema y tablas permitidas del worker."""
        try:
            if not allowed:
                return json.dumps(
                    {"schema": schema, "tables": [], "note": "Sin allowed_tables en manifiesto."},
                    ensure_ascii=False,
                )
            in_clause = ", ".join(f"'{t}'" for t in allowed)
            sql = (
                "SELECT table_schema, table_name, column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                f"WHERE table_schema = '{schema}' AND table_name IN ({in_clause}) "
                "ORDER BY table_name, ordinal_position"
            )
            raw = db.query(sql)
            rows = json.loads(raw) if isinstance(raw, str) else []
            if not isinstance(rows, list):
                return raw if isinstance(raw, str) else json.dumps({"error": "Respuesta inesperada de information_schema."})

            by_table: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                tbl = row.get("table_name") or ""
                by_table.setdefault(tbl, []).append(row)

            ddl_parts: list[str] = []
            for tbl in sorted(by_table.keys()):
                cols = by_table[tbl]
                col_defs = []
                for c in cols:
                    cn = c.get("column_name", "")
                    dt = c.get("data_type", "")
                    nullable = str(c.get("is_nullable") or "YES").upper() == "YES"
                    null_sql = "" if nullable else " NOT NULL"
                    col_defs.append(f"  {cn} {dt}{null_sql}")
                ddl_parts.append(f"CREATE TABLE {schema}.{tbl} (\n" + ",\n".join(col_defs) + "\n);")

            return json.dumps(
                {
                    "schema": schema,
                    "ddl": "\n\n".join(ddl_parts),
                    "columns": rows,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    return [
        StructuredTool.from_function(
            get_schema_info,
            name="get_schema_info",
            description="Obligatorio al inicio de análisis: devuelve columnas y DDL del esquema analytics_core (solo tablas permitidas).",
        )
    ]
