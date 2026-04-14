"""
Ingesta OHLCV hacia quant_core.ohlcv_data (Finanz + quant habilitado).

Histórico (timeframes configurables): SSH al lake Capadonna — CAPADONNA_SSH_HOST,
CAPADONNA_REMOTE_OHLC_CMD (plantilla JSON en stdout). Ver specs:
specs/features/Capadonna Lake OHLC SSH + IBKR Live.md

Tiempo real / fallback HTTP: IBKR_MARKET_DATA_URL (GET; query ticker, timeframe,
lookback_days); IBKR_PORTFOLIO_API_KEY o IBKR_MARKET_DATA_API_KEY opcional Bearer.

Solo IB Gateway (sin lake): IBKR_GATEWAY_OHLCV_URL apunta a GET .../api/market/ibkr/historical
(mismo contrato query/Bearer que arriba).
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
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List, Optional, Tuple

from duckclaw.utils.logger import log_tool_execution_sync

_log = logging.getLogger(__name__)


def _ibkr_http_timeout_sec() -> float:
    raw = (
        os.environ.get("IBKR_HTTP_TIMEOUT_SEC")
        or os.environ.get("IBKR_GATEWAY_HTTP_TIMEOUT_SEC")
        or "120"
    ).strip()
    try:
        t = float(raw)
    except ValueError:
        t = 120.0
    return float(max(30, min(t, 300)))


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
    _ssh_ok = capadonna_ssh_config_ok()
    if not _ssh_ok:
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


def _http_fetch_json_at_base(
    base: str, tkr: str, tf: str, lookback_days: int
) -> Tuple[Optional[Any], Optional[str]]:
    base = (base or "").strip()
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
    _to = _ibkr_http_timeout_sec()
    try:
        with urllib.request.urlopen(req, timeout=_to) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return json.loads(body), None
    except urllib.error.HTTPError as e:
        _log.warning("[quant_market] HTTP %s", e.code)
        detail = f"HTTP {e.code}: mercado no disponible."
        try:
            raw = e.read().decode("utf-8", errors="replace")
            body = json.loads(raw)
            if isinstance(body, dict):
                msg = body.get("message") or body.get("error")
                if msg is not None and str(msg).strip():
                    detail = f"HTTP {e.code}: {str(msg).strip()}"
        except (json.JSONDecodeError, TypeError, UnicodeDecodeError):
            pass
        return None, json.dumps({"error": detail}, ensure_ascii=False)
    except urllib.error.URLError as e:
        _log.warning("[quant_market] URLError: %s", e.reason)
        reason_s = str(e.reason)
        errno = getattr(e.reason, "errno", None)
        refused = "refused" in reason_s.lower() or errno == 61
        hint = ""
        if refused:
            hint = (
                " Si la API Capadonna (puerto 8002) está en el VPS/Tailscale, "
                "IBKR_GATEWAY_OHLCV_URL debe usar el mismo host que IBKR_PORTFOLIO_API_URL "
                "(p. ej. /api/market/ohlcv o /api/market/ibkr/historical). "
                "127.0.0.1:8002 solo sirve con servicio local o túnel."
            )
        return None, json.dumps(
            {"error": f"Conexión fallida: {reason_s}.{hint}"},
            ensure_ascii=False,
        )
    except json.JSONDecodeError as e:
        return None, json.dumps({"error": f"Respuesta no JSON: {e}"}, ensure_ascii=False)


def _http_fetch_json(tkr: str, tf: str, lookback_days: int) -> Tuple[Optional[Any], Optional[str]]:
    base = (os.environ.get("IBKR_MARKET_DATA_URL") or "").strip()
    return _http_fetch_json_at_base(base, tkr, tf, lookback_days)


def _vix_ticker_store(ticker_upper: str) -> Optional[str]:
    """Normaliza VIX / ^VIX al ticker guardado en quant_core (`VIX`)."""
    s = (ticker_upper or "").strip().upper()
    if s.startswith("^"):
        s = s[1:]
    return "VIX" if s == "VIX" else None


def _yfinance_interval_for_tf(tf_norm: str) -> str:
    """Intervalos soportados por yfinance.history (subset alineado con Finanz)."""
    return {
        "1m": "1m",
        "2m": "2m",
        "5m": "5m",
        "15m": "15m",
        "30m": "30m",
        "60m": "60m",
        "1h": "1h",
        "1d": "1d",
        "1w": "1wk",
        "1M": "1mo",
    }.get(tf_norm, "1d")


def _fetch_vix_yfinance_payload(
    *,
    ticker_store: str,
    tf: str,
    lookback_days: int,
) -> Tuple[Optional[list[dict[str, Any]]], Optional[str]]:
    """
    OHLCV para el índice VIX usando Yahoo (^VIX). Ejecuta en el gateway (no sandbox).
    """
    try:
        import yfinance as yf  # type: ignore[import-untyped]
    except ImportError:
        return None, json.dumps(
            {
                "error": "YFINANCE_IMPORT_ERROR",
                "message": "Instala yfinance en el venv del gateway (dependencia duckclaw-agents).",
            },
            ensure_ascii=False,
        )
    tf_norm = _normalize_timeframe_route_key(tf)
    interval = _yfinance_interval_for_tf(tf_norm)
    end = datetime.now(timezone.utc)
    start = end - timedelta(days=lookback_days)
    try:
        tk_yf = yf.Ticker("^VIX")
        hist = tk_yf.history(
            start=start.strftime("%Y-%m-%d"),
            end=(end + timedelta(days=1)).strftime("%Y-%m-%d"),
            interval=interval,
            auto_adjust=False,
            prepost=False,
        )
    except Exception as e:
        _log.warning("[quant_market] yfinance VIX: %s", e)
        return None, json.dumps(
            {"error": "YFINANCE_FETCH_FAILED", "message": str(e)[:500]},
            ensure_ascii=False,
        )
    if hist is None or hist.empty:
        return None, json.dumps(
            {
                "error": "YFINANCE_EMPTY",
                "ticker": ticker_store,
                "timeframe": tf,
                "message": "yfinance devolvió 0 velas para ^VIX (intervalo/ventana).",
            },
            ensure_ascii=False,
        )
    bars: list[dict[str, Any]] = []
    for ts_idx, row in hist.iterrows():
        try:
            ts_dt = ts_idx.to_pydatetime() if hasattr(ts_idx, "to_pydatetime") else ts_idx
            if getattr(ts_dt, "tzinfo", None) is not None:
                ts_dt = ts_dt.astimezone(timezone.utc).replace(tzinfo=None)
            o = float(row["Open"])
            h = float(row["High"])
            l = float(row["Low"])
            c = float(row["Close"])
            v_raw = row.get("Volume")
            v = 0.0
            if v_raw is not None:
                try:
                    vf = float(v_raw)
                    if vf == vf:
                        v = vf
                except (TypeError, ValueError):
                    pass
            bars.append(
                {
                    "ticker": ticker_store,
                    "timestamp": ts_dt.strftime("%Y-%m-%d %H:%M:%S"),
                    "open": o,
                    "high": h,
                    "low": l,
                    "close": c,
                    "volume": v,
                }
            )
        except (KeyError, TypeError, ValueError) as ex:
            _log.debug("[quant_market] yfinance VIX row skip: %s", ex)
            continue
    if not bars:
        return None, json.dumps(
            {"error": "YFINANCE_PARSE_FAILED", "message": "No se pudieron normalizar velas de ^VIX."},
            ensure_ascii=False,
        )
    return bars, None


def _ts_sort_key(ts: str) -> float:
    try:
        return datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S").timestamp()
    except ValueError:
        return 0.0


def _infer_user_id_for_writer(db_path: str) -> str:
    parts = Path(db_path).expanduser().resolve().parts
    if "private" in parts:
        i = parts.index("private")
        if i + 1 < len(parts):
            return str(parts[i + 1])
    return "default"


def _ohlcv_batch_upsert_sql_params(norm_rows: list[tuple[Any, ...]]) -> tuple[str, list[Any]]:
    parts_sql: list[str] = []
    flat: list[Any] = []
    for bt, ts, o, h, l, c, v in norm_rows:
        parts_sql.append("(?, CAST(? AS TIMESTAMP), ?, ?, ?, ?, ?)")
        flat.extend([bt, ts, o, h, l, c, v])
    values_sql = ",\n".join(parts_sql)
    sql = f"""
INSERT INTO quant_core.ohlcv_data (ticker, timestamp, open, high, low, close, volume)
VALUES {values_sql}
ON CONFLICT (ticker, timestamp) DO UPDATE SET
    open = excluded.open,
    high = excluded.high,
    low = excluded.low,
    close = excluded.close,
    volume = excluded.volume
"""
    return sql.strip(), flat


def _persist_ohlcv_batch(
    db: Any, norm_rows: list[tuple[Any, ...]]
) -> tuple[bool, list[tuple[Any, ...]], str]:
    """
    Persiste velas en quant_core.ohlcv_data.
    Workers con manifest read_only usan DuckDB RO: las INSERT directas fallan;
    se encola un único batch vía Redis (mismo patrón que admin_sql en factory).
    """
    if not norm_rows:
        return True, [], ""
    sql, flat = _ohlcv_batch_upsert_sql_params(norm_rows)
    path = str(getattr(db, "_path", "") or "").strip()
    ro = bool(getattr(db, "_read_only", False))
    if ro and path and path != ":memory:":
        from duckclaw.db_write_queue import enqueue_duckdb_write_sync, poll_task_status_sync

        released_ro = False
        resu = getattr(db, "resume_readonly_file_handle", None)
        try:
            susp = getattr(db, "suspend_readonly_file_handle", None)
            if callable(susp) and callable(resu):
                susp()
                released_ro = True
            resolved = str(Path(path).expanduser().resolve())
            uid = _infer_user_id_for_writer(resolved)
            task_id = enqueue_duckdb_write_sync(
                db_path=resolved,
                query=sql,
                params=flat,
                user_id=uid,
                tenant_id="default",
            )
            poll_to = 15.0 if released_ro else 3.0
            st = poll_task_status_sync(task_id, timeout_sec=poll_to)
            if st is None:
                return (
                    False,
                    [],
                    "Cola db-writer sin confirmación (timeout). Comprueba Redis y el proceso DuckClaw-DB-Writer.",
                )
            if st.status != "success":
                return False, [], (st.detail or "db-writer rechazó o falló la escritura OHLCV.")
            return True, norm_rows, ""
        except Exception as e:
            return False, [], str(e)[:500]
        finally:
            if released_ro and callable(resu):
                try:
                    resu()
                except Exception:
                    pass
    try:
        db.execute(sql, flat)
        return True, norm_rows, ""
    except Exception as e:
        return False, [], str(e)[:500]


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
    norm_rows: list[tuple[Any, ...]] = []
    for bar in bars:
        row = _normalize_row(bar, tkr)
        if row:
            norm_rows.append(row)
    if not norm_rows:
        return json.dumps(
            {
                "error": "OHLCV_NORMALIZE_FAILED",
                "ticker": tkr,
                "timeframe": tf,
                "lookback_days": lookback_days,
                "source": source,
                "bars_in_payload": len(bars),
                "message": (
                    "La API devolvió barras que no se pudieron normalizar "
                    "(timestamp u OHLC inválidos o faltantes)."
                ),
            },
            ensure_ascii=False,
        )
    ok, inserted_rows, err_detail = _persist_ohlcv_batch(db, norm_rows)
    inserted = len(inserted_rows) if ok else 0
    if not ok:
        return json.dumps(
            {
                "error": "OHLCV_PERSIST_FAILED",
                "ticker": tkr,
                "timeframe": tf,
                "lookback_days": lookback_days,
                "source": source,
                "rows_normalized": len(norm_rows),
                "detail": err_detail,
                "message": (
                    "No se pudo persistir velas en quant_core.ohlcv_data. "
                    f"Detalle: {err_detail}"
                ),
            },
            ensure_ascii=False,
        )
    best = max(inserted_rows, key=lambda r: _ts_sort_key(str(r[1])))
    out: dict[str, Any] = {
        "status": "ok",
        "ticker": tkr,
        "rows_upserted": inserted,
        "timeframe": tf,
        "lookback_days": lookback_days,
        "source": source,
        "bars_received": len(norm_rows),
        "last_close": float(best[5]),
        "last_bar_timestamp": str(best[1]),
    }
    return json.dumps(out, ensure_ascii=False)


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
    vix_store = _vix_ticker_store(tkr)
    if vix_store:
        bars, yerr = _fetch_vix_yfinance_payload(
            ticker_store=vix_store, tf=tf, lookback_days=lookback_days
        )
        if yerr:
            return yerr
        return _upsert_bars(db, bars, vix_store, tf, lookback_days, "yfinance")

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
                    "IBKR_REALTIME_TIMEFRAMES) e IBKR_MARKET_DATA_URL está vacío en el proceso del gateway. "
                    "Añade IBKR_MARKET_DATA_URL al env de PM2 (p. ej. ecosystem.api.config.cjs) además de .env. "
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


@log_tool_execution_sync(name="fetch_ib_gateway_ohlcv")
def _fetch_ib_gateway_ohlcv_impl(
    db: Any,
    *,
    ticker: str,
    timeframe: str = "1h",
    lookback_days: int = 20,
) -> str:
    """
    OHLCV solo vía HTTP al endpoint IB Gateway (p. ej. /api/market/ibkr/historical).
    No usa lake SSH ni yfinance; persiste en quant_core.ohlcv_data.
    """
    tkr = (ticker or "").strip().upper()
    if not tkr or len(tkr) > 12:
        return json.dumps({"error": "Ticker inválido."}, ensure_ascii=False)
    try:
        lookback_days = max(1, min(int(lookback_days), 4000))
    except (TypeError, ValueError):
        lookback_days = 20
    tf = (timeframe or "1h").strip() or "1h"
    if not _TF_SAFE.fullmatch(tf) or len(tf) > 16:
        return json.dumps({"error": "timeframe inválido (solo alfanumérico, máx. 16)."}, ensure_ascii=False)

    base = (os.environ.get("IBKR_GATEWAY_OHLCV_URL") or "").strip()
    if not base:
        return json.dumps(
            {
                "error": "IBKR_GATEWAY_OHLCV_UNCONFIGURED",
                "message": (
                    "IBKR_GATEWAY_OHLCV_URL está vacío. Define la URL del GET /api/market/ibkr/historical "
                    "(solo IB Gateway, sin lake) en el proceso del gateway, p. ej. PM2."
                ),
            },
            ensure_ascii=False,
        )
    payload, err = _http_fetch_json_at_base(base, tkr, tf, lookback_days)
    if err:
        return err
    if payload is None:
        return json.dumps(
            {"error": "Sin respuesta del endpoint IBKR Gateway OHLCV."}, ensure_ascii=False
        )
    return _upsert_bars(db, payload, tkr, tf, lookback_days, "ibkr_gateway_http")


def _finanz_reply_already_documents_successful_ingest(reply: str) -> bool:
    """
    No sustituir el borrador si ya resume ingesta OK + verificación aunque mencione
    CAPADONNA_OFFLINE como matiz (runtime: nota al pie tras ibkr_http exitoso).
    """
    r = (reply or "").strip()
    if not r:
        return False
    low = r.lower()
    if "fetch_market_data" not in low:
        return False
    if "ingesta" in low and "exitosa" in low:
        return True
    if "`ok`" in r and "fetch_market" in low:
        return True
    if "quant_core.ohlcv_data" in low and "filas" in low and "✅" in r:
        return True
    return False


def finanz_reconcile_reply_with_fetch_market_tool(messages: Any, reply: str) -> str:
    """
    El asistente a veces ignora un ToolMessage exitoso de ``fetch_market_data`` (p. ej. tras un
    historial largo de fallos) y narra ``CAPADONNA_OFFLINE`` o lake SSH. Eso contradice el JSON
    real de la tool (``status`` ok). Corregimos el texto de egreso antes de síntesis/validadores.
    """
    r = (reply or "").strip()
    if not r or not messages:
        return reply or ""
    low = r.lower()
    false_offline = (
        "capadonna_offline" in low
        or "lake capadonna fuera" in low
        or "gateway ssh al vps" in low
    )
    if not false_offline:
        return reply or ""
    if _finanz_reply_already_documents_successful_ingest(r):
        return reply or ""

    last_ok: dict[str, Any] | None = None
    seq = list(messages)[-120:] if len(messages) > 120 else list(messages)
    for m in reversed(seq):
        name: str | None = None
        content: Any = None
        if isinstance(m, dict):
            rrole = str(m.get("role") or m.get("type") or "").lower()
            if rrole not in ("tool", "toolmessage"):
                continue
            name = m.get("name") if isinstance(m.get("name"), str) else None
            content = m.get("content")
        else:
            cls = type(m).__name__
            if cls != "ToolMessage" and getattr(m, "type", None) != "tool":
                continue
            name = getattr(m, "name", None)
            content = getattr(m, "content", None)

        if name != "fetch_market_data":
            continue
        if isinstance(content, list):
            try:
                from duckclaw.integrations.llm_providers import lc_message_content_to_text

                body = lc_message_content_to_text(m)
            except Exception:
                body = str(content)
        elif isinstance(content, str):
            body = content
        else:
            body = str(content or "")
        try:
            data = json.loads(body.strip())
        except (json.JSONDecodeError, TypeError, AttributeError):
            continue
        if not isinstance(data, dict) or data.get("status") != "ok":
            continue
        try:
            rows = int(data.get("rows_upserted") or 0)
        except (TypeError, ValueError):
            rows = 0
        if rows < 0:
            continue
        last_ok = data
        break

    if not last_ok:
        return reply or ""

    tkr = str(last_ok.get("ticker") or "?")
    tf = str(last_ok.get("timeframe") or "?")
    rows = int(last_ok.get("rows_upserted") or 0)
    src = str(last_ok.get("source") or "")
    lb = last_ok.get("lookback_days")
    lookback = str(lb) if lb is not None else "?"
    return (
        f"## Ingesta OHLCV\n\n"
        f"`fetch_market_data` **correcto** para **{tkr}** (`timeframe={tf}`, lookback_days={lookback}, "
        f"fuente `{src}`): **{rows}** fila(s) upsert en `quant_core.ohlcv_data`.\n\n"
        f"_Nota interna: el borrador citaba error de lake/SSH; el JSON de la herramienta indica éxito._\n\n"
        f"**Siguientes pasos**\n"
        f"- Si el usuario pidió conteo o último cierre, ejecuta `read_sql` sobre `quant_core.ohlcv_data` "
        f"para **{tkr}** en esta ventana.\n"
        f"- `CAPADONNA_OFFLINE` aplica sobre todo a `fetch_lake_ohlcv`, no a esta ingesta HTTP/lake exitosa."
    )


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
