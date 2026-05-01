"""Detección de régimen macro (VIX, VSS, PGQ) — MOC Macro PGQ VSS."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any

from duckclaw.forge.atoms.investor_profile_vss import _search_semantic_memory_rows
from duckclaw.forge.models.core_satellite import MacroRegimeSnapshot

_MANUAL_ID = "singleton"
_MACRO_VSS_QUERY = "Fed tasas inflación régimen macro mercado riesgo VIX"


def _query_json_rows(db: Any, sql: str) -> list[dict[str, Any]]:
    raw = db.query(sql)
    rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
    return [r for r in rows if isinstance(r, dict)]


def query_pgq_assets_for_regime(
    db: Any,
    regime_name: str,
    edge_types: list[str],
    min_weight: float,
) -> list[str]:
    """
    Lista nombres de nodos ACTIVO con arista hacia `regime_name` (`dst`).
    """
    rg = (regime_name or "").strip().replace("'", "''")
    if not rg or not edge_types:
        return []
    ef = ",".join("'" + str(e).replace("'", "''") + "'" for e in edge_types)
    sql = f"""
    SELECT DISTINCT src.name AS activo
    FROM quant_core.macro_edges e
    JOIN quant_core.macro_nodes src ON src.id = e.src_node_id
    JOIN quant_core.macro_nodes dst ON dst.id = e.dst_node_id
    WHERE dst.name = '{rg}'
      AND lower(COALESCE(src.node_type, '')) = 'activo'
      AND e.edge_type IN ({ef})
      AND COALESCE(CAST(e.weight AS DOUBLE), 0) >= {float(min_weight)}
      AND (e.valid_until IS NULL OR e.valid_until > CURRENT_TIMESTAMP)
    ORDER BY activo
    """
    rows = _query_json_rows(db, sql)
    return [str(r.get("activo") or "").strip().upper() for r in rows if r.get("activo")]


def _read_manual_override(db: Any) -> tuple[str | None, float | None, str]:
    rows = _query_json_rows(
        db,
        "SELECT regime_override, confidence, evidence FROM quant_core.macro_manual_state "
        f"WHERE id = '{_MANUAL_ID}' LIMIT 1",
    )
    if not rows:
        return None, None, ""
    r0 = rows[0]
    ro = str(r0.get("regime_override") or "").strip() or None
    try:
        cf = float(r0.get("confidence")) if r0.get("confidence") is not None else None
    except (TypeError, ValueError):
        cf = None
    ev = str(r0.get("evidence") or "").strip()
    return ro, cf, ev


def _vix_last_close(db: Any) -> float | None:
    from duckclaw.forge.skills.quant_market_bridge import _fetch_ib_gateway_ohlcv_impl

    try:
        raw = _fetch_ib_gateway_ohlcv_impl(db, ticker="VIX", timeframe="1d", lookback_days=7)
    except Exception:
        raw = ""
    try:
        pj = json.loads(raw) if isinstance(raw, str) else {}
    except json.JSONDecodeError:
        pj = {}
    if isinstance(pj, dict) and pj.get("status") == "ok" and pj.get("last_close") is not None:
        try:
            return float(pj["last_close"])
        except (TypeError, ValueError):
            return None
    try:
        rows = _query_json_rows(
            db,
            "SELECT close FROM quant_core.ohlcv_data WHERE upper(ticker) IN ('VIX','^VIX') "
            "ORDER BY timestamp DESC LIMIT 1",
        )
    except Exception:
        rows = []
    if rows and rows[0].get("close") is not None:
        try:
            return float(rows[0]["close"])
        except (TypeError, ValueError):
            return None
    return None


def _classify_regime_from_vix(vix: float | None) -> tuple[str, float]:
    if vix is None:
        return "DESCONOCIDO", 0.0
    if vix > 30:
        return "REGIMEN_RISK_OFF", 0.9
    if vix > 20:
        return "REGIMEN_RISK_OFF", 0.6
    if vix < 15:
        return "REGIMEN_RISK_ON", 0.8
    return "REGIMEN_NEUTRAL", 0.5


def detect_current_regime(
    db: Any,
    tenant_id: str = "",
    *,
    vss_timeout_sec: float | None = None,
) -> dict[str, Any]:
    del tenant_id
    import os

    t_vss = vss_timeout_sec
    if t_vss is None:
        try:
            t_vss = max(0.5, float((os.environ.get("DUCKCLAW_MOC_VSS_TIMEOUT_SEC") or "3").strip()) / 2.0)
        except ValueError:
            t_vss = 1.5

    manual_reg, manual_conf, _manual_ev = _read_manual_override(db)

    if manual_reg:
        regime = manual_reg.strip().upper()
        conf = float(manual_conf) if manual_conf is not None else 0.85
        conf = max(0.0, min(1.0, conf))
        snap = MacroRegimeSnapshot(
            regime=regime,
            vix=None,
            confidence=conf,
            coherent_assets=query_pgq_assets_for_regime(
                db,
                regime,
                ["REFUGIO_DURANTE", "BENEFICIADO_POR", "CORRELACIONADO_EN"],
                0.6,
            ),
            contraindicated_assets=query_pgq_assets_for_regime(
                db,
                regime,
                ["CONTRAINDICADO_EN", "PRESIONADO_POR"],
                0.5,
            ),
            manual_override=True,
        )
        return snap.model_dump()

    vix = _vix_last_close(db)
    regime, conf = _classify_regime_from_vix(vix)

    def _macro_vss() -> list[str]:
        rows = _search_semantic_memory_rows(db, _MACRO_VSS_QUERY, 5)
        out: list[str] = []
        for row in rows:
            c = str(row.get("content") or "").strip()
            if c:
                out.append(c[:400])
        return out

    snippets: list[str] = []
    if t_vss and t_vss > 0:
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(_macro_vss)
            try:
                snippets = fut.result(timeout=t_vss)
            except FuturesTimeoutError:
                snippets = []
    else:
        snippets = _macro_vss()

    if snippets:
        conf = min(1.0, conf + 0.15)

    coherent = query_pgq_assets_for_regime(
        db, regime, ["REFUGIO_DURANTE", "BENEFICIADO_POR", "CORRELACIONADO_EN"], 0.6
    )
    contras = query_pgq_assets_for_regime(
        db, regime, ["CONTRAINDICADO_EN", "PRESIONADO_POR"], 0.5
    )

    return MacroRegimeSnapshot(
        regime=regime,
        vix=vix,
        confidence=conf,
        coherent_assets=coherent,
        contraindicated_assets=contras,
        macro_context_snippets=snippets[:2],
        manual_override=False,
    ).model_dump()
