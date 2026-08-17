"""Position metrics skill — deterministic SL/TP / PnL / deleveraging tools."""

from __future__ import annotations

import json
from typing import Any, Optional

from langchain_core.tools import StructuredTool


def register_position_metrics_skill(
    tools_list: list[Any],
    position_metrics_config: Optional[dict] = None,
) -> None:
    """Register arithmetic tools. Config empty dict is enough to enable."""
    cfg = position_metrics_config if isinstance(position_metrics_config, dict) else {}
    if cfg.get("enabled") is False:
        return

    from duckclaw.position_metrics import (
        calculate_deleveraging_tranche,
        calculate_pnl_contribution,
        calculate_tp_sl_distance,
    )

    def _tp_sl(price: float, sl: float, tp: float) -> str:
        """Distancias % unsigned a SL/TP + RR. Copia el JSON; no recalcules signos."""
        return json.dumps(
            calculate_tp_sl_distance(price, sl, tp),
            ensure_ascii=False,
        )

    def _pnl_contrib(pnl: float, portfolio_pnl: float) -> str:
        """% contribución de un ticker al PnL del portfolio. Copia el JSON."""
        return json.dumps(
            calculate_pnl_contribution(pnl, portfolio_pnl),
            ensure_ascii=False,
        )

    def _delev(current_pct: float, target_pct: float, steps_remaining: int) -> str:
        """Tramo en puntos % hacia target de exposición. Copia el JSON."""
        return json.dumps(
            calculate_deleveraging_tranche(current_pct, target_pct, steps_remaining),
            ensure_ascii=False,
        )

    tools_list.append(
        StructuredTool.from_function(
            _tp_sl,
            name="calculate_tp_sl_distance",
            description=(
                "[Position metrics] Distancia % a SL y TP (magnitudes positivas) + rr_ratio + side. "
                "Cuándo: reportes /loop P4 o cualquier cita de distancia a stop/take-profit. "
                "NO calcules % en prosa: invoca esta tool y copia dist_sl_pct/dist_tp_pct/rr_ratio "
                "tal cual del JSON. Args: price, sl, tp (números)."
            ),
        )
    )
    tools_list.append(
        StructuredTool.from_function(
            _pnl_contrib,
            name="calculate_pnl_contribution",
            description=(
                "[Position metrics] % contribución de un ticker al PnL del portfolio. "
                "Cuándo: desglose de PnL por nombre en /loop. "
                "NO dividas en prosa: copia contribution_pct del JSON. "
                "Args: pnl (ticker), portfolio_pnl (total)."
            ),
        )
    )
    tools_list.append(
        StructuredTool.from_function(
            _delev,
            name="calculate_deleveraging_tranche",
            description=(
                "[Position metrics] Tamaño de tramo (puntos %) en plan de deleveraging. "
                "Cuándo: pasos restantes hacia target de exposición. "
                "Copia tranche_pct_points del JSON. "
                "Args: current_pct, target_pct, steps_remaining (entero >= 1)."
            ),
        )
    )
