"""
IBKR Bridge — consulta read-only del portafolio de Interactive Brokers.

Spec: Integración de Contexto IBKR (Read-Only Portfolio API)
Requiere: IBKR_PORTFOLIO_API_URL e IBKR_PORTFOLIO_API_KEY en el entorno.
"""

from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional, Tuple

from duckclaw.utils.logger import log_tool_execution_sync

_log = logging.getLogger(__name__)


def _ibkr_account_mode() -> str:
    m = (os.environ.get("IBKR_ACCOUNT_MODE") or "paper").strip().lower()
    return m if m in ("paper", "live") else "paper"


def _ibkr_portfolio_request_headers(api_key: str) -> dict[str, str]:
    """Cabeceras GET portafolio; el backend puede usar X-Duckclaw-IBKR-Account-Mode para enrutar paper vs live."""
    mode = _ibkr_account_mode()
    return {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json",
        "X-Duckclaw-IBKR-Account-Mode": mode,
    }


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
        import urllib.request
        from urllib.error import HTTPError, URLError

        headers = _ibkr_portfolio_request_headers(api_key)

        def _get(url: str) -> Any:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))

        data = _get(api_url)
        if not isinstance(data, dict):
            return None, "respuesta no es JSON objeto"
        portfolio = data.get("portfolio") or data.get("positions") or []
        total_val = data.get("total_value") or data.get("net_liquidation") or 0
        if (not portfolio or total_val == 0) and (positions_url or api_url.endswith("/summary")):
            fallback_url = positions_url or "/".join(api_url.split("/")[:-2]) + "/positions"
            try:
                pos_data = _get(fallback_url)
                if isinstance(pos_data, dict):
                    pos_list = pos_data.get("positions") or pos_data.get("portfolio") or (
                        pos_data if isinstance(pos_data, list) else []
                    )
                    if pos_list:
                        data = dict(data)
                        data["portfolio"] = pos_list
                        if not data.get("total_value") and pos_data.get("total_value"):
                            data["total_value"] = pos_data.get("total_value")
                        if not data.get("net_liquidation") and pos_data.get("net_liquidation"):
                            data["total_value"] = data.get("total_value") or pos_data.get("net_liquidation")
            except Exception:
                pass
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


def _ibkr_portfolio_preamble() -> str:
    """Texto previo: deja claro qué modo pide Duckclaw (paper por defecto para trading)."""
    mode = _ibkr_account_mode()
    return (
        f"Cuenta IBKR solicitada (env `IBKR_ACCOUNT_MODE`): **{mode}**. "
        "El snapshot numérico depende de que `IBKR_PORTFOLIO_API_URL` apunte a un servicio conectado al IB Gateway en **ese** modo.\n\n"
    )


def _extract_portfolio_context(data: Any) -> str:
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
            return (
                "Snapshot de cuenta IBKR no disponible (`snapshot_unavailable`). "
                "La URL `IBKR_PORTFOLIO_API_URL` respondió, pero el backend no obtuvo datos de cuenta/posiciones. "
                "Revisa en el **servidor donde corre la API** (no en el Mac del gateway DuckClaw) que el IB Gateway "
                "esté logueado en la misma modalidad que pide DuckClaw "
                f"(`IBKR_ACCOUNT_MODE` actual: **{_ibkr_account_mode()}**): "
                "desajuste paper vs live (p. ej. `IB_ENV=live` en la API mientras aquí pides paper) es la causa más frecuente. "
                "Comprueba también que el cliente API no consuma el único slot de sesión si hace falta otro client id."
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

    # region agent log
    try:
        _sample = portfolio[0] if isinstance(portfolio, list) and portfolio and isinstance(portfolio[0], dict) else {}
        _has_account_pnl = any(
            k in (data if isinstance(data, dict) else {})
            for k in ("unrealized_pnl", "realized_pnl", "total_pnl", "daily_pnl")
        )
        _sample_keys = list(_sample.keys())[:30] if isinstance(_sample, dict) else []
        _has_position_pnl = any(
            k in _sample_keys
            for k in (
                "unrealized_pnl",
                "realized_pnl",
                "daily_pnl",
                "pnl",
                "unrealizedPnL",
                "realizedPnL",
            )
        )
        with open(
            "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
            "a",
            encoding="utf-8",
        ) as _df:
            _df.write(
                json.dumps(
                    {
                        "sessionId": "c964f7",
                        "runId": "pre-fix",
                        "hypothesisId": "H1_ibkr_payload_has_pnl",
                        "location": "packages/agents/src/duckclaw/forge/skills/ibkr_bridge.py:_extract_portfolio_context",
                        "message": "ibkr_payload_shape",
                        "data": {
                            "portfolio_len": len(portfolio) if isinstance(portfolio, list) else 0,
                            "has_account_pnl": _has_account_pnl,
                            "has_position_pnl_sample": _has_position_pnl,
                            "sample_keys": _sample_keys,
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # endregion

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

    lines = [
        f"Estado: IBKR Gateway conectado (modo cuenta pedido: {_ibkr_account_mode()}).",
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
    # region agent log
    try:
        with open(
            "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
            "a",
            encoding="utf-8",
        ) as _df:
            _df.write(
                json.dumps(
                    {
                        "sessionId": "c964f7",
                        "runId": "pre-fix",
                        "hypothesisId": "H2_ibkr_render_contains_pnl",
                        "location": "packages/agents/src/duckclaw/forge/skills/ibkr_bridge.py:_extract_portfolio_context",
                        "message": "ibkr_render_has_pnl_tokens",
                        "data": {
                            "contains_pnl_word": ("pnl" in rendered.lower()),
                            "render_preview": rendered[:220],
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # endregion
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
        import urllib.request
        from urllib.error import HTTPError, URLError

        headers = _ibkr_portfolio_request_headers(api_key)

        def _get(url: str) -> Any:
            req = urllib.request.Request(url, headers=headers, method="GET")
            with urllib.request.urlopen(req, timeout=15.0) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))

        data = _get(api_url)
        portfolio = data.get("portfolio") or data.get("positions") or []
        total_val = data.get("total_value") or data.get("net_liquidation") or 0

        # Si summary devuelve vacío, intentar /api/positions (cash, sGOV pueden estar ahí)
        if (not portfolio or total_val == 0) and (
            positions_url or api_url.endswith("/summary")
        ):
            # /api/portfolio/summary -> /api/positions (según docs Capadonna)
            fallback_url = positions_url or "/".join(api_url.split("/")[:-2]) + "/positions"
            try:
                pos_data = _get(fallback_url)
                _log.info("[ibkr] summary vacío, fallback /positions | keys=%s", list(pos_data.keys()) if isinstance(pos_data, dict) else "?")
                # Combinar: positions puede ser lista o dict con portfolio
                pos_list = pos_data.get("positions") or pos_data.get("portfolio") or (pos_data if isinstance(pos_data, list) else [])
                if pos_list:
                    data = dict(data) if isinstance(data, dict) else {}
                    data["portfolio"] = pos_list
                    data["positions"] = pos_list
                    if not data.get("total_value") and pos_data.get("total_value"):
                        data["total_value"] = pos_data.get("total_value")
                    if not data.get("net_liquidation") and pos_data.get("net_liquidation"):
                        data["total_value"] = data.get("total_value") or pos_data.get("net_liquidation")
            except Exception as e:
                _log.warning("[ibkr] fallback /positions failed: %s", e)

        portfolio = data.get("portfolio") or data.get("positions") or []
        _log.info("[ibkr] API OK | total_value=%s | portfolio_len=%s | raw_keys=%s",
                  data.get("total_value"), len(portfolio),
                  list(data.keys())[:10] if isinstance(data, dict) else "?")
        if not portfolio and isinstance(data, dict):
            _log.info("[ibkr] Respuesta vacía. Revisa: 1) Capadonna usa IB_ENV=live (no paper) 2) IB Gateway conectado a cuenta live | sample=%r",
                      json.dumps(data, ensure_ascii=False)[:300])

        return _ibkr_portfolio_preamble() + _extract_portfolio_context(data)
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
            "Respeta `IBKR_ACCOUNT_MODE` (paper/live) vía cabecera hacia `IBKR_PORTFOLIO_API_URL`. "
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
