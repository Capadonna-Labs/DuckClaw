"""
Plantilla — ML4T `DataQualityReport` desde filas DuckClaw `quant_core.ohlcv_data` (sandbox).

Uso: copiar como `code` en `execute_sandbox_script`; sustituir `OHLC_ROWS_BY_SYMBOL`,
`BAR_FREQUENCY`, `DATA_SOURCE`. No construir `DataQualityReport` con dict simple: ML4T
exige `metrics` tipado como `DataQualityMetrics`, `date_range` tupla `(datetime, datetime)`
UTC, y campos obligatorios `symbol`, `source`, `frequency`, `is_production_ready`.

Sin ml4t-data ni red en sandbox.
"""
from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd
from ml4t.diagnostic.integration import (
    AnomalyType,
    DataAnomaly,
    DataQualityMetrics,
    DataQualityReport,
    Severity,
)

# --------------------------------------------------------------------
# Inputs (rellenar en runtime — evidencia misma ingestión/read_sql turno)
# --------------------------------------------------------------------
OHLC_ROWS_BY_SYMBOL: dict[str, list[dict[str, object]]] = {}

BAR_FREQUENCY: str = "1h"

DATA_SOURCE: str = "duckclaw_ibkr_http"


def _utc_dt(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _df_for_symbol(rows: list[dict[str, object]]) -> pd.DataFrame:
    if not rows:
        raise ValueError("empty rows")
    df = pd.DataFrame(rows).copy()
    for col in ("ticker", "timestamp", "open", "high", "low", "close", "volume"):
        if col not in df.columns:
            df[col] = "" if col == "ticker" else float("nan")
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    for col in ("open", "high", "low", "close", "volume"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
    if df.empty:
        raise ValueError("no valid timestamps")
    return df.reset_index(drop=True)


def _build_anomalies(symbol: str, df: pd.DataFrame) -> list[DataAnomaly]:
    out: list[DataAnomaly] = []
    for i in range(len(df)):
        ts_pyd = _utc_dt(df["timestamp"].iloc[i].to_pydatetime())
        oh = df["open"].iloc[i]
        hil = df["high"].iloc[i]
        lw = df["low"].iloc[i]
        cl = df["close"].iloc[i]
        if any(pd.isna(x) for x in (oh, hil, lw, cl)):
            continue
        fv = (float(oh), float(hil), float(lw), float(cl))
        if fv[1] < fv[2]:
            out.append(
                DataAnomaly(
                    anomaly_type=AnomalyType.OHLC_VIOLATION,
                    severity=Severity.ERROR,
                    timestamp=ts_pyd,
                    symbol=symbol,
                    description=f"high < low (row={i})",
                    value=fv[1],
                )
            )
        if min(fv) <= 0:
            out.append(
                DataAnomaly(
                    anomaly_type=AnomalyType.NEGATIVE_PRICE,
                    severity=Severity.CRITICAL,
                    timestamp=ts_pyd,
                    symbol=symbol,
                    description="non-positive OHLC bar",
                    value=fv[-1],
                )
            )

    dup_buckets = sorted({pd.Timestamp(t) for t in df.loc[df["timestamp"].duplicated(keep=False), "timestamp"].unique()})
    for t in dup_buckets[:40]:
        out.append(
            DataAnomaly(
                anomaly_type=AnomalyType.DUPLICATE_TIMESTAMP,
                severity=Severity.WARNING,
                timestamp=_utc_dt(t.to_pydatetime()),
                symbol=symbol,
                description=f"duplicate bar timestamp ({t.isoformat()})",
                value=None,
            )
        )

    return out[:250]


def _timeliness_minutes(now: datetime, df: pd.DataFrame) -> float:
    last = pd.Timestamp(df["timestamp"].iloc[-1]).tz_convert(UTC).to_pydatetime(warn=False)
    delta = now - _utc_dt(last)
    return max(delta.total_seconds() / 60.0, 0.0)


def report_for(symbol: str, rows: list[dict[str, object]]) -> dict[str, object]:
    now = datetime.now(tz=UTC)
    df = _df_for_symbol(rows)
    tmin = _utc_dt(df["timestamp"].iloc[0].to_pydatetime())
    tmax = _utc_dt(df["timestamp"].iloc[-1].to_pydatetime())
    n = int(df.shape[0])

    anomalies = _build_anomalies(symbol, df)
    dup_mask_any = df["timestamp"].duplicated(keep=False)
    dup_rate = float(dup_mask_any.mean()) if n else 1.0
    hl_bad = float((df["high"].astype(float) < df["low"].astype(float)).mean())

    cols_ok = (
        (~df[["open", "high", "low", "close"]].isna()).all(axis=1)
        & (df[["open", "high", "low", "close"]].astype(float) > 0).all(axis=1)
        & (~df["timestamp"].duplicated(keep=False))
    )
    row_ok_frac = float(cols_ok.mean()) if n else 0.0

    completeness = max(0.0, min(1.0, row_ok_frac * (1.0 - min(hl_bad, 0.5))))

    violations = hl_bad + dup_rate
    consistency = max(0.0, min(1.0, 1.0 - min(1.0, violations)))

    acc = consistency * completeness
    nc = sum(1 for a in anomalies if a.severity == Severity.CRITICAL)
    ne = sum(1 for a in anomalies if a.severity == Severity.ERROR)
    nw = sum(1 for a in anomalies if a.severity == Severity.WARNING)

    metrics = DataQualityMetrics(
        completeness=completeness,
        timeliness=_timeliness_minutes(now, df),
        accuracy_score=acc,
        consistency_score=consistency,
        n_records=n,
        n_anomalies=len(anomalies),
        n_critical=nc,
        n_error=ne,
        n_warning=nw,
    )

    recs: list[str] = []
    if completeness < 0.95:
        recs.append("Revisar gaps o filas incompletas en OHLC antes de producir estrategias.")
    if nw + ne > 0:
        recs.append("Inspeccionar timestamps duplicados y violaciones OHLC antes de usar en ML4T backtest.")

    prod = completeness >= 0.95 and nc == 0 and ne <= 2

    rpt = DataQualityReport(
        symbol=symbol,
        source=DATA_SOURCE,
        date_range=(tmin, tmax),
        frequency=BAR_FREQUENCY,
        metrics=metrics,
        anomalies=anomalies,
        recommendations=recs,
        is_production_ready=bool(prod),
    )
    return rpt.model_dump(mode="json")


def main() -> None:
    if not OHLC_ROWS_BY_SYMBOL:
        raise SystemExit(
            json.dumps(
                {"ok": False, "error": "fill OHLC_ROWS_BY_SYMBOL from read_sql OHLC rows"},
                ensure_ascii=False,
            )
        )
    out: dict[str, object | list] = {"ok": True, "reports": []}
    for sym, rows in OHLC_ROWS_BY_SYMBOL.items():
        try:
            out["reports"].append(report_for(str(sym).upper(), list(rows)))  # type: ignore[list-item]
        except Exception as e:  # noqa: BLE001 — diagnóstico sandbox
            out["reports"].append({"symbol": sym, "error": str(e)})  # type: ignore[list-item]
    print(json.dumps(out, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
