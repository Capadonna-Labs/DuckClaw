"""DuckClaw core: DuckDB bridge. Namespace merge con duckclaw-shared."""

from __future__ import annotations

import json
import os
import pkgutil
import inspect
from typing import Any, Literal, Optional

__path__ = pkgutil.extend_path(__path__, __name__)

try:
    from duckclaw._duckclaw import DuckClaw as _NativeDuckClaw
except ImportError:
    _NativeDuckClaw = None

import duckdb as _duckdb

from duckclaw.debug_session_log import agent_debug_log


class DuckClaw:
    """
    Puente DuckDB. La extensión C++ solo se usa con read_only=False; con read_only=True
    se usa siempre duckdb Python para respetar el modo solo lectura.
    """

    __slots__ = ("_path", "_read_only", "_native", "_con")

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
        use_native = (
            engine == "auto"
            and _NativeDuckClaw is not None
            and not self._read_only
            and self._path != ":memory:"
        )
        if use_native:
            self._native = _NativeDuckClaw(self._path)
        else:
            self._con = _duckdb.connect(self._path, read_only=self._read_only)
        # #region agent log
        try:
            _db_tail = (self._path or "")[-96:]
            if _db_tail.endswith(".duckdb"):
                _fr = inspect.stack()[1]
                agent_debug_log(
                    "duckclaw/__init__.py:DuckClaw.__init__",
                    "duckdb_handle_open",
                    {
                        "pid": os.getpid(),
                        "read_only": self._read_only,
                        "native": self._native is not None,
                        "path_tail": _db_tail,
                        "caller": f"{_fr.filename}:{_fr.lineno}",
                    },
                    hypothesis_id="H1",
                )
        except Exception:
            pass
        # #endregion

    def query(self, sql: str) -> str:
        if self._native is not None:
            return self._native.query(sql)
        # #region agent log
        if self._con is None:
            agent_debug_log(
                "duckclaw/__init__.py:DuckClaw.query",
                "query with _con is None",
                {
                    "read_only": self._read_only,
                    "path_tail": (self._path or "")[-64:],
                    "sql_head": (sql or "")[:120],
                },
                hypothesis_id="H1",
            )
        # #endregion
        result = self._con.execute(sql)
        rows = result.fetchall()
        names = [d[0] for d in result.description]
        out = [dict(zip(names, (str(v) for v in row))) for row in rows]
        return json.dumps(out, ensure_ascii=False)

    def execute(self, sql: str, params: Optional[Any] = None) -> Any:
        if self._native is not None:
            if params is not None:
                return self._native.execute(sql, params)
            return self._native.execute(sql)
        # #region agent log
        if self._con is None:
            agent_debug_log(
                "duckclaw/__init__.py:DuckClaw.execute",
                "execute with _con is None",
                {
                    "read_only": self._read_only,
                    "path_tail": (self._path or "")[-64:],
                    "sql_head": (sql or "")[:120],
                },
                hypothesis_id="H1",
            )
        # #endregion
        if params is not None:
            self._con.execute(sql, params)
        else:
            self._con.execute(sql)
        return self._con.fetchall()

    def get_version(self) -> str:
        if self._native is not None:
            return str(self._native.get_version())
        return str(self._con.execute("SELECT version()").fetchone()[0])

    def __enter__(self) -> "DuckClaw":
        return self

    def __exit__(self, _exc_type: Any, _exc: Any, _tb: Any) -> None:
        self.close()

    def close(self) -> None:
        """Cierra el handle DuckDB para liberar el archivo (conexiones efímeras)."""
        # #region agent log
        try:
            _db_tail = (self._path or "")[-96:]
            if _db_tail.endswith(".duckdb"):
                agent_debug_log(
                    "duckclaw/__init__.py:DuckClaw.close",
                    "duckdb_handle_close",
                    {
                        "pid": os.getpid(),
                        "read_only": self._read_only,
                        "native": self._native is not None,
                        "path_tail": _db_tail,
                    },
                    hypothesis_id="H3",
                )
        except Exception:
            pass
        # #endregion
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
        # #region agent log
        agent_debug_log(
            "duckclaw/__init__.py:suspend_readonly_file_handle",
            "after suspend (RO handle released)",
            {"read_only": self._read_only, "path_tail": (self._path or "")[-64:]},
            hypothesis_id="H2",
        )
        # #endregion

    def resume_readonly_file_handle(self) -> None:
        """Reabre la conexión RO tras ``suspend_readonly_file_handle``."""
        if self._native is not None or self._path == ":memory:" or not self._read_only:
            return
        if self._con is None:
            self._con = _duckdb.connect(self._path, read_only=True)
        # #region agent log
        agent_debug_log(
            "duckclaw/__init__.py:resume_readonly_file_handle",
            "after resume (RO handle open)",
            {"read_only": self._read_only, "path_tail": (self._path or "")[-64:]},
            hypothesis_id="H2",
        )
        # #endregion


__all__ = ["DuckClaw"]
