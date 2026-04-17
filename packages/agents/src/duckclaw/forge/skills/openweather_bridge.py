"""
OpenWeather Bridge - clima actual por ciudad con enriquecimiento opcional.

Requiere:
- OPENWEATHER_API_KEY
Opcional:
- TAVILY_API_KEY (si se habilita contexto adicional)
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, Optional

from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)

_OPENWEATHER_API_URL = "https://api.openweathermap.org/data/2.5/weather"
_OPENWEATHER_KEY_ENV = "OPENWEATHER_API_KEY"
_TAVILY_KEY_ENV = "TAVILY_API_KEY"
_DEBUG_LOG_PATH = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-07d446.log"


def _agent_debug_log(
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any],
    *,
    run_id: str = "baseline",
) -> None:
    # #region agent log
    try:
        payload: dict[str, Any] = {
            "sessionId": "07d446",
            "runId": run_id,
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(datetime.now(timezone.utc).timestamp() * 1000),
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion


class OpenWeatherCurrentInput(BaseModel):
    city: str = Field(..., description="Ciudad a consultar (ej. Medellin, Bogota, London).")
    country: str | None = Field(
        default=None, description="Codigo de pais opcional para desambiguar (ej. CO, US, ES)."
    )
    units: str = Field(default="metric", description="metric | imperial | standard")
    lang: str = Field(default="es", description="Codigo de idioma (ej. es, en).")


def _sanitize_units(units: str | None, default_units: str = "metric") -> str:
    raw = (units or "").strip().lower()
    if raw in ("metric", "imperial", "standard"):
        return raw
    dflt = (default_units or "metric").strip().lower()
    return dflt if dflt in ("metric", "imperial", "standard") else "metric"


def _sanitize_lang(lang: str | None, default_lang: str = "es") -> str:
    raw = (lang or "").strip().lower()
    if raw:
        return raw
    dflt = (default_lang or "es").strip().lower()
    return dflt or "es"


def _fetch_openweather_current(*, city: str, country: str | None, units: str, lang: str) -> dict[str, Any]:
    api_key = (os.environ.get(_OPENWEATHER_KEY_ENV) or "").strip()
    # #region agent log
    _agent_debug_log(
        "H1",
        "openweather_bridge.py:_fetch_openweather_current",
        "api_key_presence",
        {
            "has_api_key": bool(api_key),
            "api_key_len": len(api_key),
            "city_len": len(city or ""),
            "country_present": bool((country or "").strip()),
            "units": units,
            "lang": lang,
        },
    )
    # #endregion
    if not api_key:
        return {
            "ok": False,
            "error": f"missing_api_key:{_OPENWEATHER_KEY_ENV}",
            "message": "Falta OPENWEATHER_API_KEY en el entorno del proceso.",
        }
    q = city.strip()
    if country and country.strip():
        q = f"{q},{country.strip()}"
    params = urllib.parse.urlencode({"q": q, "appid": api_key, "units": units, "lang": lang})
    url = f"{_OPENWEATHER_API_URL}?{params}"
    req = urllib.request.Request(url, headers={"User-Agent": "duckclaw-openweather-bridge/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
        # #region agent log
        _agent_debug_log(
            "H4",
            "openweather_bridge.py:_fetch_openweather_current",
            "openweather_http_ok",
            {
                "response_has_name": bool((payload or {}).get("name") if isinstance(payload, dict) else False),
                "response_has_weather": bool((payload or {}).get("weather") if isinstance(payload, dict) else False),
            },
        )
        # #endregion
        return {"ok": True, "payload": payload, "request_url": url}
    except urllib.error.HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")
        except Exception:
            body = ""
        detail = None
        if body:
            try:
                parsed = json.loads(body)
                detail = parsed.get("message") if isinstance(parsed, dict) else str(parsed)
            except Exception:
                detail = body[:500]
        return {
            "ok": False,
            "error": f"http_{exc.code}",
            "message": detail or str(exc.reason),
            "request_url": url,
        }
    except urllib.error.URLError as exc:
        return {
            "ok": False,
            "error": "network_error",
            "message": str(exc.reason),
            "request_url": url,
        }
    except (TimeoutError, json.JSONDecodeError, OSError) as exc:
        return {
            "ok": False,
            "error": "request_failed",
            "message": str(exc),
            "request_url": url,
        }


def _extract_weather_fields(payload: dict[str, Any], *, units: str, lang: str) -> dict[str, Any]:
    main = payload.get("main") or {}
    weather = (payload.get("weather") or [{}])[0]
    wind = payload.get("wind") or {}
    rain = payload.get("rain") or {}
    snow = payload.get("snow") or {}
    city = payload.get("name")
    country = (payload.get("sys") or {}).get("country")
    now_iso = datetime.now(timezone.utc).isoformat()
    return {
        "location": {"city": city, "country": country},
        "units": units,
        "lang": lang,
        "weather": {
            "condition": weather.get("main"),
            "description": weather.get("description"),
            "icon": weather.get("icon"),
        },
        "metrics": {
            "temp": main.get("temp"),
            "feels_like": main.get("feels_like"),
            "temp_min": main.get("temp_min"),
            "temp_max": main.get("temp_max"),
            "humidity": main.get("humidity"),
            "pressure": main.get("pressure"),
        },
        "wind": {"speed": wind.get("speed"), "deg": wind.get("deg"), "gust": wind.get("gust")},
        "precipitation": {"rain_1h": rain.get("1h"), "rain_3h": rain.get("3h"), "snow_1h": snow.get("1h")},
        "timestamp_unix": payload.get("dt"),
        "observed_at_utc": now_iso,
        "source": {"provider": "OpenWeather", "endpoint": "current_weather_v2.5"},
    }


def _should_add_context(weather_data: dict[str, Any]) -> bool:
    weather = weather_data.get("weather") or {}
    desc = str(weather.get("description") or "").lower()
    cond = str(weather.get("condition") or "").lower()
    rain = weather_data.get("precipitation") or {}
    rain_1h = rain.get("rain_1h")
    has_rain = isinstance(rain_1h, (int, float)) and float(rain_1h) > 0
    severe_tokens = ("rain", "storm", "thunder", "lluv", "torment", "flood", "inund")
    return has_rain or any(tok in desc or tok in cond for tok in severe_tokens)


def _tavily_context_notes(city: str, country: str | None, *, max_notes: int = 3) -> list[str]:
    try:
        from tavily import TavilyClient
    except ImportError:
        return []
    api_key = (os.environ.get(_TAVILY_KEY_ENV) or "").strip()
    if not api_key:
        return []
    place = f"{city}, {country}" if country else city
    query = (
        f"{place} lluvia accidentes inundaciones movilidad cierres vias alerta clima hoy "
        f"site:gov.co OR site:siata.gov.co OR site:medellin.gov.co"
    )
    try:
        client = TavilyClient(api_key=api_key)
        res = client.search(
            query=query,
            search_depth="advanced",
            include_answer=False,
            max_results=max_notes,
            include_raw_content=False,
            topic="general",
        )
        results = res.get("results", []) if isinstance(res, dict) else []
        notes: list[str] = []
        for item in results[:max_notes]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title") or "").strip()
            url = str(item.get("url") or "").strip()
            if title and url:
                notes.append(f"{title} ({url})")
        return notes
    except Exception as exc:
        _log.warning("openweather tavily context failed: %s", exc)
        return []


def _openweather_current_tool(
    openweather_config: Optional[dict] = None, research_config: Optional[dict] = None
) -> Optional[Any]:
    from langchain_core.tools import StructuredTool

    ow_cfg = openweather_config or {}
    if ow_cfg.get("enabled") is False:
        return None
    default_units = _sanitize_units(ow_cfg.get("default_units"), "metric")
    default_lang = _sanitize_lang(ow_cfg.get("default_lang"), "es")
    include_tavily_context = bool(ow_cfg.get("include_tavily_context", False))
    research_enabled = bool((research_config or {}).get("tavily_enabled", False))

    def _run(city: str, country: str | None = None, units: str = "metric", lang: str = "es") -> str:
        resolved_units = _sanitize_units(units, default_units)
        resolved_lang = _sanitize_lang(lang, default_lang)
        # #region agent log
        _agent_debug_log(
            "H3",
            "openweather_bridge.py:_openweather_current_tool/_run",
            "tool_invoke_inputs",
            {
                "city_len": len(city or ""),
                "country_present": bool((country or "").strip()),
                "resolved_units": resolved_units,
                "resolved_lang": resolved_lang,
            },
        )
        # #endregion
        fetched = _fetch_openweather_current(
            city=city,
            country=country,
            units=resolved_units,
            lang=resolved_lang,
        )
        if not fetched.get("ok"):
            return json.dumps(
                {
                    "ok": False,
                    "error": fetched.get("error"),
                    "message": fetched.get("message"),
                    "source": {"provider": "OpenWeather"},
                },
                ensure_ascii=False,
            )
        payload = fetched.get("payload")
        if not isinstance(payload, dict):
            return json.dumps(
                {
                    "ok": False,
                    "error": "invalid_payload",
                    "message": "OpenWeather devolvio un payload invalido.",
                    "source": {"provider": "OpenWeather"},
                },
                ensure_ascii=False,
            )
        data = _extract_weather_fields(payload, units=resolved_units, lang=resolved_lang)
        out: dict[str, Any] = {"ok": True, "data": data}
        if include_tavily_context and research_enabled and _should_add_context(data):
            out["context_notes"] = _tavily_context_notes(
                city=data["location"].get("city") or city,
                country=data["location"].get("country") or country,
            )
        return json.dumps(out, ensure_ascii=False)

    return StructuredTool.from_function(
        _run,
        name="openweather_current_city",
        description=(
            "Consulta clima actual por ciudad con OpenWeather (temperatura, sensacion, humedad, "
            "viento y precipitacion). Parametros: city, country opcional, units, lang."
        ),
        args_schema=OpenWeatherCurrentInput,
    )


def register_openweather_skill(
    tools_list: list[Any],
    openweather_config: Optional[dict] = None,
    research_config: Optional[dict] = None,
) -> None:
    # #region agent log
    _agent_debug_log(
        "H2",
        "openweather_bridge.py:register_openweather_skill",
        "register_called",
        {
            "openweather_config_is_none": openweather_config is None,
            "research_config_present": research_config is not None,
            "enabled_flag": (openweather_config or {}).get("enabled")
            if isinstance(openweather_config, dict)
            else None,
        },
    )
    # #endregion
    if openweather_config is None:
        return
    try:
        tool = _openweather_current_tool(openweather_config, research_config)
        if tool:
            tools_list.append(tool)
    except Exception as exc:
        _log.warning("register_openweather_skill failed: %s", exc)
