"""SIATA radar: listado HTTPS en /data/radar/ (scraping ligero, sin :8089)."""

from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests
from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)

_RADAR_BASE = "https://siata.gov.co/data/radar/"
_TIMEOUT_SEC = 10
_MAX_TOOL_JSON_CHARS = 500_000
_MAX_SUBDIRS_TO_SCAN = 15

# Carpetas de día YYYYMMDD (listado Apache).
_FOLDER_DATE_RE = re.compile(r'href=["\'](\d{8})/["\']', re.IGNORECASE)
# Primer segmento de subcarpeta bajo radar (evita ?C=N, parent, absolutos).
_SUBDIR_RE = re.compile(
    r'<td class="indexcolname">\s*<a href="([^"/?#][^"?#]*?)/"',
    re.IGNORECASE,
)


def _today_yyyymmdd() -> str:
    return datetime.now(ZoneInfo("America/Bogota")).strftime("%Y%m%d")


def _serialize_for_llm(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False)
    if len(raw) <= _MAX_TOOL_JSON_CHARS:
        return raw
    return json.dumps(
        {
            "status": payload.get("status"),
            "error": payload.get("error"),
            "truncated": True,
            "preview": raw[:_MAX_TOOL_JSON_CHARS],
        },
        ensure_ascii=False,
    )


def _http_get_text(url: str) -> str:
    r = requests.get(url, timeout=_TIMEOUT_SEC, allow_redirects=True)
    r.raise_for_status()
    return r.text


def _immediate_subdirs(html: str) -> list[str]:
    """Subcarpetas directas del listado (excluye parent y anclas raras)."""
    found: list[str] = []
    seen: set[str] = set()
    for m in _SUBDIR_RE.finditer(html):
        name = (m.group(1) or "").strip()
        if not name or name in seen:
            continue
        low = name.lower()
        if low in ("..", ".", "parent directory"):
            continue
        if name.startswith("?"):
            continue
        if "/" in name:
            continue
        seen.add(name)
        found.append(name)
    return found


def _collect_date_folder_paths(index_html: str) -> list[tuple[str, str]]:
    """
    Pares (ruta_relativa_con_slash_final, yyyymmdd).
    Ej.: ('20260329/', '20260329') o ('40_DBZH/20260329/', '20260329').
    """
    at_root = sorted(set(_FOLDER_DATE_RE.findall(index_html)))
    out: list[tuple[str, str]] = []
    if at_root:
        for d in at_root:
            out.append((f"{d}/", d))
        return out

    subdirs = _immediate_subdirs(index_html)[:_MAX_SUBDIRS_TO_SCAN]
    for sd in subdirs:
        sub_url = urljoin(_RADAR_BASE, sd + "/")
        try:
            sub_html = _http_get_text(sub_url)
        except requests.exceptions.RequestException as e:
            logger.debug("No se pudo listar %s: %s", sub_url, e)
            continue
        for d in sorted(set(_FOLDER_DATE_RE.findall(sub_html))):
            out.append((f"{sd}/{d}/", d))
    return out


def _file_hrefs(html: str) -> list[str]:
    """Enlaces a ficheros probable (no directorios)."""
    raw = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.IGNORECASE)
    out: list[str] = []
    for h in raw:
        u = (h or "").split("#")[0].split("?")[0].strip()
        if not u or u.endswith("/"):
            continue
        low = u.lower()
        if low in ("..", "../"):
            continue
        if low.startswith("http") and "siata.gov.co" not in low:
            continue
        base = u.rsplit("/", 1)[-1]
        if not base or base.startswith(".") or "C=" in u:
            continue
        if "." not in base:
            continue
        out.append(u)
    return out


def _basename(path: str) -> str:
    return path.rstrip("/").rsplit("/", 1)[-1]


def _file_sort_key(filename: str) -> tuple[str, str, str]:
    """
    Clave para ordenar de más reciente a más antiguo.
    Soporta ..._YYYYMMDD_HHMM..., YYYYMMDDHHMM.ext (compacto), o solo fecha.
    """
    base = _basename(filename)
    m = re.search(r"(?<![0-9])(\d{8})_(\d{4})(?![0-9])", base)
    if m:
        return (m.group(1), m.group(2), base)
    m2 = re.search(r"(?<![0-9])(\d{8})_(\d{6})(?![0-9])", base)
    if m2:
        hhmmss = m2.group(2)
        return (m2.group(1), hhmmss[:4], base)
    m_compact = re.search(r"(?<![0-9])(\d{8})(\d{4})\.", base)
    if m_compact:
        return (m_compact.group(1), m_compact.group(2), base)
    m3 = re.search(r"(\d{8})", base)
    if m3:
        return (m3.group(1), "9999", base)
    return ("00000000", "0000", base)


def _utc_time_to_colombia_labels(
    year: int,
    month: int,
    day: int,
    hour_utc: int,
    minute: int,
    second: int = 0,
) -> tuple[str, str]:
    """
    El timestamp en el nombre del archivo del radar SIATA está en UTC.
    Devuelve (hora UTC etiqueta, hora Colombia 12h con AM/PM).
    """
    utc_dt = datetime(year, month, day, hour_utc, minute, second, tzinfo=timezone.utc)
    bog = utc_dt.astimezone(ZoneInfo("America/Bogota"))
    if second:
        ts_utc = f"{hour_utc:02d}:{minute:02d}:{second:02d}"
    else:
        ts_utc = f"{hour_utc:02d}:{minute:02d}"
    # p. ej. "09:06 AM" — la hora local Colombia equivale a UTC−5 (sin DST).
    ts_col = bog.strftime("%I:%M %p")
    return ts_utc, ts_col


def _radar_timestamp_fields_from_filename(filename: str) -> dict[str, Any]:
    """
    Rellena timestamp_utc, timestamp_colombia y extracted_timestamp.
    Las horas del nombre de archivo se interpretan como UTC; Colombia vía astimezone.
    """
    base = _basename(filename)
    out: dict[str, Any] = {
        "timestamp_utc": None,
        "timestamp_colombia": None,
        "extracted_timestamp": "no inferido del nombre",
    }
    m = re.search(r"(?<![0-9])(\d{8})_(\d{4})(?![0-9])", base)
    if m:
        raw_d, raw_t = m.group(1), m.group(2)
        if len(raw_t) != 4:
            out["extracted_timestamp"] = f"{raw_d}_{raw_t} (nombre de archivo)"
            return out
        try:
            y, mo, d = int(raw_d[:4]), int(raw_d[4:6]), int(raw_d[6:8])
            hh, mm = int(raw_t[:2]), int(raw_t[2:])
            utc_l, col_l = _utc_time_to_colombia_labels(y, mo, d, hh, mm)
            out["timestamp_utc"] = utc_l
            out["timestamp_colombia"] = col_l
            out["extracted_timestamp"] = (
                f"{raw_d[:4]}-{raw_d[4:6]}-{raw_d[6:8]} · {utc_l} UTC → {col_l} (America/Bogota)"
            )
        except ValueError:
            out["extracted_timestamp"] = f"{raw_d}_{raw_t} (nombre de archivo)"
        return out
    m2 = re.search(r"(?<![0-9])(\d{8})_(\d{6})(?![0-9])", base)
    if m2:
        raw_d, raw_ts = m2.group(1), m2.group(2)
        try:
            y, mo, d = int(raw_d[:4]), int(raw_d[4:6]), int(raw_d[6:8])
            hh, mm, ss = int(raw_ts[:2]), int(raw_ts[2:4]), int(raw_ts[4:6])
            utc_l, col_l = _utc_time_to_colombia_labels(y, mo, d, hh, mm, ss)
            out["timestamp_utc"] = utc_l
            out["timestamp_colombia"] = col_l
            out["extracted_timestamp"] = (
                f"{raw_d[:4]}-{raw_d[4:6]}-{raw_d[6:8]} · {utc_l} UTC → {col_l} (America/Bogota)"
            )
        except ValueError:
            out["extracted_timestamp"] = f"{raw_d}_{raw_ts} (nombre de archivo)"
        return out
    # YYYYMMDDHHMM antes del punto (p. ej. 202603291623.png).
    m_compact = re.search(r"(?<![0-9])(\d{8})(\d{4})\.[a-z0-9]+$", base, re.IGNORECASE)
    if m_compact:
        raw_d, raw_t = m_compact.group(1), m_compact.group(2)
        try:
            y, mo, d = int(raw_d[:4]), int(raw_d[4:6]), int(raw_d[6:8])
            hh, mm = int(raw_t[:2]), int(raw_t[2:])
            utc_l, col_l = _utc_time_to_colombia_labels(y, mo, d, hh, mm)
            out["timestamp_utc"] = utc_l
            out["timestamp_colombia"] = col_l
            out["extracted_timestamp"] = (
                f"{raw_d[:4]}-{raw_d[4:6]}-{raw_d[6:8]} · {utc_l} UTC → {col_l} (America/Bogota)"
            )
        except ValueError:
            out["extracted_timestamp"] = f"{raw_d}{raw_t} (nombre de archivo)"
        return out
    m3 = re.search(r"(\d{8})", base)
    if m3:
        raw_d = m3.group(1)
        try:
            datetime.strptime(raw_d, "%Y%m%d")
            out["extracted_timestamp"] = f"{raw_d[:4]}-{raw_d[4:6]}-{raw_d[6:8]} (solo fecha en el archivo)"
        except ValueError:
            out["extracted_timestamp"] = raw_d
    return out


def scrape_siata_radar_realtime() -> dict[str, Any]:
    """
    Descubre la carpeta de día más reciente bajo https://siata.gov.co/data/radar/
    y el último archivo por convención de nombre (timestamp).
    """
    try:
        index_html = _http_get_text(_RADAR_BASE)
    except requests.exceptions.Timeout:
        return {"status": "error", "error": "Timeout al listar el radar SIATA (10s). Intenta más tarde."}
    except requests.exceptions.RequestException as e:
        return {
            "status": "error",
            "error": f"No se pudo acceder al listado del radar: {e!s}",
        }

    candidates = _collect_date_folder_paths(index_html)
    if not candidates:
        return {
            "status": "error",
            "error": (
                "No se encontraron carpetas YYYYMMDD en /data/radar/. "
                "El sitio puede haber cambiado el listado."
            ),
        }

    today = _today_yyyymmdd()
    dates = sorted({d for _, d in candidates}, reverse=True)
    chosen_date = today if today in dates else dates[0]

    paths_for = sorted({p for p, d in candidates if d == chosen_date}, reverse=True)
    folder_rel = paths_for[0]
    folder_url = urljoin(_RADAR_BASE, folder_rel)

    try:
        folder_html = _http_get_text(folder_url)
    except requests.exceptions.Timeout:
        return {"status": "error", "error": "Timeout al abrir la carpeta del día en el radar SIATA."}
    except requests.exceptions.RequestException as e:
        return {"status": "error", "error": f"No se pudo listar la carpeta del radar: {e!s}"}

    files = _file_hrefs(folder_html)
    if not files:
        return {
            "status": "error",
            "error": f"No se hallaron archivos en {folder_url}",
            "latest_folder": folder_rel.rstrip("/"),
        }

    def full_url(href: str) -> str:
        if href.lower().startswith("http"):
            return href
        return urljoin(folder_url, href)

    resolved = [(h, full_url(h)) for h in files]
    best_href, best_url = max(resolved, key=lambda x: _file_sort_key(x[0]))
    latest_name = _basename(best_href)

    ts = _radar_timestamp_fields_from_filename(latest_name)
    return {
        "status": "success",
        "latest_folder": folder_rel.rstrip("/"),
        "latest_file": latest_name,
        "timestamp_utc": ts["timestamp_utc"],
        "timestamp_colombia": ts["timestamp_colombia"],
        "extracted_timestamp": ts["extracted_timestamp"],
        "url": best_url,
    }


def _tool_scrape_siata_radar_realtime() -> str:
    return _serialize_for_llm(scrape_siata_radar_realtime())


def get_tools(db: Any, schema_name: str, spec: Any = None) -> list:
    return [
        StructuredTool.from_function(
            _tool_scrape_siata_radar_realtime,
            name="scrape_siata_radar_realtime",
            description=(
                "Data engineer: descubre la carpeta de fecha más reciente en "
                "https://siata.gov.co/data/radar/ (HTTPS), el último archivo del radar por nombre "
                "(timestamp en UTC en el nombre; la respuesta incluye timestamp_utc y timestamp_colombia). "
                "Sin argumentos. No repliques este scraping en el sandbox."
            ),
        ),
    ]
