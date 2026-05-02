#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Descarga PM2.5 horario desde Open-Meteo Air Quality.")
    parser.add_argument("--start-date", required=True, help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default="data/raw/openmeteo", help="Directorio de salida")
    parser.add_argument("--lat", type=float, default=6.2442, help="Latitud (Medellín por defecto)")
    parser.add_argument("--lon", type=float, default=-75.5812, help="Longitud (Medellín por defecto)")
    parser.add_argument("--zone", default="Medellín", help="Zona para salida")
    parser.add_argument("--station", default="Open-Meteo Grid", help="Nombre estación/fuente")
    parser.add_argument(
        "--cities-profile",
        default="",
        help="Perfil de ciudades (colombia_main) para descargar varias zonas en una corrida.",
    )
    return parser.parse_args()


def validate_date(value: str) -> str:
    datetime.strptime(value, "%Y-%m-%d")
    return value


def fetch_openmeteo(start_date: str, end_date: str, lat: float, lon: float, zone: str, station: str) -> pd.DataFrame:
    url = "https://air-quality-api.open-meteo.com/v1/air-quality"
    params = {
        "latitude": lat,
        "longitude": lon,
        "hourly": "pm2_5",
        "start_date": start_date,
        "end_date": end_date,
        "timezone": "America/Bogota",
    }
    resp = requests.get(url, params=params, timeout=45)
    resp.raise_for_status()
    payload = resp.json()
    hourly = payload.get("hourly", {}) if isinstance(payload, dict) else {}
    times = hourly.get("time", [])
    pm = hourly.get("pm2_5", [])
    df = pd.DataFrame({"datetime": times, "pm25": pm})
    if df.empty:
        return pd.DataFrame(columns=["date", "zone", "station", "pm25", "source", "lat", "lon"])
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    out = pd.DataFrame(
        {
            "date": df["datetime"].dt.date.astype("string"),
            "zone": zone,
            "station": station,
            "pm25": pd.to_numeric(df["pm25"], errors="coerce"),
            "source": "Open-Meteo",
            "lat": lat,
            "lon": lon,
        }
    ).dropna(subset=["date", "pm25"])
    return out


def fetch_openmeteo_multi(start_date: str, end_date: str, profile: str, station: str) -> pd.DataFrame:
    profiles: dict[str, list[tuple[str, float, float]]] = {
        "colombia_main": [
            ("Bogotá", 4.7110, -74.0721),
            ("Medellín", 6.2442, -75.5812),
            ("Cali", 3.4516, -76.5320),
            ("Barranquilla", 10.9685, -74.7813),
            ("Cartagena", 10.3910, -75.4794),
            ("Bucaramanga", 7.1193, -73.1227),
            ("Pereira", 4.8143, -75.6946),
            ("Manizales", 5.0703, -75.5138),
            ("Cúcuta", 7.8939, -72.5078),
        ]
    }
    cities = profiles.get(profile, [])
    if not cities:
        raise ValueError(f"Perfil de ciudades no soportado: {profile}")
    frames: list[pd.DataFrame] = []
    for city, lat, lon in cities:
        frame = fetch_openmeteo(start_date, end_date, lat, lon, city, station)
        frames.append(frame)
    out = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["date", "zone", "station", "pm25", "source", "lat", "lon"]
    )
    return out


def main() -> int:
    args = parse_args()
    start = validate_date(args.start_date)
    end = validate_date(args.end_date)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    if args.cities_profile:
        df = fetch_openmeteo_multi(start, end, args.cities_profile, args.station)
    else:
        df = fetch_openmeteo(start, end, args.lat, args.lon, args.zone, args.station)
    stem = f"openmeteo_pm25_{start}_{end}"
    df.to_csv(output_dir / f"{stem}.csv", index=False)
    df.to_parquet(output_dir / f"{stem}.parquet", index=False)
    print(f"rows={len(df)} file={output_dir / f'{stem}.parquet'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
