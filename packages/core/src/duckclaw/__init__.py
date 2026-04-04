"""DuckClaw core: DuckDB bridge. Namespace merge con duckclaw-shared."""

from __future__ import annotations

import json
import pkgutil
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


__all__ = ["DuckClaw"]
