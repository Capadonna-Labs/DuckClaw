"""Manifest ``allowed_tables`` enforcement for worker SQL tools (read_sql / admin_sql).

Every table the statement references must be allowed. The previous check passed
as soon as *any* allowed name appeared anywhere in the text, so e.g.
``CREATE TABLE x AS SELECT * FROM quant_core.ohlcv_data`` slipped through, and
mentioning ``information_schema`` in a comment disabled the check entirely.

ponytail: lightweight tokenizer, not a SQL parser — covers FROM (incl. comma
lists), JOIN, INTO, UPDATE, TABLE/VIEW DDL, COPY, DESCRIBE/SUMMARIZE, CTE names
and table functions. Swap for ``sqlglot`` if statements outgrow it.
"""

from __future__ import annotations

import json
import re
from typing import Any, Iterable, Optional

_STRIP_RE = re.compile(r"'(?:[^']|'')*'|--[^\n]*|/\*.*?\*/", re.DOTALL)
_TOKEN_RE = re.compile(r'"[^"]*"|[A-Za-z_][A-Za-z0-9_$]*|[.,();]|\S')
# Keyword -> next identifier is a table reference.
_REF_KEYWORDS = {"FROM", "JOIN", "INTO", "UPDATE", "TABLE", "VIEW", "COPY", "DESCRIBE", "SUMMARIZE", "USING"}
_SKIP_AFTER_KEYWORD = {"IF", "NOT", "EXISTS", "ONLY", "OR", "REPLACE", "TEMP", "TEMPORARY", "LATERAL"}
# "DO UPDATE SET", "JOIN ... USING (col)" etc.: the next word is syntax, not a table.
_NOT_A_TABLE = {"SELECT", "WITH", "TABLE", "VALUES", "SET"}
_FROM_CLAUSE_END = {
    "WHERE", "GROUP", "ORDER", "LIMIT", "OFFSET", "HAVING", "UNION", "EXCEPT", "INTERSECT",
    "JOIN", "LEFT", "RIGHT", "INNER", "FULL", "CROSS", "NATURAL", "POSITIONAL", "ASOF", "ANTI",
    "SEMI", "ON", "USING", "QUALIFY", "WINDOW", "SET", "RETURNING", "SELECT",
}
# FROM inside these calls is syntax, not a table (EXTRACT(YEAR FROM ts), TRIM(x FROM y)).
_FROM_FUNCTIONS = {"EXTRACT", "TRIM", "SUBSTRING", "POSITION", "OVERLAY"}
_SYSTEM_SCHEMAS = {"information_schema", "pg_catalog"}


def _is_ident(tok: str) -> bool:
    return bool(tok) and (tok[0] == '"' or tok[0].isalpha() or tok[0] == "_")


def _norm(tok: str) -> str:
    return tok.strip('"').lower()


def _read_qualified(toks: list[str], j: int) -> tuple[str, int]:
    parts = [_norm(toks[j])]
    j += 1
    while j + 1 < len(toks) and toks[j] == "." and _is_ident(toks[j + 1]):
        parts.append(_norm(toks[j + 1]))
        j += 2
    return ".".join(parts), j


def referenced_tables(sql: str) -> set[str]:
    """Lower-cased table names (possibly schema-qualified) the statement touches."""
    toks = _TOKEN_RE.findall(_STRIP_RE.sub("''", sql or ""))
    n = len(toks)
    upper = [t.upper() for t in toks]
    ctes = {
        _norm(toks[i - 1])
        for i in range(2, n - 1)
        if upper[i] == "AS" and toks[i + 1] == "(" and _is_ident(toks[i - 1])
        and upper[i - 2] in ("WITH", "RECURSIVE", ",")
    }
    refs: set[str] = set()
    paren_owner: list[str] = []  # token before each open "(" (detects EXTRACT(... FROM ...))
    for i, tok in enumerate(toks):
        if tok == "(":
            paren_owner.append(upper[i - 1] if i else "")
            continue
        if tok == ")":
            if paren_owner:
                paren_owner.pop()
            continue
        kw = upper[i]
        if kw not in _REF_KEYWORDS:
            continue
        if kw == "FROM" and paren_owner and paren_owner[-1] in _FROM_FUNCTIONS:
            continue
        j = i + 1
        while j < n and upper[j] in _SKIP_AFTER_KEYWORD:
            j += 1
        while j < n and _is_ident(toks[j]) and upper[j] not in _NOT_A_TABLE:
            name, j = _read_qualified(toks, j)
            if kw in ("FROM", "JOIN") and j < n and toks[j] == "(":
                break  # table function: read_csv(...), range(...)
            refs.add(name)
            if kw != "FROM":
                break
            # FROM a [alias], b [alias] ...: skip to the next top-level comma.
            depth = 0
            while j < n:
                t, u = toks[j], upper[j]
                if t == "(":
                    depth += 1
                elif t == ")":
                    if depth == 0:
                        break
                    depth -= 1
                elif depth == 0 and (t in (",", ";") or u in _FROM_CLAUSE_END):
                    break
                j += 1
            if j < n and toks[j] == ",":
                j += 1
                continue
            break
    return {r for r in refs if r not in ctes}


def disallowed_tables(sql: str, allowed: Iterable[Any], schema: str | None) -> list[str]:
    """References not covered by ``allowed`` (entries bare or schema-qualified)."""
    allow = {str(a).strip().lower() for a in allowed if str(a).strip()}
    sch = (schema or "").strip().lower()
    bad: list[str] = []
    for ref in sorted(referenced_tables(sql)):
        parts = ref.split(".")
        name = parts[-1]
        qualifier = parts[-2] if len(parts) > 1 else ""
        if qualifier in _SYSTEM_SCHEMAS or name.startswith("duckdb_"):
            continue
        tail = f"{qualifier}.{name}" if qualifier else name
        if tail in allow:
            continue
        if not qualifier and sch and f"{sch}.{name}" in allow:
            continue
        if name in allow and qualifier in ("", sch, "main"):
            continue
        bad.append(ref)
    return bad


def allowed_tables_error(allowed: Iterable[Any] | None, schema: str | None, sql: str) -> Optional[str]:
    """JSON error body when the statement touches a table outside the manifest, else None."""
    allowed_list = [str(a) for a in (allowed or [])]
    if not allowed_list:
        return None
    bad = disallowed_tables(sql, allowed_list, schema)
    if not bad:
        return None
    return json.dumps(
        {
            "error": (
                f"Solo se permiten las tablas: {', '.join(allowed_list)}. "
                f"No permitidas en esta consulta: {', '.join(bad)}."
            )
        }
    )
