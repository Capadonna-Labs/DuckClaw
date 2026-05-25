"""
IBKR Bridge — consulta read-only del portafolio de Interactive Brokers.

Spec: Integración de Contexto IBKR (Read-Only Portfolio API)
Requiere: IBKR_PORTFOLIO_API_URL e IBKR_PORTFOLIO_API_KEY en el entorno.
"""

from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Literal, Optional, Tuple

from duckclaw.utils.logger import log_tool_execution_sync

_log = logging.getLogger(__name__)


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


_DU_PAPER_ACCOUNT_ID = re.compile(r"^DU\d+$", re.IGNORECASE)


def _ibkr_normalize_mode_token(raw: str) -> Optional[Literal["paper", "live"]]:
    s = raw.strip().lower()
    if s in ("paper", "demo", "sim", "simulation", "sandbox"):
        return "paper"
    if s in ("live", "real", "production"):
        return "live"
    return None


def _ibkr_infer_snapshot_account_mode(data: Any) -> Optional[Literal["paper", "live"]]:
    """
    Mejor esfuerzo: modo económico del snapshot según el JSON del servicio (no la cabecera enviada).
    IBKR suele usar cuentas paper con id tipo DU######.
    """
    if not isinstance(data, dict):
        return None

    def _from_dict(d: dict[str, Any]) -> Optional[Literal["paper", "live"]]:
        for key in (
            "account_mode",
            "ib_account_mode",
            "snapshot_account_mode",
            "ib_env",
            "ib_env_mode",
            "environment",
            "trading_mode",
            "account_type",
        ):
            v = d.get(key)
            if isinstance(v, str):
                m = _ibkr_normalize_mode_token(v)
                if m:
                    return m
        if d.get("paper") is True or d.get("is_paper") is True:
            return "paper"
        if d.get("paper") is False or d.get("is_paper") is False:
            return "live"
        for key in ("account_id", "accountId", "account", "acct_id", "acctId", "ib_account"):
            v = d.get(key)
            if isinstance(v, str) and _DU_PAPER_ACCOUNT_ID.match(v.strip()):
                return "paper"
            if isinstance(v, dict):
                for ak in ("accountId", "account_id", "id", "acctId"):
                    aid = v.get(ak)
                    if isinstance(aid, str) and _DU_PAPER_ACCOUNT_ID.match(aid.strip()):
                        return "paper"
        return None

    got = _from_dict(data)
    if got:
        return got
    inner = data.get("data")
    if isinstance(inner, dict):
        got = _from_dict(inner)
        if got:
            return got

    def _walk(obj: Any, depth: int) -> Optional[Literal["paper", "live"]]:
        if depth > 3:
            return None
        if isinstance(obj, dict):
            for vv in obj.values():
                if isinstance(vv, str) and _DU_PAPER_ACCOUNT_ID.match(vv.strip()):
                    return "paper"
                r = _walk(vv, depth + 1)
                if r:
                    return r
        elif isinstance(obj, list):
            for it in obj[:40]:
                r = _walk(it, depth + 1)
                if r:
                    return r
        return None

    return _walk(data, 0)


def _finanz_env_assumed_snapshot_mode() -> Optional[Literal["paper", "live"]]:
    """Override local cuando el JSON del servicio no declara modo (p. ej. observability sin `account_id`)."""
    raw = (os.environ.get("IBKR_FINANZ_ASSUMED_SNAPSHOT_MODE") or "").strip().lower()
    if raw in ("paper", "live"):
        return raw  # type: ignore[return-value]
    return None


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


def _ibkr_resolve_payload_live_only(
    api_url: str,
    api_key: str,
    positions_url: str,
) -> tuple[dict[str, Any], str, str]:
    """
    Un solo GET en modo **live** (cuenta real). Sin reintento al modo paper:
    uso del worker Finanz para no mezclar números de simulación con cuenta live.
    """
    data = _ibkr_fetch_portfolio_payload(api_url, api_key, positions_url, "live")
    return data, "live", "live"


def finanz_active_paper_quant_session_notice(
    finanz_db_path: str,
    *,
    ibkr_numeric_snapshot_shown: bool = True,
) -> str:
    """
    Si en la bóveda Finanz existe `quant_core.trading_sessions` (id=active) en
    status ACTIVE y mode paper, devuelve un aviso breve para la respuesta al usuario.

    ``ibkr_numeric_snapshot_shown``: False cuando Finanz omitió montos IBKR (cuenta paper).
    """
    p = (finanz_db_path or "").strip()
    if not p:
        return ""
    try:
        from duckclaw import DuckClaw

        with DuckClaw(p, read_only=True) as db_ro:
            raw = db_ro.query(
                "SELECT mode, status, tickers FROM quant_core.trading_sessions "
                "WHERE id = 'active' LIMIT 1"
            )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if not rows or not isinstance(rows[0], dict):
            return ""
        row = rows[0]
        if str(row.get("status") or "").strip().upper() != "ACTIVE":
            return ""
        if str(row.get("mode") or "").strip().lower() != "paper":
            return ""
        tickers = str(row.get("tickers") or "").strip()
        tick_part = f" Tickers sesión: {tickers}." if tickers else ""
        if ibkr_numeric_snapshot_shown:
            ibkr_part = (
                "El bloque IBKR de arriba es **solo cuenta live** (real); no lo interpretes como "
                "saldo del playbook en simulación."
            )
        else:
            ibkr_part = (
                "En este turno **no hay cifras del broker** en el mensaje (Gateway en cuenta paper). "
                "El playbook Quant en paper es aparte."
            )
        return (
            "\n\n---\n**Aviso (Finanz):** hay una **sesión de trading Quant en modo paper** "
            "registrada como ACTIVA en tu DuckDB (`quant_core.trading_sessions`)."
            f"{tick_part} {ibkr_part} Para el ciclo paper usa el bot/worker Quant.\n"
        )
    except Exception:
        return ""


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
    data = _ibkr_fetch_portfolio_payload(api_url, api_key, positions_url, configured)
    effective = configured
    fb = (os.environ.get("IBKR_ACCOUNT_MODE_ALT_FALLBACK") or "1").strip().lower()
    if fb in ("0", "false", "no"):
        return data, effective, configured
    # Solo reintento ante snapshot_unavailable (desajuste paper/live frecuente en Capadonna).
    if _ibkr_error_suggests_mode_mismatch(data):
        alt = "live" if configured == "paper" else "paper"
        data_alt = _ibkr_fetch_portfolio_payload(api_url, api_key, positions_url, alt)
        if _ibkr_snapshot_has_substance(data_alt):
            data = data_alt
            effective = alt
            _log.info(
                "[ibkr] snapshot_unavailable en modo %s; usando datos de modo %s",
                configured,
                effective,
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


def fetch_ibkr_unrealized_pnl_total_numeric() -> Tuple[Optional[float], str]:
    """
    Suma unrealized_pnl de todas las posiciones del snapshot IBKR (mismo contrato que get_ibkr_portfolio).
    Retorna (suma, "") si hay payload usable; (None, mensaje) si falla configuración o red.
    Si el snapshot no trae unrealized por posición, retorna (0.0, "").
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
        if not portfolio or not isinstance(portfolio, list):
            return 0.0, ""
        agg = 0.0
        has_any = False
        for pos in portfolio:
            if not isinstance(pos, dict):
                continue
            u = (
                pos.get("unrealized_pnl")
                if pos.get("unrealized_pnl") is not None
                else pos.get("unrealizedPnL")
            )
            if u is not None and str(u).strip() != "":
                try:
                    agg += float(u)
                    has_any = True
                except (TypeError, ValueError):
                    pass
        if not has_any:
            return 0.0, ""
        return agg, ""
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
    _exec_note = (
        "**Nota:** este snapshot es solo la API de posiciones (`IBKR_PORTFOLIO_API_URL`); "
        "las ejecuciones van por el hook/servicio de ordenes. Un fill reciente puede no verse al instante aqui, "
        "o no coincidir si portfolio y ejecucion apuntan a distinta cuenta o instancia de Gateway.\n\n"
    )
    if effective_mode != configured_mode:
        return (
            f"Cuenta IBKR: snapshot en modo **{effective_mode}** "
            f"(env `IBKR_ACCOUNT_MODE` era **{configured_mode}**; ese modo devolvió `snapshot_unavailable` y se reintentó en **{effective_mode}**). "
            f"Para evitar el reintento, define `IBKR_ACCOUNT_MODE={effective_mode}` alineado al IB Gateway.\n\n"
            + _exec_note
        )
    return (
        f"Cuenta IBKR solicitada (env `IBKR_ACCOUNT_MODE`): **{effective_mode}**. "
        "El snapshot numérico depende de que `IBKR_PORTFOLIO_API_URL` apunte a un servicio conectado al IB Gateway en **ese** modo.\n\n"
        + _exec_note
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


def _finanz_ibkr_session_mode(finanz_db_path: str) -> tuple[bool, Literal["paper", "live"] | None]:
    """
    Lee ``ibkr_enabled`` / ``ibkr_portfolio_mode`` del chat actual (``/ibkr`` fly command).
    Retorna (habilitado, modo solicitado).
    """
    from duckclaw import DuckClaw
    from duckclaw.forge.skills.quant_tool_context import get_quant_tool_chat_id
    from duckclaw.graphs.on_the_fly_commands import get_chat_state

    chat_id = get_quant_tool_chat_id()
    if not chat_id:
        return False, None
    p = (finanz_db_path or "").strip()
    if not p:
        return False, None
    try:
        with DuckClaw(p, read_only=True) as db_ro:
            enabled_raw = (get_chat_state(db_ro, chat_id, "ibkr_enabled") or "").strip().lower()
            mode_raw = (get_chat_state(db_ro, chat_id, "ibkr_portfolio_mode") or "").strip().lower()
    except Exception:
        return False, None
    if enabled_raw not in ("true", "1", "on", "sí", "si"):
        return False, None
    mode: Literal["paper", "live"] | None
    if mode_raw in ("paper", "live"):
        mode = mode_raw  # type: ignore[assignment]
    else:
        mode = "paper"
    return True, mode


def _get_ibkr_portfolio_finanz_impl(finanz_db_path: str) -> str:
    """
    Variante **Finanz**: requiere ``/ibkr on --mode paper|live`` en el chat.
    Usa la cabecera del modo elegido; en paper muestra el snapshot paper (sin suprimir saldos).
    """
    enabled, session_mode = _finanz_ibkr_session_mode(finanz_db_path)
    if not enabled or session_mode is None:
        return (
            "IBKR portfolio deshabilitado en esta sesión. "
            "Actívalo con `/ibkr on --mode paper` o `/ibkr on --mode live`."
        )

    api_url = os.environ.get("IBKR_PORTFOLIO_API_URL", "").strip()
    api_key = os.environ.get("IBKR_PORTFOLIO_API_KEY", "").strip()
    positions_url = os.environ.get("IBKR_PORTFOLIO_POSITIONS_URL", "").strip()

    if not api_url or not api_key:
        _log.warning("[ibkr] Credenciales no configuradas (IBKR_PORTFOLIO_API_URL/KEY)")
        return "Error de configuración: Las credenciales de la API de IBKR no están configuradas en el entorno."

    notice_err = finanz_active_paper_quant_session_notice(
        finanz_db_path, ibkr_numeric_snapshot_shown=(session_mode == "live")
    )
    try:
        from urllib.error import HTTPError, URLError

        data = _ibkr_fetch_portfolio_payload(api_url, api_key, positions_url, session_mode)
        effective = session_mode
        configured = session_mode
        portfolio = data.get("portfolio") or data.get("positions") or []
        plen = len(portfolio) if isinstance(portfolio, list) else 0
        inferred = _ibkr_infer_snapshot_account_mode(data)
        assumed = _finanz_env_assumed_snapshot_mode()
        economic: Optional[Literal["paper", "live"]]
        if inferred in ("paper", "live"):
            economic = inferred
        elif assumed in ("paper", "live"):
            economic = assumed
        else:
            economic = None

        _log.info(
            "[ibkr/finanz] API OK (live-only) | effective_mode=%s | inferred=%s | assumed=%s | economic=%s | total_value=%s | portfolio_len=%s",
            effective,
            inferred,
            assumed,
            economic,
            data.get("total_value"),
            plen,
        )

        if session_mode == "paper":
            pre = (
                "**Finanz — cuenta IBKR (paper):** sesión con `/ibkr on --mode paper`.\n\n"
            )
            body = _extract_portfolio_context(data, account_mode_for_display="paper")
            return pre + body + finanz_active_paper_quant_session_notice(
                finanz_db_path, ibkr_numeric_snapshot_shown=False
            )

        if economic == "paper":
            _log.warning(
                "[ibkr/finanz] Sesión live pero el JSON sugiere cuenta paper — se muestran datos del snapshot"
            )
        if inferred == "live":
            display_mode = "live"
            pre = (
                "**Finanz — cuenta IBKR (live):** sesión `/ibkr on --mode live`; "
                "el servicio declaró snapshot **live** en el JSON.\n\n"
            )
        elif economic is None:
            display_mode = "no verificado (API sin metadatos de cuenta)"
            pre = (
                "**Finanz — cuenta IBKR (modo no verificado):** sesión `/ibkr on --mode live`; "
                "la respuesta no declara modo de cuenta de forma fiable.\n\n"
            )
        else:
            display_mode = "live"
            pre = "**Finanz — cuenta IBKR (live):** sesión `/ibkr on --mode live`.\n\n"

        body = _extract_portfolio_context(data, account_mode_for_display=display_mode)
        return pre + body + finanz_active_paper_quant_session_notice(
            finanz_db_path, ibkr_numeric_snapshot_shown=True
        )
    except HTTPError as e:
        _log.warning("[ibkr/finanz] HTTP %s: %s", e.code, e.reason)
        return (
            "Error de conexión: El Gateway de IBKR está desconectado en este momento. "
            "No puedo acceder a los datos de tu portafolio de inversiones."
            + notice_err
        )
    except URLError as e:
        _log.warning("[ibkr/finanz] URLError: %s", e.reason)
        if "timed out" in str(e.reason).lower() or "timeout" in str(e.reason).lower():
            return "Error de conexión: Timeout al conectar con el servidor de IBKR. Intenta más tarde." + notice_err
        return (
            "Error de conexión: El Gateway de IBKR está desconectado en este momento. "
            "No puedo acceder a los datos de tu portafolio de inversiones."
            + notice_err
        )
    except (TimeoutError, OSError) as e:
        _log.warning("[ibkr/finanz] Timeout/OSError: %s", e)
        if "timed out" in str(e).lower() or "timeout" in type(e).__name__.lower():
            return "Error de conexión: Timeout al conectar con el servidor de IBKR. Intenta más tarde." + notice_err
        return (
            "Error de conexión: El Gateway de IBKR está desconectado en este momento. "
            "No puedo acceder a los datos de tu portafolio de inversiones."
            + notice_err
        )
    except json.JSONDecodeError as e:
        _log.warning("[ibkr/finanz] JSON decode error: %s", e)
        return "Error interno: La API de IBKR devolvió una respuesta no válida." + notice_err
    except Exception as e:
        _log.exception("[ibkr/finanz] Unexpected error")
        return f"Error interno al procesar el portafolio: {str(e)}" + notice_err


def replace_get_ibkr_portfolio_with_finanz_live_variant(tools: list[Any], finanz_db_path: str) -> None:
    """Sustituye la tool estándar por la variante live-only + aviso sesión paper Quant."""
    from langchain_core.tools import StructuredTool

    db_path = str(finanz_db_path or "").strip()
    if not db_path:
        return

    for i, t in enumerate(tools):
        if getattr(t, "name", None) != "get_ibkr_portfolio":
            continue

        def _finanz_ibkr_call() -> str:
            return _get_ibkr_portfolio_finanz_impl(db_path)

        tools[i] = StructuredTool.from_function(
            _finanz_ibkr_call,
            name="get_ibkr_portfolio",
            description=(
                "Broker IBKR (solo si el usuario activó `/ibkr on --mode paper|live` en este chat). "
                "Consulta posiciones y saldo según el modo de sesión (paper o live). "
                "OBLIGATORIO cuando el usuario pide resumen amplio de cuentas con broker y IBKR está activo. "
                "Ignora read_sql para posiciones que solo existen en IBKR."
            ),
        )
        return


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
