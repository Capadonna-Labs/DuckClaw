"""DuckDB runtime paths, ATTACH handling, and result-size guards for workers."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from duckclaw.gateway_db import get_gateway_db_path

_log = logging.getLogger(__name__)

READ_SQL_MAX_RESPONSE_CHARS = max(8_000, int(os.environ.get("DUCKCLAW_READ_SQL_MAX_RESPONSE_CHARS", "80000")))
RUN_SANDBOX_TOOL_LLM_MAX_CHARS = max(4_000, int(os.environ.get("DUCKCLAW_RUN_SANDBOX_TOOL_LLM_MAX_CHARS", "12000")))


def truncate_read_sql_result_for_llm(raw: str) -> str:
    if not isinstance(raw, str) or len(raw) <= READ_SQL_MAX_RESPONSE_CHARS:
        return raw
    return json.dumps(
        {
            "warning": (
                "Salida truncada por límite de tamaño del gateway. Para JSON remotos usa LIMIT, "
                "menos columnas, o run_sandbox para aplanar/resumir el archivo completo."
            ),
            "preview": raw[:READ_SQL_MAX_RESPONSE_CHARS],
            "total_chars": len(raw),
            "omitted_chars": len(raw) - READ_SQL_MAX_RESPONSE_CHARS,
        },
        ensure_ascii=False,
    )


def escape_attach_path(path: str) -> str:
    return str(path).replace("'", "''")


def same_duckdb_file(a: str, b: str) -> bool:
    sa = (a or "").strip()
    sb = (b or "").strip()
    if not sa or not sb:
        return False
    try:
        return Path(sa).expanduser().resolve() == Path(sb).expanduser().resolve()
    except Exception:
        return os.path.abspath(sa) == os.path.abspath(sb)


def resolve_shared_db_path(spec: Any, override: Optional[str]) -> Optional[str]:
    env_key = (getattr(spec, "forge_shared_db_path_env", None) or "").strip()
    if not env_key:
        return None
    raw = (override or "").strip()
    if raw:
        return raw
    return (os.environ.get(env_key) or "").strip() or None


def apply_forge_attaches(
    db: Any,
    private_path: str,
    shared_path: Optional[str],
    *,
    read_only_attaches: bool | None = None,
    private_attach_read_only: bool = False,
    shared_attach_read_only: bool = True,
    skip_private_attach: bool = False,
) -> None:
    if read_only_attaches is not None:
        private_attach_read_only = bool(read_only_attaches)
        shared_attach_read_only = bool(read_only_attaches)
    ro_p = " (READ_ONLY)" if private_attach_read_only else ""
    ro_s = " (READ_ONLY)" if shared_attach_read_only else ""
    if not skip_private_attach:
        esc_p = escape_attach_path(private_path)
        try:
            try:
                db.execute("DETACH private")
            except Exception:
                pass
            db.execute(f"ATTACH '{esc_p}' AS private{ro_p}")
        except Exception as exc:
            _log.debug("forge ATTACH private skipped: %s", exc)
    sp = (shared_path or "").strip()
    try:
        try:
            db.execute("DETACH shared")
        except Exception:
            pass
    except Exception:
        pass
    if not sp:
        return
    try:
        if Path(sp).resolve() == Path(private_path).resolve():
            return
    except Exception:
        if os.path.abspath(sp) == os.path.abspath(private_path):
            return
    Path(sp).parent.mkdir(parents=True, exist_ok=True)
    esc_s = escape_attach_path(sp)
    try:
        db.execute(f"ATTACH '{esc_s}' AS shared{ro_s}")
    except Exception as exc:
        _log.warning("forge ATTACH shared failed (%s): %s", sp, exc)


def bootstrap_shared_main_schema(db: Any, spec: Any) -> None:
    if not getattr(spec, "forge_apply_schema_to_shared", False):
        return
    from duckclaw.workers.loader import _split_sql, load_schema_sql

    sql = load_schema_sql(spec)
    if not sql.strip():
        return
    adapted = sql.replace("CREATE TABLE IF NOT EXISTS main.", "CREATE TABLE IF NOT EXISTS shared.main.")
    for stmt in _split_sql(adapted):
        if stmt.strip():
            try:
                db.execute(stmt)
            except Exception as exc:
                _log.debug("forge shared schema stmt skipped: %s", exc)


def infer_user_id_for_writer(db_path: str) -> str:
    parts = Path(db_path).expanduser().resolve().parts
    if "private" in parts:
        i = parts.index("private")
        if i + 1 < len(parts):
            return str(parts[i + 1])
    return "default"


def get_db_path(worker_id: str, instance_name: Optional[str], base_path: Optional[str]) -> str:
    del worker_id
    base = (base_path or os.environ.get("DUCKDB_PATH") or get_gateway_db_path() or "").strip()
    if not base:
        base = str(Path.cwd() / "db" / "workers.duckdb")
    p = Path(base)
    if base_path and p.suffix.lower() == ".duckdb":
        p.parent.mkdir(parents=True, exist_ok=True)
        return str(p.expanduser().resolve())
    if not p.suffix or p.suffix.lower() != ".duckdb":
        p = p / "workers.duckdb"
    if instance_name:
        p = p.parent / f"workers_{instance_name}.duckdb"
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)
