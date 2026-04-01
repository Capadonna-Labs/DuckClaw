"""
Registro del estado CFD (Cyber-Fluid Dynamics) en quant_core.fluid_state.

Spec: specs/features/Cyber-Fluid Dynamics CFD (Finanz).md
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Optional

from duckclaw.utils.logger import log_tool_execution_sync

_log = logging.getLogger(__name__)

_VALID_PHASES = frozenset({"SOLID", "LIQUID", "GAS", "PLASMA"})


def _norm_phase(raw: str) -> Optional[str]:
    p = (raw or "").strip().upper()
    return p if p in _VALID_PHASES else None


def _compute_hex_signature(
    ticker: str,
    ts: str,
    phase: str,
    mass: Optional[float],
    density: Optional[float],
    temperature: Optional[float],
    pressure: Optional[float],
    viscosity: Optional[float],
    surface_tension: Optional[float],
) -> str:
    payload = {
        "ticker": ticker.upper(),
        "timestamp": ts,
        "phase": phase,
        "mass": mass,
        "density": density,
        "temperature": temperature,
        "pressure": pressure,
        "viscosity": viscosity,
        "surface_tension": surface_tension,
    }
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


@log_tool_execution_sync(name="record_fluid_state")
def _record_fluid_state_impl(
    db: Any,
    *,
    ticker: str,
    phase: str,
    timestamp: str = "",
    hex_signature: str = "",
    mass: Optional[float] = None,
    density: Optional[float] = None,
    temperature: Optional[float] = None,
    pressure: Optional[float] = None,
    viscosity: Optional[float] = None,
    surface_tension: Optional[float] = None,
) -> str:
    tkr = (ticker or "").strip().upper()
    ph = _norm_phase(phase)
    if not tkr:
        return json.dumps({"error": "ticker obligatorio."}, ensure_ascii=False)
    if not ph:
        return json.dumps(
            {"error": f"phase debe ser uno de: {sorted(_VALID_PHASES)}"},
            ensure_ascii=False,
        )

    ts = (timestamp or "").strip()
    if not ts:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

    hx = (hex_signature or "").strip()
    if not hx:
        hx = _compute_hex_signature(
            tkr, ts, ph, mass, density, temperature, pressure, viscosity, surface_tension
        )

    try:
        db.execute(
            """
            INSERT INTO quant_core.fluid_state (
                ticker, timestamp, hex_signature,
                mass, density, temperature, pressure, viscosity, surface_tension, phase
            )
            VALUES (?, CAST(? AS TIMESTAMP), ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker, timestamp) DO UPDATE SET
                hex_signature = excluded.hex_signature,
                mass = excluded.mass,
                density = excluded.density,
                temperature = excluded.temperature,
                pressure = excluded.pressure,
                viscosity = excluded.viscosity,
                surface_tension = excluded.surface_tension,
                phase = excluded.phase
            """,
            (tkr, ts, hx, mass, density, temperature, pressure, viscosity, surface_tension, ph),
        )
    except Exception as e:
        _log.warning("[quant_cfd] insert fluid_state failed: %s", e)
        return json.dumps({"error": str(e)}, ensure_ascii=False)

    return json.dumps(
        {
            "status": "ok",
            "ticker": tkr,
            "timestamp": ts,
            "phase": ph,
            "hex_signature": hx,
        },
        ensure_ascii=False,
    )


def register_quant_cfd_skill(db: Any, spec: Any, tools: list[Any]) -> None:
    from langchain_core.tools import StructuredTool

    def _run(
        ticker: str,
        phase: str,
        timestamp: str = "",
        hex_signature: str = "",
        mass: Optional[float] = None,
        density: Optional[float] = None,
        temperature: Optional[float] = None,
        pressure: Optional[float] = None,
        viscosity: Optional[float] = None,
        surface_tension: Optional[float] = None,
    ) -> str:
        return _record_fluid_state_impl(
            db,
            ticker=ticker,
            phase=phase,
            timestamp=timestamp,
            hex_signature=hex_signature,
            mass=mass,
            density=density,
            temperature=temperature,
            pressure=pressure,
            viscosity=viscosity,
            surface_tension=surface_tension,
        )

    tools.append(
        StructuredTool.from_function(
            _run,
            name="record_fluid_state",
            description=(
                "Persiste un snapshot CFD en quant_core.fluid_state (Cyber-Fluid Dynamics). "
                "fases: SOLID|LIQUID|GAS|PLASMA. Opcionales: mass, density, temperature, pressure, "
                "viscosity, surface_tension (métricas típicamente de run_sandbox). "
                "timestamp opcional; hex_signature opcional (se deriva si vacío). "
                "Tras calcular el reactor en sandbox, usa esto para auditoría del estado del fluido."
            ),
        )
    )
