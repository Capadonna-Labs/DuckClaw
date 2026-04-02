"""
Ingesta OHLCV hacia quant_core.ohlcv_data (Finanz + quant habilitado).

Histórico (timeframes configurables): SSH al lake Capadonna — CAPADONNA_SSH_HOST,
CAPADONNA_REMOTE_OHLC_CMD (plantilla JSON en stdout). Ver specs:
specs/features/Capadonna Lake OHLC SSH + IBKR Live.md

Tiempo real / fallback HTTP: IBKR_MARKET_DATA_URL (GET; query ticker, timeframe,
lookback_days); IBKR_PORTFOLIO_API_KEY o IBKR_MARKET_DATA_API_KEY opcional Bearer.
"""

from __future__ import annotations

import json
import logging
import os
import re
import shlex
import subprocess
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

from duckclaw.utils.logger import log_tool_execution_sync

_log = logging.getLogger(__name__)

_TF_SAFE = re.compile(r"^[0-9A-Za-z]+$")

_DEFAULT_HISTORICAL_TF = "1d,1w,1M,moc"
_DEFAULT_REALTIME_TF = "1m,5m,15m,30m,1h"


def _ssh_failed_json(message: str) -> str:
    return json.dumps({"error": "SSH_FAILED", "message": message}, ensure_ascii=False)


def _capadonna_offline_json(message: str = "Túnel Lake cerrado") -> str:
    return json.dumps({"error": "CAPADONNA_OFFLINE", "message": message}, ensure_ascii=False)


def _resolved_identity_file() -> Optional[str]:
    """Ruta a clave SSH: CAPADONNA_SSH_KEY_PATH gana sobre CAPADONNA_SSH_IDENTITY_FILE."""
    raw = (os.environ.get("CAPADONNA_SSH_KEY_PATH") or "").strip() or (
        os.environ.get("CAPADONNA_SSH_IDENTITY_FILE") or ""
    ).strip()
    if not raw:
        return None
    expanded = os.path.expanduser(raw)
    return expanded if expanded else None


def capadonna_ssh_config_ok() -> bool:
    """
    True si el lake puede intentarse: host, comando remoto, y si hay -i en env,
    el archivo debe existir.
    """
    host = (os.environ.get("CAPADONNA_SSH_HOST") or "").strip()
    cmd_tmpl = (os.environ.get("CAPADONNA_REMOTE_OHLC_CMD") or "").strip()
    if not host or not cmd_tmpl:
        return False
    id_path = _resolved_identity_file()
    if id_path is None:
        return True
    return os.path.isfile(id_path)


def _normalize_timeframe_route_key(tf: str) -> str:
    """Clave para enrutar lake vs IBKR: distingue 1M (mes) de 1m (minuto)."""
    s = (tf or "").strip()
    if not s:
        return "1d"
    if s == "1M":
        return "1M"
    return s.lower()


def _parse_tf_set(env_name: str, default_csv: str) -> set[str]:
    raw = (os.environ.get(env_name) or "").strip()
    if not raw:
        raw = default_csv
    return {_normalize_timeframe_route_key(x) for x in raw.split(",") if x.strip()}


def _lake_ssh_configured() -> bool:
    host = (os.environ.get("CAPADONNA_SSH_HOST") or "").strip()
    cmd = (os.environ.get("CAPADONNA_REMOTE_OHLC_CMD") or "").strip()
    return bool(host and cmd)


def _use_lake_ssh(tf_norm: str) -> bool:
    if not _lake_ssh_configured():
        return False
    hist = _parse_tf_set("CAPADONNA_HISTORICAL_TIMEFRAMES", _DEFAULT_HISTORICAL_TF)
    live = _parse_tf_set("IBKR_REALTIME_TIMEFRAMES", _DEFAULT_REALTIME_TF)
    if tf_norm not in hist:
        return False
    if tf_norm in live:
        return False
    return True


def lake_belief_observed_values() -> tuple[float, float]:
    """
    (lake_host_configured, lake_status_online) para agent_beliefs.
    - lake_host_configured: env completo válido (incl. clave si está declarada).
    - lake_status_online: host + comando remoto presentes (túnel a nivel config).
    """
    strict = capadonna_ssh_config_ok()
    routed = _lake_ssh_configured()
    return (1.0 if strict else 0.0, 1.0 if routed else 0.0)


def _bars_from_payload(data: Any) -> List[dict]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("bars", "data", "ohlcv", "candles", "rows", "results"):
        v = data.get(key)
        if isinstance(v, list):
            return [x for x in v if isinstance(x, dict)]
    return []


def _pick(d: dict, *keys: str) -> Any:
    lower = {str(k).lower(): k for k in d}
    for k in keys:
        lk = k.lower()
        if lk in lower:
            return d[lower[lk]]
    for k in keys:
        if k in d:
            return d[k]
    return None


def _parse_ts(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    if isinstance(raw, (int, float)):
        # assume ms if large
        x = float(raw)
        if x > 1e12:
            x = x / 1000.0
        if x > 1e10:
            x = x / 1000.0
        try:
            dt = datetime.fromtimestamp(x, tz=timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S")
        except (OverflowError, OSError, ValueError):
            return None
    s = str(raw).strip()
    if not s:
        return None
    return s.replace("T", " ").replace("Z", "")[:32]


def _normalize_row(bar: dict, ticker_default: str) -> Optional[tuple]:
    ts = _parse_ts(_pick(bar, "timestamp", "time", "date", "t", "ts", "datetime"))
    o = _pick(bar, "open", "o")
    h = _pick(bar, "high", "h")
    l = _pick(bar, "low", "l")
    c = _pick(bar, "close", "c")
    v = _pick(bar, "volume", "vol", "v")
    tick = _pick(bar, "ticker", "symbol") or ticker_default
    if not ts or tick is None:
        return None
    try:
        return (
            str(tick).strip().upper(),
            ts,
            float(o),
            float(h),
            float(l),
            float(c),
            float(v) if v is not None else 0.0,
        )
    except (TypeError, ValueError):
        return None


def _normalized_bar_dicts(data: Any, tkr: str) -> List[dict[str, Any]]:
    bars = _bars_from_payload(data)
    if not bars and isinstance(data, dict):
        inner = data.get(tkr) or data.get("series")
        bars = _bars_from_payload(inner)
    out: List[dict[str, Any]] = []
    for bar in bars:
        row = _normalize_row(bar, tkr)
        if not row:
            continue
        tick, ts, o, h, l, c, v = row
        out.append(
            {
                "ticker": tick,
                "timestamp": ts,
                "open": o,
                "high": h,
                "low": l,
                "close": c,
                "volume": v,
            }
        )
    return out


def _run_lake_ssh_json(tkr: str, tf: str, lookback_days: int) -> Tuple[Optional[Any], Optional[str]]:
    """Ejecuta el comando remoto; errores de transporte/parseo como JSON con error SSH_FAILED."""
    host = (os.environ.get("CAPADONNA_SSH_HOST") or "").strip()
    cmd_tmpl = (os.environ.get("CAPADONNA_REMOTE_OHLC_CMD") or "").strip()
    user = (os.environ.get("CAPADONNA_SSH_USER") or "capadonna").strip()
    try:
        timeout_s = max(10, min(int(os.environ.get("CAPADONNA_SSH_TIMEOUT") or "120"), 600))
    except (TypeError, ValueError):
        timeout_s = 120
    remote_cmd = (
        cmd_tmpl.replace("{ticker}", shlex.quote(tkr))
        .replace("{timeframe}", shlex.quote(tf))
        .replace("{lookback_days}", shlex.quote(str(lookback_days)))
    )
    ssh_args: List[str] = ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=30"]
    id_path = _resolved_identity_file()
    if id_path:
        ssh_args.extend(["-i", id_path])
    ssh_args.extend([f"{user}@{host}", remote_cmd])
    try:
        proc = subprocess.run(
            ssh_args,
            capture_output=True,
            text=True,
            timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        _log.warning("[quant_market] lake SSH timeout (%ss)", timeout_s)
        return None, _ssh_failed_json(f"SSH al lake superó el límite de {timeout_s}s.")
    except FileNotFoundError:
        return None, _ssh_failed_json("Ejecutable `ssh` no encontrado en PATH.")
    if proc.returncode != 0:
        err_tail = (proc.stderr or "").strip()[:500]
        _log.warning("[quant_market] lake SSH rc=%s", proc.returncode)
        msg = f"SSH al lake falló (código {proc.returncode})."
        if err_tail:
            msg = f"{msg} {err_tail[:400]}"
        return None, _ssh_failed_json(msg)
    if (proc.stderr or "").strip():
        _log.debug("[quant_market] lake SSH stderr: %s", proc.stderr.strip()[:400])
    body = (proc.stdout or "").strip()
    if not body:
        return None, _ssh_failed_json("El comando remoto no devolvió JSON en stdout.")
    try:
        return json.loads(body), None
    except json.JSONDecodeError as e:
        return None, _ssh_failed_json(f"Salida del lake no es JSON válido: {e}")


def _fetch_lake_ohlcv_impl(
    *,
    ticker: str,
    timeframe: str = "1d",
    lookback_days: int = 90,
) -> str:
    if not capadonna_ssh_config_ok():
        return _capadonna_offline_json("Túnel Lake cerrado")
    tkr = (ticker or "").strip().upper()
    if not tkr or len(tkr) > 12:
        return _ssh_failed_json("Ticker inválido.")
    try:
        lookback_days = max(1, min(int(lookback_days), 4000))
    except (TypeError, ValueError):
        lookback_days = 90
    tf = (timeframe or "1d").strip() or "1d"
    if not _TF_SAFE.fullmatch(tf) or len(tf) > 16:
        return _ssh_failed_json("timeframe inválido (solo alfanumérico, máx. 16).")
    payload, err = _run_lake_ssh_json(tkr, tf, lookback_days)
    if err:
        return err
    bars = _normalized_bar_dicts(payload, tkr)
    return json.dumps(
        {
            "status": "ok",
            "ticker": tkr,
            "timeframe": tf,
            "lookback_days": lookback_days,
            "bar_count": len(bars),
            "bars": bars,
        },
        ensure_ascii=False,
    )


@log_tool_execution_sync(name="fetch_lake_ohlcv")
def fetch_lake_ohlcv(
    ticker: str,
    timeframe: str = "1d",
    lookback_days: int = 90,
) -> str:
    """OHLCV vía SSH al lake (solo JSON; no escribe DuckDB). Errores: CAPADONNA_OFFLINE, SSH_FAILED."""
    return _fetch_lake_ohlcv_impl(
        ticker=ticker, timeframe=timeframe, lookback_days=int(lookback_days)
    )


def _http_fetch_json(tkr: str, tf: str, lookback_days: int) -> Tuple[Optional[Any], Optional[str]]:
    base = (os.environ.get("IBKR_MARKET_DATA_URL") or "").strip()
    if not base:
        return None, None  # caller builds config error
    q = urllib.parse.urlencode(
        {"ticker": tkr, "timeframe": tf, "lookback_days": str(lookback_days)}
    )
    url = f"{base}&{q}" if "?" in base else f"{base}?{q}"
    req = urllib.request.Request(url, method="GET")
    token = (
        os.environ.get("IBKR_PORTFOLIO_API_KEY") or os.environ.get("IBKR_MARKET_DATA_API_KEY") or ""
    ).strip()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Accept", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body), None
    except urllib.error.HTTPError as e:
        _log.warning("[quant_market] HTTP %s", e.code)
        return None, json.dumps({"error": f"HTTP {e.code}: mercado no disponible."}, ensure_ascii=False)
    except urllib.error.URLError as e:
        _log.warning("[quant_market] URLError: %s", e.reason)
        return None, json.dumps({"error": f"Conexión fallida: {e.reason!s}"}, ensure_ascii=False)
    except json.JSONDecodeError as e:
        return None, json.dumps({"error": f"Respuesta no JSON: {e}"}, ensure_ascii=False)


def _upsert_bars(db: Any, data: Any, tkr: str, tf: str, lookback_days: int, source: str) -> str:
    bars = _bars_from_payload(data)
    if not bars and isinstance(data, dict):
        inner = data.get(tkr) or data.get("series")
        bars = _bars_from_payload(inner)
    if not bars:
        if source == "lake_ssh":
            return json.dumps(
                {
                    "error": "LAKE_EMPTY_BARS",
                    "ticker": tkr,
                    "timeframe": tf,
                    "message": (
                        "SSH al lake respondió sin velas útiles: el símbolo puede no existir en data/lake "
                        "(Hive daily/gold/intraday/moc) o el lookback no intersecta particiones. "
                        "No indica fallo de IBKR_MARKET_DATA_URL."
                    ),
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "error": "NO_OHLCV_BARS",
                "ticker": tkr,
                "message": "Sin barras OHLCV en la respuesta. Revisa el contrato del endpoint HTTP o del script lake.",
            },
            ensure_ascii=False,
        )
    inserted = 0
    for bar in bars:
        row = _normalize_row(bar, tkr)
        if not row:
            continue
        bt, ts, o, h, l, c, v = row
        try:
            db.execute(
                """
                INSERT INTO quant_core.ohlcv_data (ticker, timestamp, open, high, low, close, volume)
                VALUES (?, CAST(? AS TIMESTAMP), ?, ?, ?, ?, ?)
                ON CONFLICT (ticker, timestamp) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume
                """,
                (bt, ts, o, h, l, c, v),
            )
            inserted += 1
        except Exception as e:
            _log.debug("[quant_market] row skip: %s", e)
    return json.dumps(
        {
            "status": "ok",
            "ticker": tkr,
            "rows_upserted": inserted,
            "timeframe": tf,
            "lookback_days": lookback_days,
            "source": source,
        },
        ensure_ascii=False,
    )


@log_tool_execution_sync(name="fetch_market_data")
def _fetch_market_data_impl(
    db: Any,
    *,
    ticker: str,
    timeframe: str = "1d",
    lookback_days: int = 365,
) -> str:
    tkr = (ticker or "").strip().upper()
    if not tkr or len(tkr) > 12:
        return json.dumps({"error": "Ticker inválido."}, ensure_ascii=False)
    try:
        lookback_days = max(1, min(int(lookback_days), 4000))
    except (TypeError, ValueError):
        lookback_days = 365
    tf = (timeframe or "1d").strip() or "1d"
    if not _TF_SAFE.fullmatch(tf) or len(tf) > 16:
        return json.dumps({"error": "timeframe inválido (solo alfanumérico, máx. 16)."}, ensure_ascii=False)

    tf_norm = _normalize_timeframe_route_key(tf)
    use_lake = _use_lake_ssh(tf_norm)

    if use_lake:
        payload, err = _run_lake_ssh_json(tkr, tf, lookback_days)
        if err:
            return err
        return _upsert_bars(db, payload, tkr, tf, lookback_days, "lake_ssh")

    base = (os.environ.get("IBKR_MARKET_DATA_URL") or "").strip()
    if not base:
        return json.dumps(
            {
                "error": "IBKR_MARKET_HTTP_UNCONFIGURED",
                "message": (
                    "Este timeframe no está enrutado al lake (revisa CAPADONNA_HISTORICAL_TIMEFRAMES vs "
                    "IBKR_REALTIME_TIMEFRAMES) e IBKR_MARKET_DATA_URL está vacío. "
                    "Para solo lake: usa 1d/1w/1M/moc o añade el TF al histórico y quítalo de realtime; "
                    "o define IBKR_MARKET_DATA_URL para intradía por HTTP."
                ),
            },
            ensure_ascii=False,
        )
    payload, err = _http_fetch_json(tkr, tf, lookback_days)
    if err:
        return err
    if payload is None:
        return json.dumps({"error": "Sin respuesta del gateway IBKR."}, ensure_ascii=False)
    return _upsert_bars(db, payload, tkr, tf, lookback_days, "ibkr_http")


def register_quant_market_skill(db: Any, tools: list[Any], spec: Any) -> None:
    """Registra fetch_market_data si el manifest tiene quant.enabled."""
    from langchain_core.tools import StructuredTool

    def _run(ticker: str, timeframe: str = "1d", lookback_days: int = 365) -> str:
        return _fetch_market_data_impl(
            db, ticker=ticker, timeframe=timeframe, lookback_days=int(lookback_days)
        )

    tools.append(
        StructuredTool.from_function(
            _run,
            name="fetch_market_data",
            description=(
                "Descarga OHLCV y guarda en quant_core.ohlcv_data. Histórico lake (SSH al VPS, data/lake Hive): "
                "1d→daily, 1w/1M→gold, 1m/5m/…/1h→intraday, moc→moc; también timeframe daily|gold|intraday|moc. "
                "Si IBKR_MARKET_DATA_URL está definido, timeframes que no van al lake usan HTTP; "
                "si está vacío, solo lake (timeframes en CAPADONNA_HISTORICAL_TIMEFRAMES y no en IBKR_REALTIME_TIMEFRAMES). "
                "Parámetros: ticker, timeframe, lookback_days."
            ),
        )
    )

    def _run_lake(ticker: str, timeframe: str = "1d", lookback_days: int = 90) -> str:
        return fetch_lake_ohlcv(ticker=ticker, timeframe=timeframe, lookback_days=int(lookback_days))

    tools.append(
        StructuredTool.from_function(
            _run_lake,
            name="fetch_lake_ohlcv",
            description=(
                "Lee OHLCV (o serie de precio en moc/) del Lake Capadonna vía SSH (Tailscale). Devuelve solo JSON con barras; "
                "no persiste en DuckDB. Timeframes: 1d→daily, 1w/1M→gold, intradía→intraday, moc→moc; también daily|gold|intraday|moc. "
                "Errores: CAPADONNA_OFFLINE, SSH_FAILED. lookback_days default 90."
            ),
        )
    )

    def _verify_visual_claim(
        symbol: str = "",
        claimed_value: Optional[float] = None,
        claim: str = "",
    ) -> str:
        narrative = (claim or "").strip()
        sym = (symbol or "").strip().upper()
        if narrative and not sym:
            return json.dumps(
                {
                    "status": "not_applicable",
                    "message": (
                        "Sin ticker+cifra de cotización en la imagen: use tavily_search u otras "
                        "fuentes para hechos de noticias; esta tool solo cruza versus quant_core.ohlcv_data."
                    ),
                },
                ensure_ascii=False,
            )
        if not sym:
            return json.dumps(
                {"error": "symbol requerido (o use claim=... solo para marcar que no hay precio de ticker)"},
                ensure_ascii=False,
            )
        if claimed_value is None:
            return json.dumps({"error": "claimed_value requerido cuando symbol está presente"}, ensure_ascii=False)
        try:
            claimed = float(claimed_value)
        except (TypeError, ValueError):
            return json.dumps({"error": "claimed_value inválido"}, ensure_ascii=False)
        try:
            raw = db.query(
                f"SELECT close, timestamp FROM quant_core.ohlcv_data WHERE UPPER(ticker)='{sym}' "
                "ORDER BY timestamp DESC LIMIT 1"
            )
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
            if not rows:
                return json.dumps(
                    {
                        "status": "no_evidence",
                        "symbol": sym,
                        "claimed_value": claimed,
                        "message": "No hay evidencia en quant_core.ohlcv_data para validar el claim visual.",
                    },
                    ensure_ascii=False,
                )
            row = rows[0] if isinstance(rows[0], dict) else {}
            actual = float(row.get("close"))
            drift = abs(actual - claimed) / actual if actual else 1.0
            return json.dumps(
                {
                    "status": "verified" if drift <= 0.01 else "mismatch",
                    "symbol": sym,
                    "claimed_value": claimed,
                    "actual_value": actual,
                    "timestamp": row.get("timestamp"),
                    "relative_drift": drift,
                },
                ensure_ascii=False,
            )
        except Exception as exc:
            return json.dumps({"error": str(exc)}, ensure_ascii=False)

    tools.append(
        StructuredTool.from_function(
            _verify_visual_claim,
            name="verify_visual_claim",
            description=(
                "Valida precio/ticker de un gráfico o tabla OHLCV: symbol + claimed_value vs último close en "
                "quant_core.ohlcv_data (verified/mismatch/no_evidence). Para titulares de noticias sin precio "
                "de bolsa en la imagen, use claim con el texto visto (devuelve not_applicable) y confirme con "
                "tavily_search."
            ),
        )
    )
