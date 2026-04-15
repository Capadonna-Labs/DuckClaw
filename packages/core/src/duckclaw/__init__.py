"""DuckClaw core: DuckDB bridge. Namespace merge con duckclaw-shared."""

from __future__ import annotations

import json
import os
import pkgutil
import inspect
import time
from typing import Any, Literal, Optional

__path__ = pkgutil.extend_path(__path__, __name__)

try:
    from duckclaw._duckclaw import DuckClaw as _NativeDuckClaw
except ImportError:
    _NativeDuckClaw = None

import duckdb as _duckdb


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
        # region agent log
        try:
            _p = str(self._path or "")
            if (not self._read_only) and ("finanzdb1.duckdb" in _p):
                _callers = []
                for _fr in inspect.stack(context=0)[1:8]:
                    _callers.append(
                        {
                            "file": str(_fr.filename)[-120:],
                            "func": str(_fr.function),
                            "line": int(_fr.lineno),
                        }
                    )
                with open(
                    "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
                    "a",
                    encoding="utf-8",
                ) as _df:
                    _df.write(
                        json.dumps(
                            {
                                "sessionId": "c964f7",
                                "hypothesisId": "L8_finanzdb1_rw_handle_lifecycle",
                                "location": "packages/core/src/duckclaw/__init__.py:DuckClaw.__init__",
                                "message": "duckclaw_open_rw_finanzdb1",
                                "data": {
                                    "pid": os.getpid(),
                                    "obj_id": id(self),
                                    "db_path_tail": _p[-140:],
                                    "read_only": bool(self._read_only),
                                    "engine": str(engine),
                                    "backend": "native" if use_native else "python",
                                    "callers": _callers,
                                },
                                "timestamp": int(time.time() * 1000),
                            }
                        )
                        + "\n"
                    )
        except Exception:
            pass
        # endregion
        if use_native:
            self._native = _NativeDuckClaw(self._path)
        else:
            self._con = _duckdb.connect(self._path, read_only=self._read_only)

    def query(self, sql: str) -> str:
        if self._native is not None:
            return self._native.query(sql)
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
        # region agent log
        try:
            _p = str(self._path or "")
            if (not self._read_only) and ("finanzdb1.duckdb" in _p):
                with open(
                    "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
                    "a",
                    encoding="utf-8",
                ) as _df:
                    _df.write(
                        json.dumps(
                            {
                                "sessionId": "c964f7",
                                "hypothesisId": "L8_finanzdb1_rw_handle_lifecycle",
                                "location": "packages/core/src/duckclaw/__init__.py:DuckClaw.close",
                                "message": "duckclaw_close_rw_finanzdb1",
                                "data": {
                                    "pid": os.getpid(),
                                    "obj_id": id(self),
                                    "db_path_tail": _p[-140:],
                                    "backend": "native" if self._native is not None else "python",
                                },
                                "timestamp": int(time.time() * 1000),
                            }
                        )
                        + "\n"
                    )
        except Exception:
            pass
        # endregion
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

    def resume_readonly_file_handle(self) -> None:
        """Reabre la conexión RO tras ``suspend_readonly_file_handle``."""
        if self._native is not None or self._path == ":memory:" or not self._read_only:
            return
        if self._con is None:
            self._con = _duckdb.connect(self._path, read_only=True)


__all__ = ["DuckClaw"]
