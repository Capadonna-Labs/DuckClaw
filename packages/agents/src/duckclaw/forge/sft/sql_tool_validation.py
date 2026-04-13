"""
Extracción y validación de SQL en tool_calls (OpenAI) y completions legacy (<tool_call> XML).

Usado por el collector SFT y Model-Guard sin depender de duckclaw.rl.
"""

from __future__ import annotations

import json
from typing import Any, Iterator


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw) if raw.strip() else {}
        except json.JSONDecodeError:
            return {}
    return {}


def iter_sql_strings_from_openai_messages(messages: list[dict[str, Any]]) -> Iterator[str]:
    """Recorre tool_calls en mensajes assistant y emite valores de la clave sql en arguments."""
    for m in messages:
        if not isinstance(m, dict):
            continue
        if (m.get("role") or "").lower() != "assistant":
            continue
        tcs = m.get("tool_calls")
        if not isinstance(tcs, list):
            continue
        for tc in tcs:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function")
            if not isinstance(fn, dict):
                continue
            args = _parse_arguments(fn.get("arguments"))
            sql = args.get("sql")
            if isinstance(sql, str) and sql.strip():
                yield sql.strip()


def validate_sql_strings(sql_strings: list[str]) -> bool:
    """True si la lista está vacía o todo el SQL parsea con sqlglot (duckdb)."""
    if not sql_strings:
        return True
    try:
        import sqlglot
    except ImportError:
        return True
    for sql in sql_strings:
        try:
            sqlglot.parse(sql, dialect="duckdb")
        except Exception:
            return False
    return True


def validate_sql_in_openai_messages(messages: list[dict[str, Any]]) -> bool:
    return validate_sql_strings(list(iter_sql_strings_from_openai_messages(messages)))


def parse_legacy_tool_calls_from_completion(completion: str) -> list[dict[str, Any]]:
    """
    Extrae objetos JSON internos en <tool_call>...</tool_call> (formato BI / traces legacy).
    Cada objeto esperado: {\"tool\": str, \"args\": {...}}.
    """
    out: list[dict[str, Any]] = []
    if not completion or not isinstance(completion, str):
        return out
    start_tag, end_tag = "<tool_call>", "</tool_call>"
    idx = 0
    while True:
        start = completion.find(start_tag, idx)
        if start < 0:
            break
        end = completion.find(end_tag, start + len(start_tag))
        if end < 0:
            break
        inner = completion[start + len(start_tag) : end].strip()
        idx = end + len(end_tag)
        try:
            obj = json.loads(inner)
        except json.JSONDecodeError:
            continue
        if not isinstance(obj, dict):
            continue
        tool = obj.get("tool")
        args = obj.get("args")
        if isinstance(args, dict):
            out.append({"tool": tool, "args": args})
    return out


def validate_sql_in_completion(completion: str) -> bool:
    """Valida SQL dentro de args en tool_calls legacy del completion."""
    try:
        import sqlglot
    except ImportError:
        return True
    for tc in parse_legacy_tool_calls_from_completion(completion):
        args = tc.get("args") or {}
        if not isinstance(args, dict):
            continue
        sql = args.get("sql")
        if not sql or not isinstance(sql, str):
            continue
        sql = sql.strip()
        if not sql:
            continue
        try:
            sqlglot.parse(sql, dialect="duckdb")
        except Exception:
            return False
    return True
