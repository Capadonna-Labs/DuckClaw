#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests


DEFAULT_SIATA_URL = "https://siata.gov.co/EntregaData1/Datos_SIATA_Aire_pm25.json"
def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Descarga PM2.5 desde SIATA (EntregaData1).")
    parser.add_argument("--start-date", required=True, help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default="data/raw/siata", help="Directorio de salida")
    parser.add_argument("--url", default=DEFAULT_SIATA_URL, help="URL JSON SIATA")
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


def fetch_siata(url: str, start_date: str, end_date: str, zone_default: str) -> pd.DataFrame:
    response = requests.get(url, timeout=45)
    response.raise_for_status()
    payload = response.json()
    rows = payload if isinstance(payload, list) else payload.get("data", [])
    exploded_rows: list[dict] = []
    for station in rows:
        if not isinstance(station, dict):
            continue
        station_name = station.get("nombre") or station.get("nombreCorto") or "siata_station"
        zone_name = station.get("municipio") or station.get("zona") or zone_default
        lat = station.get("latitud")
        lon = station.get("longitud")
        for item in station.get("datos") or []:
            if not isinstance(item, dict):
                continue
            exploded_rows.append(
                {
                    "date": item.get("fecha"),
                    "pm25": item.get("valor"),
                    "station": station_name,
                    "zone": zone_name,
                    "lat": lat,
                    "lon": lon,
                }
            )

    normalized = pd.json_normalize(exploded_rows)
    if normalized.empty:
        return pd.DataFrame(columns=["date", "zone", "station", "pm25", "source", "lat", "lon"])

    out = pd.DataFrame(
        {
            "date": pd.to_datetime(normalized["date"], errors="coerce"),
            "zone": normalized["zone"].astype("string"),
            "station": normalized["station"].astype("string"),
            "pm25": pd.to_numeric(normalized["pm25"], errors="coerce"),
            "source": "SIATA",
            "lat": pd.to_numeric(normalized["lat"], errors="coerce"),
            "lon": pd.to_numeric(normalized["lon"], errors="coerce"),
        }
    )
    out["date"] = out["date"].dt.date
    out = out.dropna(subset=["date", "pm25"])
    out = out[out["pm25"] >= 0].copy()  # SIATA usa negativos como sentinel de missing/calidad.
    mask = (out["date"] >= pd.to_datetime(start_date).date()) & (out["date"] <= pd.to_datetime(end_date).date())
    filtered = out.loc[mask].copy()
    return filtered


def main() -> int:
    args = parse_args()
    start = validate_date(args.start_date)
    end = validate_date(args.end_date)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    df = fetch_siata(args.url, start, end, args.zone_default)
    stem = f"siata_pm25_{start}_{end}"
    df.to_csv(output_dir / f"{stem}.csv", index=False)
    df.to_parquet(output_dir / f"{stem}.parquet", index=False)
    print(f"rows={len(df)} file={output_dir / f'{stem}.parquet'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
