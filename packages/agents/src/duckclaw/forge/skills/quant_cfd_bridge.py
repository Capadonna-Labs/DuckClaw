"""
Registro del estado CFD (Cyber-Fluid Dynamics) en quant_core.fluid_state.

Spec: specs/features/finanz/FINANZ_CFD_CYBER_FLUID.md
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from duckclaw.utils.logger import log_tool_execution_sync

_log = logging.getLogger(__name__)

_VALID_PHASES = frozenset({"SOLID", "LIQUID", "GAS", "PLASMA"})

_FLUID_STATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS quant_core.fluid_state (
    ticker VARCHAR NOT NULL,
    timestamp TIMESTAMP NOT NULL,
    hex_signature VARCHAR NOT NULL,
    mass DOUBLE,
    density DOUBLE,
    temperature DOUBLE,
    pressure DOUBLE,
    viscosity DOUBLE,
    surface_tension DOUBLE,
    delta DOUBLE,
    gamma DOUBLE,
    vega DOUBLE,
    theta DOUBLE,
    phase VARCHAR NOT NULL,
    PRIMARY KEY (ticker, timestamp)
)
"""
_FLUID_STATE_INDEX_SQL = (
    "CREATE INDEX IF NOT EXISTS idx_fluid_state_ticker ON quant_core.fluid_state (ticker)"
)
# Migración idempotente: DuckDB admite una sola orden ALTER por statement; encadenar con ';'.
_FLUID_STATE_ALTER_GREEKS_SQL = (
    "ALTER TABLE quant_core.fluid_state ADD COLUMN IF NOT EXISTS delta DOUBLE; "
    "ALTER TABLE quant_core.fluid_state ADD COLUMN IF NOT EXISTS gamma DOUBLE; "
    "ALTER TABLE quant_core.fluid_state ADD COLUMN IF NOT EXISTS vega DOUBLE; "
    "ALTER TABLE quant_core.fluid_state ADD COLUMN IF NOT EXISTS theta DOUBLE"
)
# Un solo execute (db-writer / duckdb) para bootstrap en modo RO vía cola
_FLUID_STATE_DDL_BUNDLE = (
    "CREATE SCHEMA IF NOT EXISTS quant_core; "
    + _FLUID_STATE_TABLE_SQL.strip()
    + "; "
    + _FLUID_STATE_ALTER_GREEKS_SQL.strip()
    + "; "
    + _FLUID_STATE_INDEX_SQL.strip()
    + ";"
)


def _infer_user_id_for_writer(db_path: str) -> str:
    parts = Path(db_path).expanduser().resolve().parts
    if "private" in parts:
        i = parts.index("private")
        if i + 1 < len(parts):
            return str(parts[i + 1])
    return "default"


def _enqueue_mutation(
    db: Any,
    *,
    sql: str,
    params: list[Any] | None = None,
) -> tuple[bool, str | None]:
    """
    Escritura DuckDB: inline si RW, si no encola a DuckClaw-DB-Writer
    (mismo patrón que `quant_market_bridge._persist_ohlcv` / PQRSD).
    """
    path = str(getattr(db, "_path", "") or "").strip()
    if not path or path == ":memory:":
        return False, "sin_ruta_duckdb"
    ro = bool(getattr(db, "_read_only", False))
    if not ro:
        try:
            stmt = sql.strip()
            pl = list(params or [])
            if pl:
                db.execute(stmt, pl)
            else:
                db.execute(stmt)
            return True, None
        except Exception as e:
            return False, str(e)[:500]
    from duckclaw.db_write_queue import enqueue_duckdb_write_sync, poll_task_status_sync

    resolved = str(Path(path).expanduser().resolve())
    uid = _infer_user_id_for_writer(resolved)
    released_ro = False
    resu = getattr(db, "resume_readonly_file_handle", None)
    try:
        susp = getattr(db, "suspend_readonly_file_handle", None)
        if callable(susp) and callable(resu):
            susp()
            released_ro = True
        task_id = enqueue_duckdb_write_sync(
            db_path=resolved,
            query=sql.strip(),
            params=list(params or []),
            user_id=uid,
            tenant_id="default",
        )
        poll_to = 20.0 if released_ro else 5.0
        st = poll_task_status_sync(task_id, timeout_sec=poll_to)
        if st is None:
            return False, "timeout db-writer"
        if st.status != "success":
            return False, (st.detail or "db-writer falló")[:500]
        return True, None
    except Exception as e:
        return False, str(e)[:500]
    finally:
        if released_ro and callable(resu):
            try:
                resu()
            except Exception:
                pass


def _ensure_fluid_state_table(db: Any) -> None:
    """Solo para conexión RW. En RO el DDL se envía vía _enqueue_mutation (no puede execute DDL)."""
    if bool(getattr(db, "_read_only", False)):
        return
    try:
        db.execute("CREATE SCHEMA IF NOT EXISTS quant_core")
    except Exception:
        pass
    try:
        db.execute(_FLUID_STATE_TABLE_SQL)
    except Exception:
        pass
    try:
        db.execute(_FLUID_STATE_ALTER_GREEKS_SQL.strip())
    except Exception:
        pass
    try:
        db.execute(_FLUID_STATE_INDEX_SQL)
    except Exception:
        pass


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
    delta: Optional[float] = None,
    gamma: Optional[float] = None,
    vega: Optional[float] = None,
    theta: Optional[float] = None,
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
        "delta": delta,
        "gamma": gamma,
        "vega": vega,
        "theta": theta,
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
    delta: Optional[float] = None,
    gamma: Optional[float] = None,
    vega: Optional[float] = None,
    theta: Optional[float] = None,
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
            tkr,
            ts,
            ph,
            mass,
            density,
            temperature,
            pressure,
            viscosity,
            surface_tension,
            delta,
            gamma,
            vega,
            theta,
        )

    ro = bool(getattr(db, "_read_only", False))
    insert_sql = """
            INSERT INTO quant_core.fluid_state (
                ticker, timestamp, hex_signature,
                mass, density, temperature, pressure, viscosity, surface_tension,
                delta, gamma, vega, theta, phase
            )
            VALUES (?, CAST(? AS TIMESTAMP), ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (ticker, timestamp) DO UPDATE SET
                hex_signature = excluded.hex_signature,
                mass = excluded.mass,
                density = excluded.density,
                temperature = excluded.temperature,
                pressure = excluded.pressure,
                viscosity = excluded.viscosity,
                surface_tension = excluded.surface_tension,
                delta = excluded.delta,
                gamma = excluded.gamma,
                vega = excluded.vega,
                theta = excluded.theta,
                phase = excluded.phase
            """
    insert_params = [
        tkr,
        ts,
        hx,
        mass,
        density,
        temperature,
        pressure,
        viscosity,
        surface_tension,
        delta,
        gamma,
        vega,
        theta,
        ph,
    ]

    if ro:
        ok, err = _enqueue_mutation(db, sql=_FLUID_STATE_DDL_BUNDLE, params=None)
        if not ok:
            _log.warning("[quant_cfd] fluid_state DDL (RO cola) falló: %s", err)
            return json.dumps({"error": err or "fluid_state_ddl_failed"}, ensure_ascii=False)
    else:
        _ensure_fluid_state_table(db)

    try:
        if ro:
            ok, err = _enqueue_mutation(db, sql=insert_sql.strip(), params=insert_params)
            if not ok:
                _log.warning("[quant_cfd] insert fluid_state failed: %s", err)
                return json.dumps({"error": err or "insert_failed"}, ensure_ascii=False)
        else:
            db.execute(insert_sql, insert_params)
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
        delta: Optional[float] = None,
        gamma: Optional[float] = None,
        vega: Optional[float] = None,
        theta: Optional[float] = None,
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
            delta=delta,
            gamma=gamma,
            vega=vega,
            theta=theta,
        )

    tools.append(
        StructuredTool.from_function(
            _run,
            name="record_fluid_state",
            description=(
                "Persiste un snapshot CFD en quant_core.fluid_state (Cyber-Fluid Dynamics). "
                "fases: SOLID|LIQUID|GAS|PLASMA. Opcionales: mass, density, temperature, pressure, "
                "viscosity, surface_tension (métricas típicamente de run_sandbox). "
                "Opcionales BSM sintético (float | None, default None): delta, gamma, vega, theta — "
                "p. ej. desde calculate_synthetic_greeks + persistencia en esta tool. "
                "timestamp opcional; hex_signature opcional (se deriva si vacío). "
                "Tras calcular el reactor en sandbox, usa esto para auditoría del estado del fluido."
            ),
        )
    )
