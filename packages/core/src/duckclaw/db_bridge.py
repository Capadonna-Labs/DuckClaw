"""DuckDB bridge implementation (importable submodule for namespace merge)."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Literal, Optional

_log = logging.getLogger(__name__)

try:
    from duckclaw._duckclaw import DuckClaw as _NativeDuckClaw
except ImportError:
    _NativeDuckClaw = None

import duckdb as _duckdb


def _vault_writer_defer_seconds() -> float:
    raw = (os.environ.get("DUCKCLAW_VAULT_WRITER_DEFER_SEC") or "120").strip()
    try:
        return max(5.0, float(raw))
    except ValueError:
        return 120.0


def _is_duckdb_lock_error(exc: BaseException) -> bool:
    """Contención al abrir mismo archivo DuckDB (otro proceso RW, u otra config en mismo PID)."""
    msg = str(exc).lower()
    return (
        "lock" in msg
        or "conflicting" in msg
        or "different configuration" in msg
    )


def _duckdb_python_connect_with_retry(db_path: str, *, read_only: bool) -> Any:
    """
    Abre duckdb.connect; en solo lectura reintenta ante lock — alineado con
    ``graph_server._open_duckclaw_readonly_with_retry`` y ``context_injection_handler._connect_duckdb_writable``.
    """
    from duckclaw.spawn_profile import effective_hub_read_only

    read_only = effective_hub_read_only(db_path, read_only)
    raw_attempts = (os.environ.get("DUCKCLAW_GATEWAY_RO_LOCK_ATTEMPTS") or "24").strip()
    try:
        attempts = max(1, min(int(raw_attempts), 80))
    except ValueError:
        attempts = 24
    raw_sleep = (os.environ.get("DUCKCLAW_GATEWAY_RO_LOCK_BASE_SLEEP_S") or "0.15").strip()
    try:
        base_sleep_s = float(raw_sleep)
    except ValueError:
        base_sleep_s = 0.15
    base_sleep_s = max(0.05, base_sleep_s)

    if not read_only or (db_path or "").strip() in ("", ":memory:"):
        return _duckdb.connect(db_path, read_only=read_only)

    last: BaseException | None = None
    for i in range(attempts):
        try:
            return _duckdb.connect(db_path, read_only=True)
        except BaseException as exc:
            last = exc
            if not _is_duckdb_lock_error(exc):
                raise
            delay = base_sleep_s * min(i + 1, 12)
            if i + 1 < attempts:
                time.sleep(delay)
            continue
    assert last is not None
    raise last


class DuckClaw:
    """
    Puente DuckDB. La extensión C++ solo se usa con read_only=False; con read_only=True
    se usa siempre duckdb Python para respetar el modo solo lectura.
    """

    __slots__ = ("_path", "_read_only", "_native", "_con", "_external_writer_defer_until")

    def __init__(
        self,
        db_path: str,
        *,
        read_only: bool = False,
        engine: Literal["auto", "python"] = "auto",
    ) -> None:
        self._path = (db_path or ":memory:").strip() or ":memory:"
        self._read_only = bool(read_only)
        self._native: Any = None
        self._con: Any = None
        self._external_writer_defer_until = 0.0
        use_native = (
            engine == "auto"
            and _NativeDuckClaw is not None
            and not self._read_only
            and self._path != ":memory:"
        )
        if use_native:
            self._native = _NativeDuckClaw(self._path)
        else:
            self._con = _duckdb_python_connect_with_retry(
                self._path,
                read_only=self._read_only,
            )

    def _external_writer_defer_active(self) -> bool:
        until = float(getattr(self, "_external_writer_defer_until", 0.0) or 0.0)
        return until > 0.0 and time.monotonic() < until

    def _rows_to_json(self, result: Any) -> str:
        rows = result.fetchall()
        names = [d[0] for d in result.description]
        out = [dict(zip(names, (str(v) for v in row))) for row in rows]
        return json.dumps(out, ensure_ascii=False)

    def _ephemeral_read_query(self, sql: str) -> str:
        """
        Lectura RO de corta duración mientras db-writer tiene prioridad de lock.

        Ephemeral connection avoids re-acquiring the gateway's persistent handle
        between StateDelta LPUSH and the remote writer COMMIT.
        """
        with _duckdb.connect(self._path, read_only=True) as conn:
            return self._rows_to_json(conn.execute(sql))

    def _ensure_python_exec_connection(self) -> None:
        """Reabre conexión Python si quedó en None tras liberar el handle para db-writer."""
        if self._native is not None:
            return
        if self._con is not None:
            return
        if self._external_writer_defer_active():
            raise RuntimeError(
                "DuckDB: consulta durante handoff a db-writer; use query() (lee vía conexión efímera)."
            )
        rp = (self._path or "").strip()
        if rp not in ("", ":memory:"):
            try:
                self.resume_file_handle()
            except Exception:
                pass
        if self._con is None:
            raise RuntimeError(
                "DuckDB: conexión cerrada (_con is None). Suele pasar si "
                "release_file_handle_for_external_writer() no fue seguido de resume_file_handle()."
            )

    def query(self, sql: str) -> str:
        if self._native is not None:
            return self._native.query(sql)
        if self._con is None and self._external_writer_defer_active():
            return self._ephemeral_read_query(sql)
        self._ensure_python_exec_connection()
        result = self._con.execute(sql)
        return self._rows_to_json(result)

    def execute(self, sql: str, params: Optional[Any] = None) -> Any:
        if self._native is not None:
            if params is None:
                return self._native.execute(sql)
            self.release_file_handle_for_external_writer()
        self._ensure_python_exec_connection()
        if params is not None:
            self._con.execute(sql, params)
        else:
            self._con.execute(sql)
        return self._con.fetchall()

    def get_version(self) -> str:
        if self._native is not None:
            return str(self._native.get_version())
        self._ensure_python_exec_connection()
        return str(self._con.execute("SELECT version()").fetchone()[0])

    def __enter__(self) -> "DuckClaw":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.close()

    def close(self) -> None:
        """Cierra el handle DuckDB para liberar el archivo (conexiones efímeras)."""
        if self._native is not None:
            try:
                self._native.execute("CHECKPOINT")
            except Exception:
                pass
            self._native = None
        if self._con is not None:
            if not self._read_only:
                try:
                    self._con.execute("CHECKPOINT")
                except Exception:
                    pass
            try:
                self._con.close()
            finally:
                self._con = None

    def suspend_readonly_file_handle(self) -> None:
        """
        Cierra la conexión Python en modo solo lectura para liberar el lock del archivo.
        Otro proceso (p. ej. db-writer) puede abrir el mismo .duckdb en escritura mientras
        esta instancia no tiene handle abierto. No-op para :memory:, motor nativo RW o read_only=False.
        """
        if self._native is not None or self._path == ":memory:" or not self._read_only:
            return
        if self._con is not None:
            try:
                self._con.close()
            except Exception:
                pass
            self._con = None

    def release_file_handle_for_external_writer(self) -> None:
        """
        Cierra cualquier handle Python al archivo (RO o RW) para que db-writer u otra
        conexión con distinta configuración pueda abrir el mismo .duckdb en este PID.
        """
        if self._path == ":memory:":
            return
        if self._native is not None:
            self.close()
            return
        if self._con is not None:
            if not self._read_only:
                try:
                    self._con.execute("CHECKPOINT")
                except Exception:
                    pass
            try:
                self._con.close()
            except Exception:
                pass
            self._con = None
        self._external_writer_defer_until = time.monotonic() + _vault_writer_defer_seconds()

    def resume_readonly_file_handle(self) -> None:
        """Reabre la conexión RO tras ``suspend_readonly_file_handle``."""
        if self._native is not None or self._path == ":memory:" or not self._read_only:
            return
        if self._con is None:
            self._con = _duckdb_python_connect_with_retry(self._path, read_only=True)

    def resume_file_handle(self) -> None:
        """Reabre handle RO o RW tras ``release_file_handle_for_external_writer``."""
        if self._native is not None or self._path == ":memory:":
            return
        self._external_writer_defer_until = 0.0
        if self._con is not None:
            return
        self._con = _duckdb_python_connect_with_retry(self._path, read_only=self._read_only)


__all__ = ["DuckClaw"]
