# specs/Pipeline_de_Datos_Zero-Copy_con_PyArrow.md

"""Pipeline de datos zero-copy: DuckDB ↔ PyArrow ↔ Parquet / IPC / Pandas / LLM.

El módulo funciona en dos modos:
  - ARROW_AVAILABLE=True  → usa pyarrow + duckdb Python SDK (zero-copy real)
  - ARROW_AVAILABLE=False → fallback a JSON/CSV (comportamiento previo sin dependencias)
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterator, Optional

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    import pyarrow.ipc as ipc
    import duckdb as _duckdb

    _ARROW = True
except ImportError:
    _ARROW = False


def arrow_available() -> bool:
    """True si pyarrow y duckdb Python SDK están disponibles."""
    return _ARROW


# ---------------------------------------------------------------------------
# ArrowBridge
# ---------------------------------------------------------------------------

class ArrowBridge:
    """Punto de acceso único al pipeline zero-copy DuckDB ↔ Arrow.

    Puede instanciarse:
    - Sin argumentos → conexión DuckDB in-memory (útil para from_json).
    - Con db_path     → conexión read-only al archivo .duckdb de DuckClaw.
    """

    def __init__(self, db_path: str | None = None):
        if not _ARROW:
            raise ImportError(
                "PyArrow y/o duckdb Python SDK no están instalados. "
                "Ejecuta: pip install pyarrow duckdb"
            )
        self._db_path = db_path
        self._conn: Any = None

    # ------------------------------------------------------------------
    # Gestión de conexión
    # ------------------------------------------------------------------

    def _get_conn(self) -> Any:
        if self._conn is None:
            if self._db_path:
                self._conn = _duckdb.connect(self._db_path, read_only=True)
            else:
                self._conn = _duckdb.connect(":memory:")
        return self._conn

    def close(self) -> None:
        if self._conn is not None:
            try:
                self._conn.close()
            except Exception:
                pass
            self._conn = None

    def __enter__(self) -> "ArrowBridge":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Constructores de clase
    # ------------------------------------------------------------------

    @classmethod
    def from_json(cls, json_str: str) -> "pa.Table":
        """Convierte la salida JSON de db.query() a un pyarrow.Table (vía duckdb in-memory).

        Evita la cadena:  JSON str → json.loads() → list[dict] → pa.Table manual.
        Usa duckdb in-memory para hacer la conversión directa a Arrow.
        """
        if not _ARROW:
            raise ImportError("pyarrow y duckdb no disponibles")
        data = json.loads(json_str) if isinstance(json_str, str) else json_str
        if not data:
            return pa.table({})
        conn = _duckdb.connect(":memory:")
        try:
            # Convierte list[dict] → pa.Table y lo registra como relación Arrow
            import pandas as _pd  # noqa: PLC0415
            df = _pd.DataFrame(data)
            conn.register("_tmp_json", df)
            return conn.execute("SELECT * FROM _tmp_json").fetch_arrow_table()
        finally:
            conn.close()

    @classmethod
    def from_parquet(cls, path: str | Path) -> "pa.Table":
        """Lee un archivo .parquet con mmap (zero-copy del kernel)."""
        if not _ARROW:
            raise ImportError("pyarrow no disponible")
        return pq.read_table(str(path), memory_map=True)

    @classmethod
    def from_db_path(cls, db_path: str, sql: str) -> "pa.Table":
        """Ejecuta sql en el archivo .duckdb en modo read-only y devuelve Arrow Table."""
        bridge = cls(db_path=db_path)
        try:
            return bridge.query_arrow(sql)
        finally:
            bridge.close()

    # ------------------------------------------------------------------
    # Consultas
    # ------------------------------------------------------------------

    def query_arrow(self, sql: str) -> "pa.Table":
        """Ejecuta SQL y devuelve un pyarrow.Table (zero-copy vía Arrow C Data Interface)."""
        return self._get_conn().execute(sql).fetch_arrow_table()

    def query_batches(self, sql: str, batch_size: int = 10_000) -> "Iterator[pa.RecordBatch]":
        """Itera sobre RecordBatches sin materializar el resultado completo en RAM."""
        reader = self._get_conn().execute(sql).arrow(batch_size)
        try:
            for batch in reader:
                yield batch
        finally:
            try:
                reader.close()
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Conversiones de salida
    # ------------------------------------------------------------------

    @staticmethod
    def to_pandas(table: "pa.Table") -> Any:
        """Convierte un pyarrow.Table a pandas DataFrame.

        Usa zero_copy_only=False como fallback seguro (pyarrow puede copiar
        cuando los tipos no son alineados, pero es siempre correcto).
        """
        return table.to_pandas(zero_copy_only=False, timestamp_as_object=False)

    @staticmethod
    def to_parquet(
        table: "pa.Table",
        path: str | Path,
        compression: str = "snappy",
    ) -> Path:
        """Escribe un pyarrow.Table a .parquet con compresión snappy por defecto."""
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        pq.write_table(table, str(dest), compression=compression)
        return dest

    @staticmethod
    def to_ipc(table: "pa.Table", path: str | Path) -> Path:
        """Escribe un pyarrow.Table a formato Arrow IPC / Feather v2 (lectura via mmap)."""
        import pyarrow.feather as feather  # noqa: PLC0415
        dest = Path(path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        feather.write_feather(table, str(dest))
        return dest

    @staticmethod
    def to_llm_context(
        table: "pa.Table",
        max_rows: int = 20,
        include_stats: bool = True,
    ) -> str:
        """Serializa un pyarrow.Table como bloque de texto compacto para el LLM.

        Spec §3 — LLMContextSerializer:
        1. Schema (columna: tipo)
        2. Muestra de max_rows filas en markdown
        3. Estadísticas básicas para columnas numéricas (si include_stats=True)
        """
        return LLMContextSerializer.serialize(table, max_rows=max_rows, include_stats=include_stats)


# ---------------------------------------------------------------------------
# StreamingBatchReader
# ---------------------------------------------------------------------------

class StreamingBatchReader:
    """Lee datasets grandes en RecordBatches sin cargar todo en RAM.

    Spec §3 — para resultados que superan la memoria disponible.
    """

    def __init__(self, db_path: str | None = None):
        if not _ARROW:
            raise ImportError("pyarrow y duckdb no disponibles")
        self._bridge = ArrowBridge(db_path=db_path)

    def read(self, sql: str, batch_size: int = 50_000) -> "Iterator[pa.RecordBatch]":
        yield from self._bridge.query_batches(sql, batch_size)

    def read_all(self, sql: str) -> "pa.Table":
        return self._bridge.query_arrow(sql)  # noqa: FURB118

    def close(self) -> None:
        self._bridge.close()

    def __enter__(self) -> "StreamingBatchReader":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()


# ---------------------------------------------------------------------------
# LLMContextSerializer
# ---------------------------------------------------------------------------

class LLMContextSerializer:
    """Convierte tablas Arrow en contexto texto compacto para el LLM.

    Spec §3: schema + muestra markdown + estadísticas.
    """

    @staticmethod
    def serialize(
        table: "pa.Table",
        max_rows: int = 20,
        include_stats: bool = True,
    ) -> str:
        if not _ARROW:
            return ""
        if table is None or table.num_rows == 0:
            return "(Sin datos)"

        lines: list[str] = []

        # 1. Schema
        schema_parts = [f"`{f.name}` ({f.type})" for f in table.schema]
        lines.append("**Schema:** " + ", ".join(schema_parts))
        lines.append("")

        # 2. Muestra en markdown
        sample = table.slice(0, max_rows)
        df = sample.to_pandas(zero_copy_only=False)
        lines.append(df.to_markdown(index=False))

        if table.num_rows > max_rows:
            lines.append(f"\n*... {table.num_rows - max_rows} filas más (muestra de {max_rows})*")

        # 3. Estadísticas numéricas básicas
        if include_stats:
            numeric_cols = [f.name for f in table.schema if pa.types.is_integer(f.type) or pa.types.is_floating(f.type)]
            if numeric_cols:
                lines.append("\n**Estadísticas:**")
                stats_df = df[numeric_cols].describe().round(2)
                lines.append(stats_df.to_markdown())

        return "\n".join(lines)

    @staticmethod
    def from_json(json_str: str, max_rows: int = 20) -> str:
        """Atajo: convierte la salida JSON de db.query() directamente a contexto LLM."""
        if not _ARROW:
            # Fallback: parsear JSON y hacer una tabla manual
            try:
                rows = json.loads(json_str) if isinstance(json_str, str) else (json_str or [])
                if not rows:
                    return "(Sin datos)"
                headers = list(rows[0].keys())
                header_line = "| " + " | ".join(headers) + " |"
                sep_line = "| " + " | ".join(["---"] * len(headers)) + " |"
                body_lines = []
                for row in rows[:max_rows]:
                    vals = [str(row.get(h, "")) for h in headers]
                    body_lines.append("| " + " | ".join(vals) + " |")
                result = "\n".join([header_line, sep_line] + body_lines)
                if len(rows) > max_rows:
                    result += f"\n*... {len(rows) - max_rows} filas más*"
                return result
            except Exception:
                return "(Error serializando datos)"
        table = ArrowBridge.from_json(json_str)
        return LLMContextSerializer.serialize(table, max_rows=max_rows)


# ---------------------------------------------------------------------------
# SandboxDataChannel
# ---------------------------------------------------------------------------

class SandboxDataChannel:
    """Exporta datos de DuckClaw al sandbox Docker como Parquet (spec §3).

    Reemplaza el export CSV de sandbox.data_inject() cuando PyArrow está disponible.
    Fallback automático a CSV si la exportación Arrow falla.
    """

    @staticmethod
    def inject(db: Any, sql: str, session_dir: Path) -> str:
        """Exporta el resultado de sql al directorio data/ de la sesión del sandbox.

        Devuelve la ruta al archivo generado (parquet si disponible, csv si no).
        """
        data_dir = session_dir / "data"
        data_dir.mkdir(parents=True, exist_ok=True)

        # Intento 1: Parquet via Arrow (zero-copy, columnar, tipado)
        if _ARROW:
            try:
                dest = data_dir / "data.parquet"
                # Crear conexión in-memory y cargar los datos vía JSON de DuckClaw
                raw = db.query(sql)
                table = ArrowBridge.from_json(raw)
                ArrowBridge.to_parquet(table, dest)
                return str(dest)
            except Exception:
                pass

        # Intento 2: COPY TO via DuckClaw execute (sin pyarrow)
        try:
            dest_csv = data_dir / "data.csv"
            db.execute(f"COPY ({sql}) TO '{dest_csv}' (HEADER, DELIMITER ',')")
            return str(dest_csv)
        except Exception:
            pass

        # Intento 3: Fallback manual JSON → CSV
        try:
            import csv  # noqa: PLC0415
            raw = db.query(sql)
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
            if not rows:
                return ""
            dest_csv = data_dir / "data.csv"
            with open(dest_csv, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            return str(dest_csv)
        except Exception as e:
            return f"Error exportando datos: {e}"

    @staticmethod
    def read_artifact(path: str) -> "pa.Table | None":
        """Lee un artefacto parquet o CSV producido por el sandbox y devuelve Arrow Table."""
        if not _ARROW:
            return None
        p = Path(path)
        if not p.exists():
            return None
        try:
            if p.suffix == ".parquet":
                return pq.read_table(str(p), memory_map=True)
            if p.suffix == ".csv":
                return _duckdb.connect(":memory:").execute(f"SELECT * FROM read_csv_auto('{p}')").arrow()
        except Exception:
            pass
        return None
