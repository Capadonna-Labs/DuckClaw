"""
Ephemeral read-only DuckDB connections for parallel worker tool execution.

Spec: docs/architecture/system_overview.md
"""

from __future__ import annotations

import json
import logging
import os
import random
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional

from duckclaw.workers.manifest import WorkerSpec
from duckclaw.workers.runtime_policy_helpers import (
    worker_has_runtime_capability as _worker_has_runtime_capability,
    worker_runtime_capability_policy as _worker_runtime_capability_policy,
)

_log = logging.getLogger(__name__)

_READ_SQL_MAX_RESPONSE_CHARS = max(8_000, int(os.environ.get("DUCKCLAW_READ_SQL_MAX_RESPONSE_CHARS", "80000")))

DEFAULT_EPHEMERAL_TOOLS = frozenset({"read_sql", "inspect_schema"})

_sem: Optional[threading.BoundedSemaphore] = None
_sem_lock = threading.Lock()


def _row_amount(row: dict[str, str], amount_field: str) -> float:
    try:
        return float(row.get(amount_field) or 0)
    except (TypeError, ValueError):
        return 0.0


def _child_row_ids_to_exclude(
    rows: list[dict[str, str]],
    *,
    amount_field: str,
    group_field: str,
    description_field: str,
    id_field: str,
    child_row_pattern: re.Pattern[str] | None,
    aggregate_markers: tuple[str, ...],
) -> set[str]:
    """
    When aggregate and child rows coexist for the same group key, exclude child rows from totals.
    Patterns come from the worker ``read_summary_dedup`` runtime policy.
    """
    groups: dict[str, dict] = {}
    for r in rows:
        if _row_amount(r, amount_field) <= 0:
            continue
        key = (r.get(group_field) or "").strip()
        desc = (r.get(description_field) or "").strip()
        if not key or not desc:
            continue
        if key not in groups:
            groups[key] = {"child_ids": [], "has_aggregate": False}
        if child_row_pattern and child_row_pattern.match(desc):
            groups[key]["child_ids"].append(str(r.get(id_field, "")))
        else:
            dlow = desc.lower()
            if aggregate_markers and any(marker in dlow for marker in aggregate_markers):
                groups[key]["has_aggregate"] = True
    excluded: set[str] = set()
    for info in groups.values():
        if info["has_aggregate"] and len(info["child_ids"]) >= 2:
            excluded.update(i for i in info["child_ids"] if i)
    return excluded


def _read_summary_dedup_policy(spec: WorkerSpec) -> dict[str, Any] | None:
    policy = _worker_runtime_capability_policy(spec, "read_summary_dedup")
    if not policy:
        return None
    table_name = str(policy.get("table_name") or "").strip().lower()
    amount_field = str(policy.get("amount_field") or "").strip()
    group_field = str(policy.get("group_field") or policy.get("creditor_field") or "").strip()
    description_field = str(policy.get("description_field") or "").strip()
    id_field = str(policy.get("id_field") or "").strip()
    if not all((table_name, amount_field, group_field, description_field, id_field)):
        return None
    child_pattern_raw = str(policy.get("child_row_pattern") or "").strip()
    child_pattern = re.compile(child_pattern_raw, re.IGNORECASE) if child_pattern_raw else None
    aggregate_markers_raw = policy.get("aggregate_markers")
    if isinstance(aggregate_markers_raw, str):
        aggregate_markers = tuple(m.strip().lower() for m in aggregate_markers_raw.split(",") if m.strip())
    elif isinstance(aggregate_markers_raw, (list, tuple)):
        aggregate_markers = tuple(str(m).strip().lower() for m in aggregate_markers_raw if str(m).strip())
    else:
        aggregate_markers = ()
    schema_name = str(policy.get("schema_name") or "").strip().lower()
    return {
        "table_name": table_name,
        "schema_name": schema_name,
        "amount_field": amount_field,
        "group_field": group_field,
        "description_field": description_field,
        "id_field": id_field,
        "child_row_pattern": child_pattern,
        "aggregate_markers": aggregate_markers,
    }


def _maybe_wrap_summary_dedup_read_sql(spec: WorkerSpec, query: str, raw: str) -> str:
    """Anexa totales deduplicados cuando una capability DB define reglas de resumen."""
    policy = _read_summary_dedup_policy(spec)
    if not policy:
        return raw
    table_name = policy["table_name"]
    qlow = query.lower()
    if table_name not in qlow:
        return raw
    schema_name = policy["schema_name"]
    sch = (getattr(spec, "schema_name", None) or "").strip().lower()
    if schema_name and schema_name not in qlow and sch != schema_name:
        return raw
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(parsed, dict):
        return raw
    if not isinstance(parsed, list) or not parsed:
        return raw
    exclude = _child_row_ids_to_exclude(
        parsed,
        amount_field=policy["amount_field"],
        group_field=policy["group_field"],
        description_field=policy["description_field"],
        id_field=policy["id_field"],
        child_row_pattern=policy["child_row_pattern"],
        aggregate_markers=policy["aggregate_markers"],
    )
    if not exclude:
        return raw
    amount_field = policy["amount_field"]
    id_field = policy["id_field"]
    naive = sum(_row_amount(r, amount_field) for r in parsed if _row_amount(r, amount_field) > 0)
    deduped = sum(
        _row_amount(r, amount_field)
        for r in parsed
        if _row_amount(r, amount_field) > 0 and str(r.get(id_field, "")) not in exclude
    )
    meta = {
        "sum_all_rows": naive,
        "recommended_total": deduped,
        "rule_applied": (
            "Excluded child rows that duplicate an aggregate row in the same group; "
            "do not sum both in a single total."
        ),
        "excluded_ids": sorted(exclude),
    }
    return json.dumps({"rows": parsed, "_summary_totals": meta}, ensure_ascii=False)


def _truncate_read_sql_result_for_llm(raw: str) -> str:
    if not isinstance(raw, str) or len(raw) <= _READ_SQL_MAX_RESPONSE_CHARS:
        return raw
    return json.dumps(
        {
            "warning": (
                "Salida truncada por límite de tamaño del gateway. Para JSON remotos usa LIMIT, "
                "menos columnas, o run_sandbox para aplanar/resumir el archivo completo."
            ),
            "preview": raw[:_READ_SQL_MAX_RESPONSE_CHARS],
            "total_chars": len(raw),
            "omitted_chars": len(raw) - _READ_SQL_MAX_RESPONSE_CHARS,
        },
        ensure_ascii=False,
    )


def _escape_attach_path(path: str) -> str:
    return str(path).replace("'", "''")


def build_attach_statements(primary_path: str, private_path: str, shared_path: Optional[str]) -> list[str]:
    """ATTACH como _apply_forge_attaches (sin DETACH) para conexión nueva."""
    stmts: list[str] = []
    esc_p = _escape_attach_path(private_path)
    stmts.append(f"ATTACH '{esc_p}' AS private")
    sp = (shared_path or "").strip()
    if not sp:
        return stmts
    try:
        if Path(sp).resolve() == Path(primary_path).resolve():
            return stmts
    except Exception:
        if os.path.abspath(sp) == os.path.abspath(primary_path):
            return stmts
    esc_s = _escape_attach_path(sp)
    stmts.append(f"ATTACH '{esc_s}' AS shared")
    return stmts


def _load_extensions_readonly(conn: Any, extensions: list[str]) -> None:
    for raw in extensions:
        ext = str(raw).strip().lower()
        if not ext or not re.match(r"^[a-z][a-z0-9_]*$", ext):
            continue
        try:
            conn.execute(f"LOAD {ext};")
        except Exception:
            pass


def connection_query_json(conn: Any, sql: str) -> str:
    """Ejecuta SQL y devuelve JSON al estilo DuckClaw (valores como string)."""
    result = conn.execute(sql)
    if result.description is None:
        return "[]"
    cols = [d[0] for d in result.description]
    rows = result.fetchall()
    out: list[dict[str, str]] = []
    for row in rows:
        out.append({cols[i]: str(row[i]) for i in range(len(cols))})
    return json.dumps(out, ensure_ascii=False)


def _enforce_allowed_tables_error(spec: WorkerSpec, q_upper: str) -> Optional[str]:
    schema = spec.schema_name
    allowed = spec.allowed_tables or []
    if not allowed:
        return None
    if "INFORMATION_SCHEMA" in q_upper or "SHOW TABLES" in q_upper or "SHOW " in q_upper:
        return None
    for t in allowed:
        ts = str(t)
        if ts.upper() in q_upper or f"{schema}.{ts}".upper() in q_upper:
            return None
    if any(k in q_upper for k in ("FROM", "INTO", "UPDATE", "DELETE", "JOIN", "TABLE")):
        return json.dumps({"error": f"Solo se permiten las tablas: {', '.join(allowed)}."})
    return None


def _qualify_allowed_tables(query: str, schema_name: str, spec: WorkerSpec) -> str:
    allowed = spec.allowed_tables or []
    if not allowed:
        return query
    out = query
    for table in allowed:
        if "." in str(table):
            continue
        escaped = re.escape(table)
        out = re.sub(rf"(?<!\.)\b{escaped}\b", f"{schema_name}.{table}", out, flags=re.IGNORECASE)
    return out


_BINDER_COLUMN_RE = re.compile(
    r"""(?:Referenced column|Binder Error:?\s*column)\s+[\"']?([A-Za-z_][\w]*)[\"']?""",
    re.IGNORECASE,
)
_BINDER_TABLE_RE = re.compile(
    r"""(?:table|relation)\s+[\"']?((?:[A-Za-z_][\w]*\.)?[A-Za-z_][\w]*)[\"']?""",
    re.IGNORECASE,
)
_FROM_JOIN_TABLE_RE = re.compile(
    r"""(?:FROM|JOIN)\s+([A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)?)""",
    re.IGNORECASE,
)


def _is_binder_column_error(err: str) -> bool:
    low = (err or "").lower()
    return "binder" in low or "referenced column" in low or "column" in low and "not found" in low


def _parse_binder_column_name(err: str) -> Optional[str]:
    m = _BINDER_COLUMN_RE.search(err or "")
    if m:
        return m.group(1)
    m2 = re.search(r"""[\"']([A-Za-z_][\w]*)[\"']\s+not found""", err or "", re.IGNORECASE)
    return m2.group(1) if m2 else None


def _tables_mentioned_in_query(query: str, spec: WorkerSpec) -> list[str]:
    found: list[str] = []
    for m in _FROM_JOIN_TABLE_RE.finditer(query or ""):
        name = (m.group(1) or "").strip()
        if name and name.lower() not in {t.lower() for t in found}:
            found.append(name)
    for t in spec.allowed_tables or []:
        ts = str(t).strip()
        if ts and ts.lower() not in {x.lower() for x in found}:
            found.append(ts)
    return found


def _edit_distance(a: str, b: str) -> int:
    a, b = a.lower(), b.lower()
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (0 if ca == cb else 1)))
        prev = cur
    return prev[-1]


def _rank_column_candidates(wrong: str, columns: list[str], *, limit: int = 8) -> list[str]:
    if not wrong or not columns:
        return columns[:limit]
    scored = sorted(
        (( _edit_distance(wrong, c), c.lower().startswith(wrong.lower()[:3]), c) for c in columns),
        key=lambda t: (t[0], 0 if t[1] else 1, t[2].lower()),
    )
    out: list[str] = []
    for _, _, c in scored:
        if c not in out:
            out.append(c)
        if len(out) >= limit:
            break
    return out


def _fetch_columns_for_table(run_query: Callable[[str], str], table_ref: str) -> list[str]:
    """Best-effort column list for schema.table or bare table via information_schema."""
    raw = (table_ref or "").strip()
    if not raw or not re.match(r"^[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)?$", raw):
        return []
    if "." in raw:
        schema, table = raw.split(".", 1)
        sql = (
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_schema = '{schema.replace(chr(39), chr(39)+chr(39))}' "
            f"AND table_name = '{table.replace(chr(39), chr(39)+chr(39))}' "
            "ORDER BY ordinal_position"
        )
    else:
        sql = (
            "SELECT column_name FROM information_schema.columns "
            f"WHERE table_name = '{raw.replace(chr(39), chr(39)+chr(39))}' "
            "AND table_schema NOT IN ('information_schema','pg_catalog') "
            "ORDER BY table_schema, ordinal_position"
        )
    try:
        parsed = json.loads(run_query(sql))
    except Exception:
        return []
    if not isinstance(parsed, list):
        return []
    cols: list[str] = []
    for row in parsed:
        if isinstance(row, dict):
            name = str(row.get("column_name") or "").strip()
            if name and name not in cols:
                cols.append(name)
    return cols


def _resolve_binder_column_context(
    run_query: Callable[[str], str],
    spec: WorkerSpec,
    query: str,
    err: str,
) -> tuple[Optional[str], Optional[str], list[str]]:
    """Return (wrong_column, resolved_table, ranked_candidates)."""
    wrong = _parse_binder_column_name(err)
    table_hint: Optional[str] = None
    tm = _BINDER_TABLE_RE.search(err or "")
    if tm:
        table_hint = tm.group(1)
    tables: list[str] = []
    if table_hint:
        tables.append(table_hint)
    tables.extend(_tables_mentioned_in_query(query, spec))
    all_cols: list[str] = []
    resolved_table: Optional[str] = None
    for tref in tables:
        cols = _fetch_columns_for_table(run_query, tref)
        if cols:
            resolved_table = tref
            all_cols = cols
            break
    if not all_cols and (spec.allowed_tables or []):
        for tref in spec.allowed_tables:
            cols = _fetch_columns_for_table(run_query, str(tref))
            if cols:
                resolved_table = str(tref)
                all_cols = cols
                break
    candidates = _rank_column_candidates(wrong or "", all_cols) if all_cols else []
    return wrong, resolved_table, candidates


# Soft alias hints — only applied when the target column exists on the resolved table.
_COMMON_COLUMN_ALIASES: dict[str, tuple[str, ...]] = {
    "qty": ("quantity", "qty"),
    "quantity": ("qty", "quantity"),
    "fill_price": ("filled_price",),
    "filled_price": ("fill_price",),
    "last_close": ("close",),
    "proposed_qty": ("proposed_weight", "quantity", "qty"),
    "position_qty": ("qty", "quantity"),
    "tickers": ("ticker", "symbol"),
    "ticker": ("symbol", "tickers"),
    "created_at": ("computed_at", "updated_at", "cancelled_at", "timestamp", "fired_at"),
    "updated_at": ("computed_at", "created_at", "timestamp", "fired_at"),
    "timestamp": ("updated_at", "computed_at", "created_at", "fired_at"),
    "price_source": ("current_price",),
    "mandate_type": ("mandate_id",),
}


def _pick_unique_column_autocorrect(wrong: str, candidates: list[str]) -> Optional[str]:
    """
    1-shot alias only when the top candidate is a clear unique winner.
    Prefer known aliases that exist on the table; else tight edit-distance gap.
    """
    if not wrong or not candidates:
        return None
    by_lower = {c.lower(): c for c in candidates}
    hinted = [
        by_lower[h.lower()]
        for h in _COMMON_COLUMN_ALIASES.get(wrong.lower(), ())
        if h.lower() in by_lower
    ]
    if len(hinted) == 1:
        return hinted[0] if hinted[0].lower() != wrong.lower() else None
    if len(hinted) > 1:
        for c in candidates:
            if c in hinted and c.lower() != wrong.lower():
                return c

    best = candidates[0]
    if best.lower() == wrong.lower():
        return None
    d0 = _edit_distance(wrong, best)
    if d0 > 3:
        return None
    if len(candidates) > 1:
        d1 = _edit_distance(wrong, candidates[1])
        if d1 - d0 < 2:
            return None
    return best


def _rewrite_sql_column(query: str, wrong: str, replacement: str) -> Optional[str]:
    if not query or not wrong or not replacement or wrong == replacement:
        return None
    new_q, n = re.subn(rf"\b{re.escape(wrong)}\b", replacement, query)
    if n < 1 or new_q == query:
        return None
    return new_q


def _enrich_binder_error(
    run_query: Callable[[str], str],
    spec: WorkerSpec,
    query: str,
    err: str,
) -> str:
    """Attach column_candidates when DuckDB Binder rejects a column name."""
    if not _is_binder_column_error(err):
        return json.dumps({"error": err})
    wrong, resolved_table, candidates = _resolve_binder_column_context(
        run_query, spec, query, err
    )
    payload: dict[str, Any] = {"error": err}
    if wrong and resolved_table:
        payload["hint"] = f"column '{wrong}' not found on {resolved_table}"
    elif wrong:
        payload["hint"] = f"column '{wrong}' not found"
    if candidates:
        payload["column_candidates"] = candidates
    return json.dumps(payload, ensure_ascii=False)


def _try_binder_column_autocorrect(
    run_query: Callable[[str], str],
    spec: WorkerSpec,
    query: str,
    err: str,
) -> Optional[str]:
    """One rewrite+retry when Binder rejects a near-match column name."""
    if not _is_binder_column_error(err):
        return None
    wrong, _table, candidates = _resolve_binder_column_context(run_query, spec, query, err)
    if not wrong:
        return None
    replacement = _pick_unique_column_autocorrect(wrong, candidates)
    if not replacement:
        return None
    rewritten = _rewrite_sql_column(query, wrong, replacement)
    if not rewritten:
        return None
    try:
        raw = _truncate_read_sql_result_for_llm(run_query(rewritten))
        wrapped = _maybe_wrap_summary_dedup_read_sql(spec, rewritten, raw)
        # Surface autocorrect so the LLM stops inventing the bad name next turn.
        try:
            parsed = json.loads(wrapped)
            if isinstance(parsed, list):
                return json.dumps(
                    {
                        "rows": parsed,
                        "_autocorrected_column": {"from": wrong, "to": replacement},
                        "_rewritten_sql": rewritten,
                    },
                    ensure_ascii=False,
                )
            if isinstance(parsed, dict) and "error" not in parsed:
                parsed = {
                    **parsed,
                    "_autocorrected_column": {"from": wrong, "to": replacement},
                    "_rewritten_sql": rewritten,
                }
                return json.dumps(parsed, ensure_ascii=False)
        except Exception:
            pass
        return wrapped
    except Exception:
        return None


def validate_worker_read_sql(spec: WorkerSpec, query: str) -> Optional[str]:
    """Devuelve cuerpo JSON de error o None si la consulta pasó validación previa a ejecución."""
    if not query or not query.strip():
        return json.dumps({"error": "Query vacío."})
    q = query.strip()
    upper = q.upper()
    err = _enforce_allowed_tables_error(spec, upper)
    if err:
        return err
    if (
        _worker_has_runtime_capability(spec, "bounded_select_star_read")
        and re.search(r"\bSELECT\s+\*", upper)
        and "LIMIT" not in upper
    ):
        return json.dumps(
            {
                "error": (
                    "SELECT * sin LIMIT no está permitido por la policy de lectura acotada. "
                    "Usa columnas explícitas, agregaciones o añade LIMIT."
                )
            }
        )
    if _worker_has_runtime_capability(spec, "bounded_json_read") and re.search(r"read_json(_auto)?\s*\(", q, re.IGNORECASE):
        if "LIMIT" not in upper and not re.search(r"\bCOUNT\s*\(", upper):
            return json.dumps(
                {
                    "error": (
                        "Incluye LIMIT (p. ej. LIMIT 30) en consultas con read_json / read_json_auto "
                        "hacia el SIATA. Sin LIMIT el JSON completo excede el contexto del modelo. "
                        "COUNT(*) está permitido sin LIMIT."
                    )
                }
            )
    ro_only = (
        "read_sql es solo lectura. Este trabajador no tiene escritura SQL; usa solo SELECT/WITH/SHOW/DESCRIBE/EXPLAIN/PRAGMA."
        if spec.read_only
        else "read_sql es solo lectura. Usa admin_sql para escrituras (INSERT/UPDATE/DELETE/CREATE, etc.)."
    )
    if not upper.startswith(("SELECT", "WITH", "SHOW", "DESCRIBE", "EXPLAIN", "PRAGMA")):
        return json.dumps({"error": ro_only})
    return None


def run_worker_read_sql(run_query: Callable[[str], str], spec: WorkerSpec, q: str) -> str:
    """Ejecuta read_sql con calificación main/shared/private si aplica (misma lógica que el worker)."""
    val_err = validate_worker_read_sql(spec, q)
    if val_err is not None:
        return val_err
    q = q.strip()
    upper = q.upper()
    try:
        raw = _truncate_read_sql_result_for_llm(run_query(q))
        return _maybe_wrap_summary_dedup_read_sql(spec, q, raw)
    except Exception as e:
        err = str(e)
        if spec.allowed_tables and any(k in upper for k in ("FROM", "JOIN")):
            for schema_try in ("main", "shared", "private"):
                try_q = _qualify_allowed_tables(q, schema_try, spec)
                if try_q != q:
                    try:
                        raw2 = _truncate_read_sql_result_for_llm(run_query(try_q))
                        return _maybe_wrap_summary_dedup_read_sql(spec, try_q, raw2)
                    except Exception as e2:
                        err = str(e2)
        fixed = _try_binder_column_autocorrect(run_query, spec, q, err)
        if fixed is not None:
            return fixed
        return _enrich_binder_error(run_query, spec, q, err)


def run_inspect_schema_worker(run_query: Callable[[str], str]) -> str:
    """Lista tablas con columnas (misma forma útil que graphs.tools.inspect_schema)."""
    try:
        r = json.loads(
            run_query(
                "SELECT table_schema, table_name FROM information_schema.tables "
                "WHERE table_schema NOT IN ('information_schema','pg_catalog') "
                "ORDER BY table_schema, table_name"
            )
        )
        if not r or not isinstance(r, list):
            return "No hay tablas en la base de datos."
        lines: list[str] = []
        for row in r:
            sch = row.get("table_schema", "") if isinstance(row, dict) else ""
            tbl = row.get("table_name", "") if isinstance(row, dict) else ""
            if not sch or not tbl:
                continue
            sch_esc = str(sch).replace("'", "''")
            tbl_esc = str(tbl).replace("'", "''")
            try:
                cols_raw = json.loads(
                    run_query(
                        "SELECT column_name FROM information_schema.columns "
                        f"WHERE table_schema = '{sch_esc}' AND table_name = '{tbl_esc}' "
                        "ORDER BY ordinal_position"
                    )
                )
            except Exception:
                cols_raw = []
            col_names = [
                str(c.get("column_name", "")).strip()
                for c in (cols_raw if isinstance(cols_raw, list) else [])
                if isinstance(c, dict) and str(c.get("column_name", "")).strip()
            ]
            if col_names:
                lines.append(f"- {sch}.{tbl}: {', '.join(col_names)}")
            else:
                lines.append(f"- {sch}.{tbl}")
        return "Tablas disponibles:\n" + "\n".join(lines) if lines else "No hay tablas."
    except Exception as e:
        return json.dumps({"error": str(e)})


def pool_enabled_globally() -> bool:
    v = (os.environ.get("DUCKCLAW_TOOL_READ_POOL_ENABLED") or "true").strip().lower()
    return v not in ("0", "false", "no", "off")


def read_pool_active_for_worker(spec: WorkerSpec) -> bool:
    return pool_enabled_globally() and bool(getattr(spec, "tool_read_pool", True))


def read_pool_max_concurrency() -> int:
    try:
        return max(1, int(os.environ.get("DUCKCLAW_TOOL_READ_POOL_CONCURRENCY", "5")))
    except ValueError:
        return 5


def read_pool_retries() -> int:
    try:
        return max(1, int(os.environ.get("DUCKCLAW_TOOL_READ_POOL_RETRIES", "3")))
    except ValueError:
        return 3


def read_pool_stmt_timeout_ms() -> int:
    try:
        return max(1_000, int(os.environ.get("DUCKCLAW_TOOL_READ_STMT_TIMEOUT_MS", "10000")))
    except ValueError:
        return 10_000


def _get_semaphore() -> threading.BoundedSemaphore:
    global _sem
    with _sem_lock:
        if _sem is None:
            _sem = threading.BoundedSemaphore(read_pool_max_concurrency())
        return _sem


def _is_transient_duckdb_error(exc: BaseException) -> bool:
    cls = type(exc)
    mod = getattr(cls, "__module__", "") or ""
    name = cls.__name__
    if "duckdb" in mod and "IOException" in name:
        return True
    msg = str(exc).lower()
    return any(x in msg for x in ("conflicting lock", " lock", "could not set lock", "io error"))


def _backoff_sleep(attempt: int) -> None:
    base = (0.05, 0.2, 0.8)
    idx = min(attempt, len(base) - 1)
    delay = base[idx] + random.uniform(0, 0.05)
    time.sleep(delay)


def run_ephemeral_read_sql(
    spec: WorkerSpec,
    primary_path: str,
    private_path: str,
    shared_path: Optional[str],
    duckdb_extensions: list[str],
    query: str,
) -> str:
    val_err = validate_worker_read_sql(spec, query)
    if val_err is not None:
        return val_err

    import duckdb

    retries = read_pool_retries()
    stmt_ms = read_pool_stmt_timeout_ms()
    sem = _get_semaphore()
    last_err: Optional[str] = None
    for attempt in range(retries):
        sem.acquire()
        try:
            with duckdb.connect(primary_path, read_only=True) as conn:
                try:
                    conn.execute("SET statement_timeout = ?", [stmt_ms])
                except Exception:
                    pass
                _load_extensions_readonly(conn, duckdb_extensions)
                for stmt in build_attach_statements(primary_path, private_path, shared_path):
                    try:
                        conn.execute(stmt)
                    except Exception as exc:
                        _log.debug("ephemeral ATTACH skip/fail: %s | %s", stmt[:80], exc)
                return run_worker_read_sql(lambda q: connection_query_json(conn, q), spec, query)
        except Exception as exc:
            last_err = str(exc)
            if _is_transient_duckdb_error(exc) and attempt + 1 < retries:
                _log.info(
                    "read_pool read_sql transient error (attempt %s/%s): %s",
                    attempt + 1,
                    retries,
                    last_err[:200],
                )
                _backoff_sleep(attempt)
                continue
            return json.dumps({"error": last_err})
        finally:
            sem.release()
    return json.dumps({"error": last_err or "unknown"})


def run_ephemeral_inspect_schema(
    primary_path: str,
    private_path: str,
    shared_path: Optional[str],
    duckdb_extensions: list[str],
) -> str:
    import duckdb

    retries = read_pool_retries()
    stmt_ms = read_pool_stmt_timeout_ms()
    sem = _get_semaphore()
    last_err: Optional[str] = None
    for attempt in range(retries):
        sem.acquire()
        try:
            with duckdb.connect(primary_path, read_only=True) as conn:
                try:
                    conn.execute("SET statement_timeout = ?", [stmt_ms])
                except Exception:
                    pass
                _load_extensions_readonly(conn, duckdb_extensions)
                for stmt in build_attach_statements(primary_path, private_path, shared_path):
                    try:
                        conn.execute(stmt)
                    except Exception as exc:
                        _log.debug("ephemeral ATTACH skip/fail: %s | %s", stmt[:80], exc)
                return run_inspect_schema_worker(lambda q: connection_query_json(conn, q))
        except Exception as exc:
            last_err = str(exc)
            if _is_transient_duckdb_error(exc) and attempt + 1 < retries:
                _log.info(
                    "read_pool inspect_schema transient error (attempt %s/%s): %s",
                    attempt + 1,
                    retries,
                    last_err[:200],
                )
                _backoff_sleep(attempt)
                continue
            return json.dumps({"error": last_err})
        finally:
            sem.release()
    return json.dumps({"error": last_err or "unknown"})


def should_parallelize_ephemeral_tool_calls(tool_calls: list[dict[str, Any]]) -> bool:
    if len(tool_calls) < 2:
        return False
    names = {(tc.get("name") or "").strip() for tc in tool_calls}
    return bool(names) and names <= DEFAULT_EPHEMERAL_TOOLS


def concurrent_tool_names() -> frozenset[str]:
    return DEFAULT_EPHEMERAL_TOOLS
