#!/usr/bin/env python3
"""
Exporta OHLCV desde el data lake de Capadonna en el VPS (solo stdout JSON).

Uso (invocado por Duckclaw vía SSH con placeholders ya sustituidos):
  python3 export_lake_ohlcv.py TICKER TIMEFRAME LOOKBACK_DAYS

Lee Parquet bajo:
  $CAPADONNA_LAKE_DATA_ROOT/<subdir>/**/*.parquet

Layout típico en el VPS (Hive + Delta, Parquet de datos):
  daily/symbol=CCJ/year=2025/CCJ_daily.parquet
  daily/symbol=NVDA/year=2026/part-....parquet   (sin ticker en el nombre del archivo)

Se ignora cualquier ruta bajo ``_delta_log`` (metadatos Delta, no datos OHLC).

Subdirectorio bajo data/lake (mismo layout Hive/Delta en las cuatro ramas):
  - daily/     → 1d o timeframe explícito ``daily``
  - intraday/  → 1m,5m,15m,30m,1h… o explícito ``intraday``
  - gold/      → 1w, 1M (mes), u explícito ``gold``
  - moc/       → timeframe ``moc`` (order flow / métricas; OHLC relajado: un solo precio → o=h=l=c)

Dependencia: duckdb (en el VPS usar un venv; PEP 668 en Debian/Ubuntu bloquea pip --user en el Python del sistema).

  En el VPS: /home/capadonna/projects/Capadonna-Driller/.venv/bin/pip install duckdb

Copiar al VPS, p. ej.:
  scp scripts/capadonna/export_lake_ohlcv.py capadonna@HOST:~/projects/Capadonna-Driller/scripts/
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


def _lake_root() -> Path:
    raw = (os.environ.get("CAPADONNA_LAKE_DATA_ROOT") or "").strip()
    if raw:
        return Path(os.path.expanduser(raw)).resolve()
    return Path(os.path.expanduser("~/projects/Capadonna-Driller/data/lake")).resolve()


def _subdir_for_timeframe(timeframe: str) -> str:
    tf = (timeframe or "1d").strip()
    tfl = tf.lower()
    if tf == "1M":
        return "gold"
    if tfl == "1w":
        return "gold"
    if tfl == "1d":
        return "daily"
    if tfl in ("1m", "2m", "3m", "5m", "10m", "15m", "30m", "1h", "2h", "4h", "60m"):
        return "intraday"
    return "gold"


def _is_under_delta_log(path: Path) -> bool:
    return any(part == "_delta_log" for part in path.parts)


def _hive_partition_matches_ticker(path: Path, ticker: str) -> bool:
    """True si algún segmento del path es symbol=TICKER o ticker=TICKER (Hive)."""
    want = ticker.strip().upper()
    for part in path.parts:
        low = part.lower()
        if low.startswith("symbol="):
            val = part.split("=", 1)[-1].strip().upper()
            if val == want:
                return True
        if low.startswith("ticker="):
            val = part.split("=", 1)[-1].strip().upper()
            if val == want:
                return True
    return False


def _filename_suggests_ticker(path: Path, ticker: str) -> bool:
    t = ticker.strip().upper()
    return t in path.stem.upper() or t in path.name.upper()


def _path_claims_ticker(path: Path, ticker: str) -> bool:
    """El fichero pertenece al ticker por partición Hive o por nombre (p. ej. CCJ_daily.parquet)."""
    return _hive_partition_matches_ticker(path, ticker) or _filename_suggests_ticker(path, ticker)


def _parquet_candidates(root: Path, ticker: str) -> list[Path]:
    if not root.is_dir():
        return []
    out: list[Path] = []
    for p in root.rglob("*.parquet"):
        if not p.is_file() or _is_under_delta_log(p):
            continue
        if _path_claims_ticker(p, ticker):
            out.append(p)
    return sorted(out)


def _parquet_fallback_all_in_subdir(root: Path, *, max_files: int) -> list[Path]:
    """Si no hubo match por símbolo/nombre, leer Parquet del subárbol y filtrar por columna symbol/ticker."""
    if not root.is_dir():
        return []
    out: list[Path] = []
    for p in sorted(root.rglob("*.parquet")):
        if not p.is_file() or _is_under_delta_log(p):
            continue
        out.append(p)
        if len(out) >= max_files:
            break
    return out


def _pick_col(names: list[str], *candidates: str) -> str | None:
    lower_map = {n.lower(): n for n in names}
    for c in candidates:
        if c.lower() in lower_map:
            return lower_map[c.lower()]
    return None


def _resolve_ohlc_columns(
    col_names: list[str],
    *,
    subdir: str,
) -> tuple[str | None, str | None, str | None, str | None, str | None, str | None] | None:
    """
    Resuelve columnas timestamp + OHLC (+ volumen opcional).
    En moc/ a menudo no hay vela completa: se usa close/price/last/mid para rellenar o,h,l,c.
    """
    ts_col = _pick_col(
        col_names,
        "timestamp",
        "ts",
        "datetime",
        "date",
        "time",
        "bar_time",
        "open_time",
        "event_time",
    )
    o_col = _pick_col(col_names, "open", "o")
    h_col = _pick_col(col_names, "high", "h")
    l_col = _pick_col(col_names, "low", "l")
    c_col = _pick_col(col_names, "close", "c", "price", "last", "mid", "mark", "px")
    v_col = _pick_col(col_names, "volume", "vol", "v", "size", "qty", "quantity")

    relax = subdir == "moc"
    if relax and c_col and (not o_col or not h_col or not l_col):
        px = c_col
        o_col = o_col or px
        h_col = h_col or px
        l_col = l_col or px
        c_col = c_col or px

    if not ts_col or not o_col or not h_col or not l_col or not c_col:
        return None
    return ts_col, o_col, h_col, l_col, c_col, v_col


def _to_float(x: Any) -> float | None:
    if x is None:
        return None
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def _parse_ts(val: Any) -> datetime | None:
    if val is None:
        return None
    if isinstance(val, datetime):
        return val if val.tzinfo else val.replace(tzinfo=timezone.utc)
    if isinstance(val, (int, float)):
        x = float(val)
        if x > 1e12:
            x /= 1000.0
        try:
            return datetime.fromtimestamp(x, tz=timezone.utc)
        except (OSError, ValueError, OverflowError):
            return None
    s = str(val).strip()
    if not s:
        return None
    s = s.replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(s)
    except ValueError:
        pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(s[:19], fmt).replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    return None


def _emit(bars: list[dict[str, Any]], *, note: str | None = None) -> None:
    payload: dict[str, Any] = {"bars": bars}
    if note:
        payload["message"] = note
    print(json.dumps(payload, ensure_ascii=False))
    sys.exit(0)


def main() -> None:
    if len(sys.argv) < 4:
        print(
            json.dumps(
                {"bars": [], "message": "Uso: export_lake_ohlcv.py TICKER TIMEFRAME LOOKBACK_DAYS"},
                ensure_ascii=False,
            )
        )
        sys.exit(0)

    ticker = sys.argv[1].strip().upper()
    timeframe = sys.argv[2].strip()
    try:
        lookback_days = max(1, min(int(sys.argv[3]), 4000))
    except ValueError:
        lookback_days = 90

    try:
        import duckdb  # noqa: PLC0415
    except ImportError:
        print(
            json.dumps(
                {
                    "bars": [],
                    "message": "Falta duckdb: en el VPS — /home/capadonna/projects/Capadonna-Driller/.venv/bin/pip install duckdb; CAPADONNA_REMOTE_OHLC_CMD debe usar …/.venv/bin/python (rutas absolutas del VPS).",
                },
                ensure_ascii=False,
            )
        )
        sys.exit(0)

    lake = _lake_root()
    sub = _subdir_for_timeframe(timeframe)
    subroot = lake / sub
    files = _parquet_candidates(subroot, ticker)
    scan_mode = "hive_nombre"
    if not files:
        files = _parquet_fallback_all_in_subdir(subroot, max_files=400)
        scan_mode = "amplio_por_columna"
    if not files:
        _emit(
            [],
            note=f"Sin archivos .parquet bajo {subroot} (subcarpeta {sub!r}, lake {lake})",
        )

    con = duckdb.connect(database=":memory:")
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)

    all_bars: list[dict[str, Any]] = []
    errors: list[str] = []

    for path in files[:300]:
        try:
            cur = con.execute("SELECT * FROM read_parquet(?)", [str(path)])
            desc = cur.description or ()
            col_names = [d[0] for d in desc]
            rows = cur.fetchall()
        except Exception as e:
            errors.append(f"{path.name}: {e}")
            continue

        sym_col = _pick_col(col_names, "symbol", "ticker", "sym")
        resolved = _resolve_ohlc_columns(col_names, subdir=sub)
        if not resolved:
            errors.append(f"{path.name}: faltan columnas timestamp/OHLC (moc: hace falta precio o close)")
            continue
        ts_col, o_col, h_col, l_col, c_col, v_col = resolved

        path_pins = _path_claims_ticker(path, ticker)
        if scan_mode == "amplio_por_columna" and not path_pins and not sym_col:
            continue

        idx = {n: i for i, n in enumerate(col_names)}
        for row in rows:
            if sym_col:
                cell = row[idx[sym_col]]
                sym = str(cell).strip().upper() if cell is not None else ""
                if sym:
                    if sym != ticker:
                        continue
                elif not path_pins:
                    continue
            elif not path_pins:
                continue
            ts_raw = row[idx[ts_col]]
            dt = _parse_ts(ts_raw)
            if dt is None:
                continue
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt < cutoff:
                continue
            o = _to_float(row[idx[o_col]])
            h = _to_float(row[idx[h_col]])
            l = _to_float(row[idx[l_col]])
            c = _to_float(row[idx[c_col]])
            if o is None or h is None or l is None or c is None:
                continue
            vol = 0.0
            if v_col:
                vol = _to_float(row[idx[v_col]]) or 0.0
            all_bars.append(
                {
                    "ticker": ticker,
                    "timestamp": dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": vol,
                }
            )

    all_bars.sort(key=lambda b: b["timestamp"])

    note = None
    if errors and not all_bars:
        note = "; ".join(errors[:3])
    elif errors:
        note = f"Advertencias: {'; '.join(errors[:2])}"
    if scan_mode == "amplio_por_columna" and all_bars:
        note = (note + "; " if note else "") + "escaneo amplio (columna symbol/ticker en filas)"

    _emit(all_bars, note=note)


if __name__ == "__main__":
    main()
