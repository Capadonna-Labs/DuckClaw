"""
Ephemeral read-only DuckDB connections for parallel worker tool execution.

Spec: specs/features/Concurrent Tool Node (Ephemeral Read-Pool).md
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

_log = logging.getLogger(__name__)

_READ_SQL_MAX_RESPONSE_CHARS = max(8_000, int(os.environ.get("DUCKCLAW_READ_SQL_MAX_RESPONSE_CHARS", "80000")))

DEFAULT_EPHEMERAL_TOOLS = frozenset({"read_sql", "inspect_schema"})

_sem: Optional[threading.BoundedSemaphore] = None
_sem_lock = threading.Lock()


_RE_MAC_MINI_CUOTA = re.compile(r"^Mac Mini - Cuota\s+", re.IGNORECASE)


def _finanz_row_amount_cop(r: dict[str, str]) -> float:
    try:
        return float(r.get("amount") or 0)
    except (TypeError, ValueError):
        return 0.0


def _finanz_deudas_mac_mini_installment_ids_to_exclude(rows: list[dict[str, str]]) -> set[str]:
    """
    Si coexisten fila agregada Mac Mini (TC Bancolombia) y filas «Mac Mini - Cuota …»,
    excluye esas cuotas del total para no doblar el mismo crédito (evidencia traces 2026-04).
    """
    tc = "TC Bancolombia"
    has_aggregate = False
    installment_ids: list[str] = []
    for r in rows:
        if _finanz_row_amount_cop(r) <= 0:
            continue
        cred = (r.get("creditor") or "").strip()
        desc = (r.get("description") or "").strip()
        if cred != tc:
            continue
        if _RE_MAC_MINI_CUOTA.match(desc):
            installment_ids.append(str(r.get("id", "")))
            continue
        dlow = desc.lower()
        if "mac mini" not in dlow:
            continue
        if "8 cuotas" in dlow or "cuotas mensuales" in dlow:
            has_aggregate = True
    if has_aggregate and len(installment_ids) >= 2:
        return {i for i in installment_ids if i}
    return set()


def _maybe_wrap_finanz_deudas_read_sql(spec: WorkerSpec, query: str, raw: str) -> str:
    """Anexa totales deduplicados cuando read_sql devuelve filas de finance_worker.deudas."""
    wid = (getattr(spec, "logical_worker_id", None) or spec.worker_id or "").strip()
    if wid != "finanz":
        return raw
    qlow = query.lower()
    if "deudas" not in qlow:
        return raw
    sch = (getattr(spec, "schema_name", None) or "").strip().lower()
    if "finance_worker" not in qlow and sch != "finance_worker":
        return raw
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if isinstance(parsed, dict):
        return raw
    if not isinstance(parsed, list) or not parsed:
        return raw
    exclude = _finanz_deudas_mac_mini_installment_ids_to_exclude(parsed)
    if not exclude:
        return raw
    naive = sum(_finanz_row_amount_cop(r) for r in parsed if _finanz_row_amount_cop(r) > 0)
    deduped = sum(
        _finanz_row_amount_cop(r)
        for r in parsed
        if _finanz_row_amount_cop(r) > 0 and str(r.get("id", "")) not in exclude
    )
    meta = {
        "suma_todas_las_filas_cop": naive,
        "total_recomendado_resumen_cop": deduped,
        "regla_aplicada": (
            "Excluidas del total las filas «Mac Mini - Cuota …» (TC Bancolombia) porque coexisten "
            "con la fila agregada del mismo crédito; no sumar ambas en un único total."
        ),
        "ids_excluidos_del_total": sorted(exclude),
    }
    return json.dumps({"deudas_filas": parsed, "_totales_resumen_cop": meta}, ensure_ascii=False)


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


def validate_worker_read_sql(spec: WorkerSpec, query: str) -> Optional[str]:
    """Devuelve cuerpo JSON de error o None si la consulta pasó validación previa a ejecución."""
    if not query or not query.strip():
        return json.dumps({"error": "Query vacío."})
    q = query.strip()
    upper = q.upper()
    err = _enforce_allowed_tables_error(spec, upper)
    if err:
        return err
    _lid = (getattr(spec, "logical_worker_id", None) or spec.worker_id or "").strip()
    if _lid == "bi_analyst" and re.search(r"\bSELECT\s+\*", upper) and "LIMIT" not in upper:
        return json.dumps(
            {
                "error": (
                    "SELECT * sin LIMIT no está permitido para tablas analíticas. "
                    "Usa columnas explícitas, agregaciones o añade LIMIT."
                )
            }
        )
    if _lid == "siata_analyst" and re.search(r"read_json(_auto)?\s*\(", q, re.IGNORECASE):
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
        return _maybe_wrap_finanz_deudas_read_sql(spec, q, raw)
    except Exception as e:
        err = str(e)
        if spec.allowed_tables and any(k in upper for k in ("FROM", "JOIN")):
            for schema_try in ("main", "shared", "private"):
                try_q = _qualify_allowed_tables(q, schema_try, spec)
                if try_q != q:
                    try:
                        raw2 = _truncate_read_sql_result_for_llm(run_query(try_q))
                        return _maybe_wrap_finanz_deudas_read_sql(spec, try_q, raw2)
                    except Exception:
                        pass
        return json.dumps({"error": err})


def run_inspect_schema_worker(run_query: Callable[[str], str]) -> str:
    """Lista tablas (misma consulta que factory._inspect_schema_worker)."""
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
            if sch and tbl:
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
