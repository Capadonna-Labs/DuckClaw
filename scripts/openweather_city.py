#!/usr/bin/env python3
"""
Consulta el clima actual de una ciudad con la API Current Weather de OpenWeatherMap.

Requisitos:
  - Crea una clave en https://openweathermap.org/api (plan gratuito).
  - Exporta la variable de entorno ``OPENWEATHER_API_KEY`` (o pásala con ``--api-key``).

Ejemplos::

  export OPENWEATHER_API_KEY=tu_clave
  uv run python scripts/openweather_city.py "Bogotá"
  uv run python scripts/openweather_city.py London --units imperial --lang en
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request


API_URL = "https://api.openweathermap.org/data/2.5/weather"

def fetch_weather(
    *,
    city: str,
    api_key: str,
    units: str,
    lang: str,
) -> dict:
    params = urllib.parse.urlencode(
        {
            "q": city,
            "appid": api_key,
            "units": units,
            "lang": lang,
        }
    )
    url = f"{API_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "duckclaw-openweather-cli/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode("utf-8")
    return json.loads(body)


def format_summary(data: dict) -> str:
    name = data.get("name", "?")
    country = (data.get("sys") or {}).get("country", "")
    main = data.get("main") or {}
    weather = (data.get("weather") or [{}])[0]
    desc = weather.get("description", "")
    temp = main.get("temp")
    feels = main.get("feels_like")
    humidity = main.get("humidity")
    wind = (data.get("wind") or {}).get("speed")
    lines = [
        f"{name}{', ' + country if country else ''}",
        f"Condición: {desc}",
        f"Temperatura: {temp} ° (sensación {feels})",
        f"Humedad: {humidity}%",
        f"Viento: {wind}",
    ]
    return "\n".join(str(x) for x in lines if x is not None)


def main() -> int:
    parser = argparse.ArgumentParser(description="Clima actual (OpenWeatherMap)")
    parser.add_argument("city", help="Nombre de la ciudad (ej. Medellín, Paris)")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("OPENWEATHER_API_KEY", ""),
        help="API key (por defecto: env OPENWEATHER_API_KEY)",
    )
    parser.add_argument(
        "--units",
        choices=("metric", "imperial", "standard"),
        default="metric",
        help="Unidades: metric (°C), imperial (°F), standard (K)",
    )
    parser.add_argument("--lang", default="es", help="Código de idioma (es, en, …)")
    parser.add_argument(
        "--json",
        action="store_true",
        help="Imprime la respuesta cruda JSON en stdout",
    )
    args = parser.parse_args()

    _env_raw = os.environ.get("OPENWEATHER_API_KEY", "")
    key = (args.api_key or "").strip()
    if not key:
        print(
            "Falta la API key. Define OPENWEATHER_API_KEY o usa --api-key.",
            file=sys.stderr,
        )
        return 1

    try:
        data = fetch_weather(
            city=args.city.strip(),
            api_key=key,
            units=args.units,
            lang=args.lang,
        )
    except urllib.error.HTTPError as e:
        try:
            err_body = e.read().decode("utf-8")
            detail = json.loads(err_body)
            msg = detail.get("message", err_body)
        except (json.JSONDecodeError, OSError):
            msg = e.reason
        print(f"Error HTTP {e.code}: {msg}", file=sys.stderr)
        if e.code == 401:
            print(
                "Pista: Tu petición ya lleva un appid bien formado; un 401 en cuentas nuevas "
                "casi siempre es del lado de OpenWeatherMap: (1) abre el correo y pulsa el "
                "enlace de confirmación de cuenta; (2) espera la activación de la clave — la FAQ "
                "oficial indica que puede tardar hasta unas horas tras el registro verificado. "
                "Panel: https://home.openweathermap.org/api_keys — "
                "https://openweathermap.org/faq#error401",
                file=sys.stderr,
            )
        return 2
    except urllib.error.URLError as e:
        print(f"Error de red: {e.reason}", file=sys.stderr)
        return 3
        
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(format_summary(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())