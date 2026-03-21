"""Partir scripts SQL en sentencias respetando comillas (no cortar `;` dentro de strings)."""

from __future__ import annotations


def split_sql_statements(sql: str) -> list[str]:
    """Divide SQL por `;` fuera de strings (' y \")."""
    out: list[str] = []
    buf: list[str] = []
    in_str: str | None = None
    i = 0
    while i < len(sql):
        c = sql[i]
        if in_str:
            if c == "\\" and i + 1 < len(sql):
                buf.append(sql[i : i + 2])
                i += 2
                continue
            if c == in_str:
                in_str = None
            buf.append(c)
            i += 1
            continue
        if c in ("'", '"'):
            in_str = c
            buf.append(c)
            i += 1
            continue
        if c == ";":
            out.append("".join(buf).strip())
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    if buf:
        out.append("".join(buf).strip())
    return out
