#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path

import pandas as pd
import requests


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Descarga variables ambientales complementarias (IDEAM o fuente compatible JSON)."
    )
    parser.add_argument("--start-date", required=True, help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default="data/raw/ideam", help="Directorio de salida")
    parser.add_argument(
        "--url",
        default=os.getenv("IDEAM_ENV_DATA_URL", "").strip(),
        help="URL JSON IDEAM/fuente compatible. Si no se define, el script falla con mensaje claro.",
    )
    parser.add_argument("--zone-default", default="Valle de Aburrá", help="Zona por defecto")
    return parser.parse_args()


def validate_date(value: str) -> str:
    datetime.strptime(value, "%Y-%m-%d")
    return value


def _pick_column(columns: list[str], candidates: list[str]) -> str | None:
    lower = {c.lower(): c for c in columns}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    return None


def fetch_ideam(url: str, start_date: str, end_date: str, zone_default: str) -> pd.DataFrame:
    response = requests.get(url, timeout=45)
    response.raise_for_status()
    payload = response.json()
    rows = payload if isinstance(payload, list) else payload.get("data", [])
    normalized = pd.json_normalize(rows)
    if normalized.empty:
        return pd.DataFrame(columns=["date", "zone", "temperature_c", "humidity_pct", "rain_mm", "source"])

    date_col = _pick_column(list(normalized.columns), ["fecha", "date", "datetime", "timestamp", "fecha_hora"])
    zone_col = _pick_column(list(normalized.columns), ["municipio", "zone", "zona", "city"])
    temp_col = _pick_column(list(normalized.columns), ["temp", "temperature", "temperatura"])
    hum_col = _pick_column(list(normalized.columns), ["humidity", "humedad"])
    rain_col = _pick_column(list(normalized.columns), ["rain", "precipitation", "lluvia", "rain_mm"])

    if date_col is None:
        raise ValueError(f"No se detectó columna de fecha en dataset IDEAM. Columnas: {list(normalized.columns)}")

    out = pd.DataFrame(
        {
            "date": pd.to_datetime(normalized[date_col], errors="coerce").dt.date,
            "zone": normalized[zone_col].astype("string") if zone_col else zone_default,
            "temperature_c": pd.to_numeric(normalized[temp_col], errors="coerce") if temp_col else pd.NA,
            "humidity_pct": pd.to_numeric(normalized[hum_col], errors="coerce") if hum_col else pd.NA,
            "rain_mm": pd.to_numeric(normalized[rain_col], errors="coerce") if rain_col else pd.NA,
            "source": "IDEAM",
        }
    )
    out = out.dropna(subset=["date"])
    mask = (out["date"] >= pd.to_datetime(start_date).date()) & (out["date"] <= pd.to_datetime(end_date).date())
    return out.loc[mask].copy()


def main() -> int:
    args = parse_args()
    start = validate_date(args.start_date)
    end = validate_date(args.end_date)
    if not args.url:
        raise SystemExit(
            "Falta URL para IDEAM. Define --url o la variable IDEAM_ENV_DATA_URL con un endpoint JSON compatible."
        )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    df = fetch_ideam(args.url, start, end, args.zone_default)
    stem = f"ideam_env_{start}_{end}"
    df.to_csv(output_dir / f"{stem}.csv", index=False)
    df.to_parquet(output_dir / f"{stem}.parquet", index=False)
    print(f"rows={len(df)} file={output_dir / f'{stem}.parquet'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
