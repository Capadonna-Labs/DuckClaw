#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import unicodedata
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
import requests

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Descarga PM2.5 desde OpenAQ v3.")
    parser.add_argument("--start-date", required=True, help="Fecha inicio (YYYY-MM-DD)")
    parser.add_argument("--end-date", required=True, help="Fecha fin (YYYY-MM-DD)")
    parser.add_argument("--output-dir", default="data/raw/openaq", help="Directorio de salida")
    parser.add_argument("--city", default="Medellín", help="Ciudad objetivo")
    parser.add_argument("--country", default="CO", help="País objetivo (ISO2)")
    parser.add_argument("--api-key", default="", help="OpenAQ API key opcional.")
    parser.add_argument(
        "--base-url",
        default="https://api.openaq.org/v3",
        help="Base URL OpenAQ v3.",
    )
    parser.add_argument("--limit", type=int, default=1000, help="Límite por página para API v3")
    parser.add_argument("--max-sensors", type=int, default=20, help="Máximo sensores PM2.5 a consultar")
    return parser.parse_args()


def validate_date(value: str) -> str:
    datetime.strptime(value, "%Y-%m-%d")
    return value


def _normalize_text(value: str) -> str:
    txt = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    return txt.strip().lower()


def _load_api_key(cli_key: str) -> str:
    if cli_key.strip():
        return cli_key.strip()
    env_key = (os.getenv("OPENAQ_API_KEY") or "").strip()
    if env_key:
        return env_key
    env_file = Path(".env")
    if not env_file.exists():
        return ""
    for line in env_file.read_text(encoding="utf-8").splitlines():
        if not line or line.lstrip().startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == "OPENAQ_API_KEY":
            return value.strip().strip('"').strip("'")
    return ""


def _paginate_get(
    url: str, *, headers: dict[str, str], params: dict[str, Any], max_pages: int = 20
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    page = 1
    while page <= max_pages:
        run_params = {**params, "page": page}
        resp = requests.get(url, params=run_params, headers=headers, timeout=45)
        resp.raise_for_status()
        payload = resp.json() if resp.content else {}
        rows = payload.get("results", []) if isinstance(payload, dict) else []
        if not rows:
            break
        out.extend(rows)
        meta = payload.get("meta", {}) if isinstance(payload, dict) else {}
        found = meta.get("found")
        limit = meta.get("limit", params.get("limit", 100))
        if isinstance(found, int) and found <= len(out):
            break
        if len(rows) < int(limit):
            break
        page += 1
    return out


def fetch_openaq(
    *,
    base_url: str,
    api_key: str,
    city: str,
    country: str,
    start_date: str,
    end_date: str,
    limit: int,
    max_sensors: int,
) -> pd.DataFrame:
    if not api_key:
        print("warning=No hay OPENAQ_API_KEY disponible (env, .env o --api-key).")
        return pd.DataFrame(columns=["date", "zone", "station", "pm25", "source", "lat", "lon"])
    headers = {"X-API-Key": api_key}
    locations = _paginate_get(
        f"{base_url.rstrip('/')}/locations",
        headers=headers,
        params={
            "iso": country.upper(),
            "parameters_id": 2,  # PM2.5
            "limit": limit,
            "order_by": "id",
            "sort_order": "asc",
        },
    )
    if not locations:
        return pd.DataFrame(columns=["date", "zone", "station", "pm25", "source", "lat", "lon"])

    city_norm = _normalize_text(city)
    filtered_locs = []
    for loc in locations:
        locality = str(loc.get("locality") or "")
        name = str(loc.get("name") or "")
        if city_norm in _normalize_text(locality) or city_norm in _normalize_text(name):
            filtered_locs.append(loc)
    if not filtered_locs:
        print(f"warning=No hubo match exacto para city={city}; usando locations PM2.5 del país {country}.")
        filtered_locs = locations

    sensors: list[dict[str, Any]] = []
    for loc in filtered_locs:
        loc_id = loc.get("id")
        for sensor in loc.get("sensors") or []:
            param = sensor.get("parameter") or {}
            pname = str(param.get("name") or "").lower().replace(".", "").replace("_", "")
            pid = param.get("id")
            if pid == 2 or pname == "pm25":
                sensors.append(
                    {
                        "sensor_id": sensor.get("id"),
                        "location_name": loc.get("name") or loc.get("locality") or city,
                        "zone": loc.get("locality") or loc.get("name") or city,
                        "lat": (loc.get("coordinates") or {}).get("latitude"),
                        "lon": (loc.get("coordinates") or {}).get("longitude"),
                        "location_id": loc_id,
                    }
                )

    uniq: dict[int, dict[str, Any]] = {}
    for s in sensors:
        sid = s.get("sensor_id")
        if isinstance(sid, int):
            uniq[sid] = s
    sensors = list(uniq.values())[:max_sensors]

    all_rows: list[dict[str, Any]] = []
    per_sensor_counts: list[dict[str, Any]] = []
    for sensor in sensors:
        sid = sensor["sensor_id"]
        ms = _paginate_get(
            f"{base_url.rstrip('/')}/sensors/{sid}/measurements/daily",
            headers=headers,
            params={
                "datetime_from": start_date,
                "datetime_to": end_date,
                "limit": limit,
            },
        )
        per_sensor_counts.append({"sensor_id": sid, "rows": len(ms)})
        for row in ms:
            period = row.get("period") or {}
            dt_from = (period.get("datetimeFrom") or {}).get("utc")
            if not dt_from:
                continue
            all_rows.append(
                {
                    "date": dt_from,
                    "zone": sensor["zone"],
                    "station": sensor["location_name"],
                    "pm25": row.get("value"),
                    "source": "OpenAQ",
                    "lat": sensor["lat"],
                    "lon": sensor["lon"],
                }
            )

    if not all_rows:
        return pd.DataFrame(columns=["date", "zone", "station", "pm25", "source", "lat", "lon"])
    normalized = pd.DataFrame(all_rows)
    normalized["date"] = pd.to_datetime(normalized["date"], errors="coerce").dt.date.astype("string")
    normalized["pm25"] = pd.to_numeric(normalized["pm25"], errors="coerce")
    return normalized.dropna(subset=["date", "pm25"])


def main() -> int:
    args = parse_args()
    start = validate_date(args.start_date)
    end = validate_date(args.end_date)
    api_key = _load_api_key(args.api_key)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    df = fetch_openaq(
        base_url=args.base_url,
        api_key=api_key,
        city=args.city,
        country=args.country,
        start_date=start,
        end_date=end,
        limit=args.limit,
        max_sensors=args.max_sensors,
    )
    stem = f"openaq_pm25_{start}_{end}"
    df.to_csv(output_dir / f"{stem}.csv", index=False)
    df.to_parquet(output_dir / f"{stem}.parquet", index=False)
    print(f"rows={len(df)} file={output_dir / f'{stem}.parquet'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
