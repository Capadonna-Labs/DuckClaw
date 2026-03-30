"""Skill: explain_sql — EXPLAIN de consultas de lectura permitidas."""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from langchain_core.tools import StructuredTool


def _safe_ident(name: str) -> str:
    return "".join(c if c.isalnum() or c == "_" else "_" for c in (name or "").strip())


def _enforce_allowed_tables(q_upper: str, schema: str, allowed_tables: list[str]) -> Optional[str]:
    if not allowed_tables:
        return None
    if "INFORMATION_SCHEMA" in q_upper or "SHOW TABLES" in q_upper or q_upper.startswith("SHOW "):
        return None
    for t in allowed_tables:
        tu = t.upper()
        if tu in q_upper or f"{schema}.{t}".upper() in q_upper:
            return None
    if any(k in q_upper for k in ("FROM", "INTO", "UPDATE", "DELETE", "JOIN", "TABLE")):
        return json.dumps({"error": f"Solo se permiten las tablas: {', '.join(allowed_tables)}."}, ensure_ascii=False)
    return None


def _qualify_allowed_tables(query: str, schema_name: str, allowed_tables: list[str]) -> str:
    if not allowed_tables:
        return query
    out = query
    for table in allowed_tables:
        escaped = re.escape(table)
        out = re.sub(rf"(?<!\.)\b{escaped}\b", f"{schema_name}.{table}", out, flags=re.IGNORECASE)
    return out


def get_tools(db: Any, schema_name: str, spec: Any = None) -> list:
    schema = _safe_ident(schema_name)
    allowed = [_safe_ident(t) for t in (getattr(spec, "allowed_tables", None) or []) if t]

    def explain_sql(query: str) -> str:
        """Ejecuta EXPLAIN sobre una consulta SELECT/WITH (solo lectura) y devuelve el plan o error."""
        if not query or not query.strip():
            return json.dumps({"error": "Query vacío."}, ensure_ascii=False)
        q = query.strip()
        upper = q.upper()
        inner = q
        if upper.startswith("EXPLAIN"):
            inner = q[upper.index("EXPLAIN") + 7 :].strip()
            inner_upper = inner.upper()
        else:
            inner_upper = upper

        err = _enforce_allowed_tables(inner_upper, schema, allowed)
        if err:
            return err

        if not inner_upper.startswith(("SELECT", "WITH")):
            return json.dumps(
                {"error": "explain_sql solo acepta SELECT o WITH (y opcionalmente EXPLAIN ya incluido)."},
                ensure_ascii=False,
            )

        explain_stmt = inner if not upper.startswith("EXPLAIN") else q
        if not explain_stmt.upper().startswith("EXPLAIN"):
            explain_stmt = f"EXPLAIN {inner}"

        try:
            return db.query(explain_stmt)
        except Exception as e:
            if allowed and any(k in inner_upper for k in ("FROM", "JOIN")):
                for sch in ("main", "shared", "private", schema):
                    try_q = _qualify_allowed_tables(inner, sch, allowed)
                    if try_q == inner:
                        continue
                    alt = f"EXPLAIN {try_q}"
                    try:
                        return db.query(alt)
                    except Exception:
                        continue
            return json.dumps({"error": str(e)}, ensure_ascii=False)

    return [
        StructuredTool.from_function(
            explain_sql,
            name="explain_sql",
            description="Devuelve el plan EXPLAIN de una consulta SELECT/WITH sobre tablas permitidas; útil para explicar la lógica al usuario.",
        )
    ]
