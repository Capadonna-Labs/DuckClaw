"""Databento (historical market data, microstructure) over its official HTTP API: read-only, fixed host, per-query cost cap.

The key comes from Integraciones (``databento_api_key``) and is never returned. Every query asks ``metadata.get_cost`` first and
is refused when the estimate is above ``DUCKCLAW_DATABENTO_MAX_COST_USD`` (default 0.50), because book data is billed by volume.
"""

from __future__ import annotations

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Optional

_API_BASE = "https://hist.databento.com/v0"   # fixed: the tool never calls a host the model or the user typed
_SCHEMAS = ("trades", "tbbo", "mbp-1", "mbp-10", "ohlcv-1s", "ohlcv-1m", "ohlcv-1h", "ohlcv-1d")   # no mbo: a full day is gigabytes
_BOOK_SCHEMAS = ("trades", "tbbo", "mbp-1", "mbp-10")
_MAX_ROWS = 5000
_SHOWN_ROWS = 20
_MAX_BYTES = 8_000_000


def _max_cost_usd() -> float:
    try:
        return max(0.0, float(os.environ.get("DUCKCLAW_DATABENTO_MAX_COST_USD") or "0.5"))
    except ValueError:
        return 0.5


def _post(api_key: str, method: str, params: dict[str, str], *, timeout: float = 30.0) -> str:
    token = base64.b64encode(f"{api_key}:".encode()).decode()
    req = urllib.request.Request(
        f"{_API_BASE}/{method}", data=urllib.parse.urlencode(params).encode(), headers={"Authorization": f"Basic {token}"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:   # noqa: S310 fixed https host
        return resp.read(_MAX_BYTES).decode("utf-8", "replace")


def summarize_rows(schema: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compact microstructure view of the returned records (prices are already decimal, see ``pretty_px``)."""
    out: dict[str, Any] = {"registros": len(rows)}
    if schema not in _BOOK_SCHEMAS:
        out["velas"] = [{k: r.get(k) for k in ("ts_event", "open", "high", "low", "close", "volume")} for r in rows[:_SHOWN_ROWS]]
        return out
    trades = [r for r in rows if r.get("price") is not None and r.get("action") in (None, "T")]
    vol = sum(float(r.get("size") or 0) for r in trades)
    if trades and vol:
        out["operaciones"], out["volumen"] = len(trades), vol
        out["vwap"] = round(sum(float(r["price"]) * float(r.get("size") or 0) for r in trades) / vol, 6)
        buy = sum(float(r.get("size") or 0) for r in trades if r.get("side") == "B")   # B = the buyer is the aggressor
        sell = sum(float(r.get("size") or 0) for r in trades if r.get("side") == "A")
        out["volumen_comprador_agresor"], out["volumen_vendedor_agresor"] = buy, sell
        out["desbalance"] = round((buy - sell) / (buy + sell), 4) if buy + sell else None
    spreads, depth = [], []
    for r in rows:
        lv = (r.get("levels") or [r])[0]
        bid, ask = lv.get("bid_px_00", lv.get("bid_px")), lv.get("ask_px_00", lv.get("ask_px"))
        if bid and ask and float(ask) >= float(bid) > 0:
            spreads.append((float(ask) - float(bid), (float(ask) - float(bid)) / ((float(ask) + float(bid)) / 2) * 1e4))
        bs, as_ = lv.get("bid_sz_00", lv.get("bid_sz")), lv.get("ask_sz_00", lv.get("ask_sz"))
        if bs is not None and as_ is not None and float(bs) + float(as_) > 0:
            depth.append((float(bs) - float(as_)) / (float(bs) + float(as_)))
    if spreads:
        out["spread_medio"] = round(sum(s for s, _ in spreads) / len(spreads), 6)
        out["spread_medio_pb"] = round(sum(b for _, b in spreads) / len(spreads), 3)
    if depth:
        out["desbalance_mejor_nivel"] = round(sum(depth) / len(depth), 4)
    out["muestra"] = rows[:_SHOWN_ROWS]
    return out


def _databento_query_impl(
    db: Any, tenant_id: str, dataset: str, symbols: str, schema: str, start: str, end: str, limit: int = 1000, *, post: Any = None
) -> str:
    """Tool body. Errors name the cause, never the key."""
    from duckclaw.forge.skills.tailscale_bridge import _hub_db
    from duckclaw.integration_secrets import resolve_integration_api_key

    api_key = ""
    for handle in (db, _hub_db()):
        if handle is not None:
            api_key = resolve_integration_api_key("databento_api_key", db=handle, tenant_id=tenant_id)
        if api_key:
            break
    if not api_key:
        return "Databento no está configurado: falta la API key en Integraciones → Datos de mercado."
    if schema not in _SCHEMAS:
        return f"Esquema no permitido: usa uno de {', '.join(_SCHEMAS)}."
    limit = max(1, min(int(limit), _MAX_ROWS))
    params = {"dataset": dataset.strip(), "symbols": symbols.strip(), "schema": schema, "start": start.strip(), "end": end.strip(), "limit": str(limit)}
    call = post or _post
    try:
        cost = float(json.loads(call(api_key, "metadata.get_cost", params)))
        if cost > _max_cost_usd():
            return f"Consulta rechazada: costo estimado ${cost:.4f} sobre el tope ${_max_cost_usd():.2f}. Acorta la ventana, baja el límite o usa un esquema más ligero."
        raw = call(api_key, "timeseries.get_range", {**params, "encoding": "json", "pretty_px": "true", "pretty_ts": "true", "map_symbols": "true"})
    except urllib.error.HTTPError as exc:
        hint = {401: "la API key es inválida", 403: "la clave no tiene acceso a ese dataset", 422: "parámetros inválidos (dataset, símbolo o fechas)", 429: "límite de uso alcanzado"}.get(exc.code, "error de la API")
        return f"Databento respondió {exc.code}: {hint}."
    except Exception as exc:  # noqa: BLE001
        return f"No se pudo consultar Databento ({type(exc).__name__})."
    rows = [json.loads(line) for line in raw.splitlines() if line.strip()]
    return json.dumps({"costo_usd": round(cost, 6), **summarize_rows(schema, [r for r in rows if isinstance(r, dict)])}, ensure_ascii=False, default=str)


def _databento_tool(config: Optional[dict], *, db: Any = None, tenant_id: str = "default") -> Optional[Any]:
    if (config or {}).get("enabled") is False:
        return None
    from langchain_core.tools import StructuredTool

    def _run(dataset: str, symbols: str, schema: str, start: str, end: str, limit: int = 1000) -> str:
        return _databento_query_impl(db, tenant_id, dataset, symbols, schema, start, end, limit)

    return StructuredTool.from_function(
        _run,
        name="databento_query",
        description=(
            "Microestructura histórica vía la API oficial de Databento (solo lectura, con tope de costo por consulta). "
            f"schema: {', '.join(_SCHEMAS)} (trades = operaciones; tbbo/mbp-1 = mejor nivel del libro; mbp-10 = 10 niveles). "
            "dataset p. ej. XNAS.ITCH, GLBX.MDP3; symbols separados por coma; start/end en ISO 8601 UTC. "
            "Devuelve spread, VWAP, desbalance de agresores y una muestra. Pide ventanas cortas: se cobra por volumen."
        ),
    )


def register_databento_skill(tools_list: list[Any], databento_config: Optional[dict] = None, *, db: Any = None, tenant_id: str = "default") -> None:
    """Offered only when the manifest has skills.databento; without a stored key the tool answers with how to configure it."""
    if not databento_config:
        return
    try:
        tool = _databento_tool(databento_config, db=db, tenant_id=tenant_id)
        if tool:
            tools_list.append(tool)
    except Exception:  # noqa: BLE001
        pass
