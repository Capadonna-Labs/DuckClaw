"""
IBKR Bridge — consulta read-only del portafolio de Interactive Brokers.

Spec: Integración de Contexto IBKR (Read-Only Portfolio API)
Requiere: IBKR_PORTFOLIO_API_URL e IBKR_PORTFOLIO_API_KEY en el entorno.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Optional, Tuple

from duckclaw.utils.logger import log_tool_execution_sync

_log = logging.getLogger(__name__)

_DEBUG_LOG_PATH = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-adf9d8.log"


def _agent_debug_log(
    hypothesis_id: str,
    location: str,
    message: str,
    data: dict[str, Any],
) -> None:
    # #region agent log
    try:
        import time

        payload: dict[str, Any] = {
            "sessionId": "adf9d8",
            "runId": "ibkr-portfolio",
            "hypothesisId": hypothesis_id,
            "location": location,
            "message": message,
            "data": data,
            "timestamp": int(time.time() * 1000),
        }
        with open(_DEBUG_LOG_PATH, "a", encoding="utf-8") as df:
            df.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass
    # #endregion


def _ibkr_account_mode() -> str:
    m = (os.environ.get("IBKR_ACCOUNT_MODE") or "paper").strip().lower()
    return m if m in ("paper", "live") else "paper"


def _ibkr_portfolio_request_headers(api_key: str, mode: Optional[str] = None) -> dict[str, str]:
    """Cabeceras GET portafolio; el backend puede usar X-Duckclaw-IBKR-Account-Mode para enrutar paper vs live."""
    m = (mode if mode is not None else _ibkr_account_mode()).strip().lower()
    if m not in ("paper", "live"):
        m = "paper"
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "X-Duckclaw-IBKR-Account-Mode": m,
    }


def _ibkr_error_suggests_mode_mismatch(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    err = str(data.get("error") or data.get("message") or "").lower()
    return "snapshot_unavailable" in err


def _ibkr_snapshot_has_substance(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    if _ibkr_error_suggests_mode_mismatch(data):
        return False
    portfolio = data.get("portfolio") or data.get("positions") or []
    if isinstance(portfolio, dict):
        portfolio = list(portfolio.values()) if portfolio else []
    if portfolio:
        return True
    for key in ("total_value", "net_liquidation", "cash", "cash_balance"):
        v = data.get(key)
        if v is None:
            continue
        try:
            if float(v) > 0:
                return True
        except (TypeError, ValueError):
            pass
    return False


def _ibkr_fetch_portfolio_payload(
    api_url: str,
    api_key: str,
    positions_url: str,
    mode: str,
) -> dict[str, Any]:
    import urllib.request

    headers = _ibkr_portfolio_request_headers(api_key, mode)

    def _get(url: str) -> Any:
        req = urllib.request.Request(url, headers=headers, method="GET")
        with urllib.request.urlopen(req, timeout=15.0) as resp:
            return json.loads(resp.read().decode("utf-8", errors="replace"))

    data = _get(api_url)
    if not isinstance(data, dict):
        return {"error": "invalid_response", "_raw": data}
    portfolio = data.get("portfolio") or data.get("positions") or []
    total_val = data.get("total_value") or data.get("net_liquidation") or 0

    if (not portfolio or total_val == 0) and (positions_url or api_url.endswith("/summary")):
        fallback_url = positions_url or "/".join(api_url.split("/")[:-2]) + "/positions"
        try:
            pos_data = _get(fallback_url)
            _log.info(
                "[ibkr] summary vacío, fallback /positions | mode=%s | keys=%s",
                mode,
                list(pos_data.keys()) if isinstance(pos_data, dict) else "?",
            )
            if isinstance(pos_data, dict):
                pos_list = pos_data.get("positions") or pos_data.get("portfolio") or (
                    pos_data if isinstance(pos_data, list) else []
                )
                if pos_list:
                    data = dict(data)
                    data["portfolio"] = pos_list
                    data["positions"] = pos_list
                    if not data.get("total_value") and pos_data.get("total_value"):
                        data["total_value"] = pos_data.get("total_value")
                    if not data.get("net_liquidation") and pos_data.get("net_liquidation"):
                        data["total_value"] = data.get("total_value") or pos_data.get("net_liquidation")
        except Exception as e:
            _log.warning("[ibkr] fallback /positions failed (mode=%s): %s", mode, e)
    return data


def _ibkr_resolve_payload_with_optional_alt(
    api_url: str,
    api_key: str,
    positions_url: str,
) -> tuple[dict[str, Any], str, str]:
    """
    Devuelve (data, effective_mode, configured_mode).
    Si IBKR_ACCOUNT_MODE_ALT_FALLBACK no es 0/false, ante snapshot_unavailable
    en el modo configurado reintenta una vez el otro modo (paper<->live).
    """
    configured = _ibkr_account_mode()
    raw_env = os.environ.get("IBKR_ACCOUNT_MODE")
    _agent_debug_log(
        "H1",
        "ibkr_bridge.py:_ibkr_resolve_payload_with_optional_alt",
        "ibkr_env_and_configured_mode",
        {"IBKR_ACCOUNT_MODE_raw": raw_env, "configured_mode": configured},
    )
    data = _ibkr_fetch_portfolio_payload(api_url, api_key, positions_url, configured)
    portfolio = data.get("portfolio") or data.get("positions") or []
    _agent_debug_log(
        "H2",
        "ibkr_bridge.py:_ibkr_resolve_payload_with_optional_alt",
        "after_primary_fetch",
        {
            "configured_mode": configured,
            "portfolio_len": len(portfolio) if isinstance(portfolio, list) else 0,
            "error": str(data.get("error") or ""),
            "needs_alt": _ibkr_error_suggests_mode_mismatch(data),
        },
    )
    effective = configured
    fb = (os.environ.get("IBKR_ACCOUNT_MODE_ALT_FALLBACK") or "1").strip().lower()
    if fb in ("0", "false", "no"):
        return data, effective, configured
    # Solo reintento ante snapshot_unavailable (desajuste paper/live frecuente en Capadonna).
    if _ibkr_error_suggests_mode_mismatch(data):
        alt = "live" if configured == "paper" else "paper"
        data_alt = _ibkr_fetch_portfolio_payload(api_url, api_key, positions_url, alt)
        _agent_debug_log(
            "H4",
            "ibkr_bridge.py:_ibkr_resolve_payload_with_optional_alt",
            "after_alt_fetch",
            {
                "alt_mode": alt,
                "alt_error": str(data_alt.get("error") or "") if isinstance(data_alt, dict) else "",
                "alt_substance": _ibkr_snapshot_has_substance(data_alt),
            },
        )
        if _ibkr_snapshot_has_substance(data_alt):
            data = data_alt
            effective = alt
            _log.info(
                "[ibkr] snapshot_unavailable en modo %s; usando datos de modo %s",
                configured,
                effective,
            )
    _agent_debug_log(
        "H3",
        "ibkr_bridge.py:_ibkr_resolve_payload_with_optional_alt",
        "resolved_effective_mode",
        {
            "configured_mode": configured,
            "effective_mode": effective,
            "used_alt": effective != configured,
            "has_substance": _ibkr_snapshot_has_substance(data),
        },
    )
    return data, effective, configured


def fetch_ibkr_total_equity_numeric() -> Tuple[Optional[float], str]:
    """
    Lee solo el valor total de cuenta desde la API IBKR (mismo contrato que get_ibkr_portfolio).
    Retorna (valor, "") si OK; (None, mensaje corto) si falla configuración o red.
    """
    api_url = os.environ.get("IBKR_PORTFOLIO_API_URL", "").strip()
    api_key = os.environ.get("IBKR_PORTFOLIO_API_KEY", "").strip()
    positions_url = os.environ.get("IBKR_PORTFOLIO_POSITIONS_URL", "").strip()
    if not api_url or not api_key:
        return None, "IBKR_PORTFOLIO_API_URL/KEY no configurados"
    try:
        from urllib.error import HTTPError, URLError

        data, _, _ = _ibkr_resolve_payload_with_optional_alt(api_url, api_key, positions_url)
        if not isinstance(data, dict):
            return None, "respuesta no es JSON objeto"
        portfolio = data.get("portfolio") or data.get("positions") or []
        total_value = data.get("total_value")
        if total_value is None:
            total_value = data.get("net_liquidation") or data.get("equity") or data.get("value") or 0
        try:
            total_value = float(total_value)
        except (TypeError, ValueError):
            total_value = 0.0
        if total_value == 0 and portfolio and isinstance(portfolio, list):
            for p in portfolio:
                if isinstance(p, dict):
                    mv = p.get("market_value") or p.get("marketValue") or p.get("value") or 0
                    try:
                        total_value += float(mv)
                    except (TypeError, ValueError):
                        pass
        if total_value <= 0:
            return None, "total_value no disponible o cero"
        return total_value, ""
    except HTTPError as e:
        return None, f"HTTP {e.code}"
    except URLError as e:
        return None, str(e.reason)[:120]
    except (TimeoutError, OSError, json.JSONDecodeError) as e:
        return None, str(e)[:120]
    except Exception as e:
        return None, str(e)[:120]


def _ibkr_portfolio_preamble(*, effective_mode: str, configured_mode: str) -> str:
    """Texto previo: modo efectivo del snapshot (puede diferir del env si hubo reintento paper/live)."""
    if effective_mode != configured_mode:
        return (
            f"Cuenta IBKR: snapshot en modo **{effective_mode}** "
            f"(env `IBKR_ACCOUNT_MODE` era **{configured_mode}**; ese modo devolvió `snapshot_unavailable` y se reintentó en **{effective_mode}**). "
            f"Para evitar el reintento, define `IBKR_ACCOUNT_MODE={effective_mode}` alineado al IB Gateway.\n\n"
        )
    return (
        f"Cuenta IBKR solicitada (env `IBKR_ACCOUNT_MODE`): **{effective_mode}**. "
        "El snapshot numérico depende de que `IBKR_PORTFOLIO_API_URL` apunte a un servicio conectado al IB Gateway en **ese** modo.\n\n"
    )


def _extract_portfolio_context(data: Any, *, account_mode_for_display: Optional[str] = None) -> str:
    """
    Extrae y formatea el contexto del portfolio desde la respuesta JSON de la API.
    Soporta formatos: {portfolio, total_value, count}, {positions, total_value}, etc.
    """
    if not isinstance(data, dict):
        return json.dumps(data, indent=2, ensure_ascii=False)

    # Si la API devuelve error en el body (aunque HTTP 200)
    err = data.get("error") or data.get("message") or data.get("detail")
    if err and isinstance(err, str):
        el = err.lower()
        # snapshot_unavailable: HTTP OK pero el servicio (p. ej. Capadonna) no pudo leer cuenta/posiciones;
        # no es lo mismo que IB Gateway caído (véase logs [ibkr] API OK + error en JSON).
        if "snapshot_unavailable" in el:
            disp = account_mode_for_display if account_mode_for_display is not None else _ibkr_account_mode()
            return (
                "Snapshot de cuenta IBKR no disponible (`snapshot_unavailable`). "
                "**No** es lo mismo que «sin conexión HTTP»: la petición llegó al servicio, pero ese proceso **no pudo leer** "
                "cuenta/posiciones desde IB Gateway/TWS. "
                f"DuckClaw ya pidió modo **{disp}** en la cabecera `X-Duckclaw-IBKR-Account-Mode`. "
                "Si en el VPS el Gateway está en live y aquí también es live, el problema suele estar en el **servicio** "
                "que sirve `IBKR_PORTFOLIO_API_URL` (Capadonna): `IB_ENV`, clientId único, sesión TWS/API, o logs del worker portfolio. "
                "Con `IBKR_ACCOUNT_MODE_ALT_FALLBACK=1` (por defecto) ya se reintenta el otro modo (paper/live); si tras eso sigue este error, "
                "revisa el backend, no el `.env` del gateway DuckClaw."
            )
        if "disconnect" in el or "gateway" in el or "unavailable" in el:
            return "Error de conexión: El Gateway de IBKR está desconectado en este momento. No puedo acceder a los datos de tu portafolio de inversiones."

    # Normalizar estructura: portfolio, positions, data.portfolio, cash como posición
    inner = data.get("data")
    portfolio = data.get("portfolio") or (inner.get("portfolio") if isinstance(inner, dict) else None)
    if portfolio is None:
        portfolio = data.get("positions") or data.get("positions_list") or []
    if isinstance(portfolio, dict):
        portfolio = list(portfolio.values()) if portfolio else []

    # Incluir cash si viene separado (cash_balance, available_funds, etc.)
    cash_val = data.get("cash") or data.get("cash_balance") or data.get("available_funds")
    if cash_val is None and isinstance(inner, dict):
        cash_val = inner.get("cash") or inner.get("cash_balance")
    if cash_val is not None and isinstance(portfolio, list):
        try:
            cv = float(cash_val)
            has_cash = any(isinstance(p, dict) and str(p.get("symbol") or "").upper() == "CASH" for p in portfolio)
            if cv != 0 and not has_cash:
                portfolio = list(portfolio) + [{"symbol": "CASH", "quantity": 1, "market_value": cv, "value": cv}]
        except (TypeError, ValueError):
            pass

    total_value = data.get("total_value")
    if total_value is None:
        total_value = data.get("net_liquidation") or data.get("equity") or data.get("value") or 0
    try:
        total_value = float(total_value)
    except (TypeError, ValueError):
        total_value = 0.0
    # Si total_value es 0 pero hay posiciones, sumar market_value
    if total_value == 0 and portfolio and isinstance(portfolio, list):
        for p in portfolio:
            if isinstance(p, dict):
                mv = p.get("market_value") or p.get("marketValue") or p.get("value") or 0
                try:
                    total_value += float(mv)
                except (TypeError, ValueError):
                    pass

    count = data.get("count")
    if count is None and isinstance(portfolio, list):
        count = len(portfolio)

    disp = account_mode_for_display if account_mode_for_display is not None else _ibkr_account_mode()
    lines = [
        f"Estado: IBKR Gateway conectado (modo cuenta del snapshot: {disp}).",
        f"Valor total: ${total_value:,.2f}",
        f"Posiciones: {count or 0}",
    ]

    if portfolio and isinstance(portfolio, list) and len(portfolio) > 0:
        lines.append("")
        lines.append("Detalle de posiciones:")
        agg_unreal = 0.0
        has_unreal = False
        agg_real = 0.0
        has_real = False
        for i, pos in enumerate(portfolio[:20], 1):  # Máx 20 para no saturar
            if isinstance(pos, dict):
                sym = pos.get("symbol") or pos.get("conid") or pos.get("ticker") or "?"
                qty = pos.get("quantity") or pos.get("position") or pos.get("qty") or 0
                val = pos.get("market_value") or pos.get("value") or pos.get("marketValue") or ""
                if val != "":
                    try:
                        val = f" ${float(val):,.2f}"
                    except (TypeError, ValueError):
                        val = f" {val}"
                pnl_parts: list[str] = []
                u = (
                    pos.get("unrealized_pnl")
                    if pos.get("unrealized_pnl") is not None
                    else pos.get("unrealizedPnL")
                )
                r = (
                    pos.get("realized_pnl")
                    if pos.get("realized_pnl") is not None
                    else pos.get("realizedPnL")
                )
                if u is not None and str(u).strip() != "":
                    try:
                        fu = float(u)
                        agg_unreal += fu
                        has_unreal = True
                        pnl_parts.append(f"PnL no realizado: ${fu:,.2f}")
                    except (TypeError, ValueError):
                        pass
                if r is not None and str(r).strip() != "":
                    try:
                        fr = float(r)
                        agg_real += fr
                        has_real = True
                        pnl_parts.append(f"PnL realizado: ${fr:,.2f}")
                    except (TypeError, ValueError):
                        pass
                pnl_suffix = f" ({' | '.join(pnl_parts)})" if pnl_parts else ""
                lines.append(f"  {i}. {sym}: {qty} unidades{val}{pnl_suffix}")
            else:
                lines.append(f"  {i}. {pos}")
        if len(portfolio) > 20:
            lines.append(f"  ... y {len(portfolio) - 20} más")
        if has_unreal or has_real:
            lines.append("")
            if has_unreal:
                lines.append(f"PnL no realizado total (snapshot): ${agg_unreal:,.2f}")
            if has_real:
                lines.append(f"PnL realizado total (snapshot): ${agg_real:,.2f}")
    else:
        lines.append("")
        lines.append("No hay posiciones activas en la cuenta IBKR.")

    rendered = "\n".join(lines)
    return rendered


@log_tool_execution_sync(name="get_ibkr_portfolio")
def _get_ibkr_portfolio_impl() -> str:
    """
    Consulta el endpoint de IBKR y retorna el estado del portafolio.
    Si /api/portfolio/summary devuelve vacío, intenta /api/positions como fallback.
    """
    api_url = os.environ.get("IBKR_PORTFOLIO_API_URL", "").strip()
    api_key = os.environ.get("IBKR_PORTFOLIO_API_KEY", "").strip()
    positions_url = os.environ.get("IBKR_PORTFOLIO_POSITIONS_URL", "").strip()

    if not api_url or not api_key:
        _log.warning("[ibkr] Credenciales no configuradas (IBKR_PORTFOLIO_API_URL/KEY)")
        return "Error de configuración: Las credenciales de la API de IBKR no están configuradas en el entorno."

    try:
        from urllib.error import HTTPError, URLError

        data, effective, configured = _ibkr_resolve_payload_with_optional_alt(
            api_url, api_key, positions_url
        )
        portfolio = data.get("portfolio") or data.get("positions") or []
        plen = len(portfolio) if isinstance(portfolio, list) else 0
        _log.info(
            "[ibkr] API OK | effective_mode=%s | total_value=%s | portfolio_len=%s | raw_keys=%s",
            effective,
            data.get("total_value"),
            plen,
            list(data.keys())[:10] if isinstance(data, dict) else "?",
        )
        if not portfolio and isinstance(data, dict) and not _ibkr_error_suggests_mode_mismatch(data):
            _log.info(
                "[ibkr] Respuesta sin posiciones | sample=%r",
                json.dumps(data, ensure_ascii=False)[:300],
            )

        return _ibkr_portfolio_preamble(
            effective_mode=effective, configured_mode=configured
        ) + _extract_portfolio_context(data, account_mode_for_display=effective)
    except HTTPError as e:
        _log.warning("[ibkr] HTTP %s: %s", e.code, e.reason)
        return "Error de conexión: El Gateway de IBKR está desconectado en este momento. No puedo acceder a los datos de tu portafolio de inversiones."
    except URLError as e:
        _log.warning("[ibkr] URLError: %s", e.reason)
        if "timed out" in str(e.reason).lower() or "timeout" in str(e.reason).lower():
            return "Error de conexión: Timeout al conectar con el servidor de IBKR. Intenta más tarde."
        return "Error de conexión: El Gateway de IBKR está desconectado en este momento. No puedo acceder a los datos de tu portafolio de inversiones."
    except (TimeoutError, OSError) as e:
        _log.warning("[ibkr] Timeout/OSError: %s", e)
        if "timed out" in str(e).lower() or "timeout" in type(e).__name__.lower():
            return "Error de conexión: Timeout al conectar con el servidor de IBKR. Intenta más tarde."
        return "Error de conexión: El Gateway de IBKR está desconectado en este momento. No puedo acceder a los datos de tu portafolio de inversiones."
    except json.JSONDecodeError as e:
        _log.warning("[ibkr] JSON decode error: %s", e)
        return "Error interno: La API de IBKR devolvió una respuesta no válida."
    except Exception as e:
        _log.exception("[ibkr] Unexpected error")
        return f"Error interno al procesar el portafolio: {str(e)}"


def _get_ibkr_portfolio_tool(config: Optional[dict] = None) -> Any:
    """
    Crea un StructuredTool para consultar el portafolio IBKR.
    config: puede ser {} o {"enabled": true} para activar (credenciales vía env).
    """
    from langchain_core.tools import StructuredTool

    return StructuredTool.from_function(
        _get_ibkr_portfolio_impl,
        name="get_ibkr_portfolio",
        description=(
            "Obtiene saldo, posiciones y valor total de la cuenta IBKR (Interactive Brokers). "
            "Usa `IBKR_ACCOUNT_MODE` (paper/live) vía cabecera; ante `snapshot_unavailable` reintenta el otro modo "
            "si `IBKR_ACCOUNT_MODE_ALT_FALLBACK` está activo (por defecto). "
            "OBLIGATORIO para: 'cuanto dinero tengo', 'resumen de mi portfolio', 'portafolio', 'acciones', 'dinero en bolsa'. "
            "Ignora read_sql/admin_sql para estas consultas; los datos vienen de IBKR."
        ),
    )


def register_ibkr_skill(
    tools_list: list[Any],
    ibkr_config: Optional[dict] = None,
) -> None:
    """
    Registra la herramienta get_ibkr_portfolio en la lista.
    Llamar desde build_worker_graph cuando el manifest tiene ibkr config.
    ibkr_config puede ser {} para activar (credenciales vía IBKR_PORTFOLIO_API_URL e IBKR_PORTFOLIO_API_KEY).
    """
    if ibkr_config is None:
        return
    cfg = ibkr_config if isinstance(ibkr_config, dict) else {}
    if cfg.get("enabled") is False:
        return
    try:
        tool = _get_ibkr_portfolio_tool(cfg)
        if tool:
            tools_list.append(tool)
    except Exception:
        pass
