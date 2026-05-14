"""
Streamlit dashboard for libedgecore telemetry.

Run from the monorepo root after ``uv sync`` for this project::

    uv run --project integrations/edge-devices streamlit run \\
      integrations/edge-devices/src/duckclaw_edge_devices/app.py
"""

from __future__ import annotations

import sys
import time
from datetime import timedelta
from pathlib import Path
from typing import Any

# Allow ``streamlit run .../app.py`` without a prior editable install.
_src = Path(__file__).resolve().parents[1]
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import pandas as pd
import streamlit as st

from duckclaw_edge_devices.client import (
    EdgeTelemetry,
    close_serial,
    load_edge_core,
    open_serial,
    read_telemetry,
)

_DEFAULT_SCHEMA = (
    "cpu_load_1m,cpu_load_5m,cpu_load_15m,ram_total_mb,ram_free_mb,"
    "slot_6,slot_7,slot_8"
)
_TICK_SEC = 0.5


def _row_from_buffer(buf: EdgeTelemetry, schema: list[str]) -> dict[str, Any]:
    device_id = buf.device_id.decode("utf-8", errors="ignore").strip()
    row: dict[str, Any] = {
        "timestamp_ms": int(buf.timestamp_ms),
        "device_id": device_id,
        "status_code": int(buf.status_code),
    }
    for i, name in enumerate(schema):
        if i < 8 and name:
            row[name] = round(float(buf.data[i]), 4)
    return row


def main() -> None:
    st.set_page_config(
        page_title="Edge telemetry (libedgecore)",
        layout="wide",
    )
    st.title("Edge telemetry")
    st.caption("Streaming desde libedgecore (modo system o serial).")

    with st.sidebar:
        st.header("Conexión")
        lib_override = st.text_input(
            "Ruta a libedgecore (opcional)",
            value="",
            help="Vacío: DUCKCLAW_EDGE_LIB_PATH o búsqueda por defecto (cwd + native/).",
        ).strip()
        mode = st.radio("Modo", ("system", "serial"), horizontal=True)
        port = st.text_input("Puerto serial", value="/dev/ttyUSB0")
        baud = st.number_input("Baud rate", min_value=9600, value=115200, step=600)
        sample_interval = st.slider(
            "Intervalo entre lecturas (s)",
            min_value=0.5,
            max_value=60.0,
            value=2.0,
            step=0.5,
        )
        schema_raw = st.text_input(
            "Esquema (CSV, hasta 8 métricas)",
            value=_DEFAULT_SCHEMA,
        )
        max_rows = st.number_input("Puntos en el gráfico", min_value=20, value=120, step=10)

    schema = [s.strip() for s in schema_raw.split(",") if s.strip()]

    if "rows" not in st.session_state:
        st.session_state.rows = []
    if "lib" not in st.session_state:
        st.session_state.lib = None
    if "fd" not in st.session_state:
        st.session_state.fd = -1
    if "last_tick" not in st.session_state:
        st.session_state.last_tick = 0.0
    if "mode_cfg" not in st.session_state:
        st.session_state.mode_cfg = None

    lib_path = lib_override or None
    lib = st.session_state.lib
    cfg_key = (lib_override, mode, port, int(baud))
    if lib is None or st.session_state.get("conn_cfg") != cfg_key:
        if lib is not None and st.session_state.fd >= 0:
            close_serial(lib, st.session_state.fd)
        st.session_state.fd = -1
        st.session_state.conn_cfg = cfg_key
        st.session_state.lib = load_edge_core(lib_path)
        st.session_state.last_tick = 0.0
        lib = st.session_state.lib

    if lib is None:
        st.error(
            "No se encontró libedgecore. Compila en integrations/edge-devices/native/ "
            "o define DUCKCLAW_EDGE_LIB_PATH."
        )
        st.stop()

    system = mode == "system"

    if not system:
        if st.session_state.fd < 0:
            fd = open_serial(lib, port, int(baud))
            if fd < 0:
                st.error(f"No se pudo abrir el puerto serial {port!r} (código {fd}).")
                st.stop()
            st.session_state.fd = fd
    else:
        if st.session_state.fd >= 0:
            close_serial(lib, st.session_state.fd)
            st.session_state.fd = -1

    fd = st.session_state.fd

    @st.fragment(run_every=timedelta(seconds=_TICK_SEC))
    def _poll() -> None:
        lib_inner = st.session_state.lib
        fd_inner = st.session_state.fd
        now = time.monotonic()
        if now - st.session_state.last_tick < float(sample_interval):
            return
        st.session_state.last_tick = now

        if lib_inner is None:
            return
        rc, buf = read_telemetry(lib_inner, system=system, fd=fd_inner)
        if rc != 0:
            st.session_state["last_error"] = f"read_telemetry rc={rc}"
            return
        st.session_state["last_error"] = ""
        row = _row_from_buffer(buf, schema)
        rows: list[dict[str, Any]] = list(st.session_state.rows)
        rows.append(row)
        cap = int(max_rows)
        if len(rows) > cap:
            rows = rows[-cap:]
        st.session_state.rows = rows

    _poll()

    err = str(st.session_state.get("last_error", ""))
    if err:
        st.warning(err)

    rows = st.session_state.rows
    if not rows:
        st.info("Esperando la primera muestra…")
        return

    last = rows[-1]
    st.subheader("Última muestra")
    st.write(
        f"**device_id:** `{last.get('device_id', '')}` · "
        f"**timestamp_ms:** `{last.get('timestamp_ms')}` · "
        f"**status:** `{last.get('status_code')}`"
    )
    mcols = st.columns(min(4, max(1, len(schema))))
    for i, name in enumerate(schema[:8]):
        if name in last:
            mcols[i % len(mcols)].metric(name, f"{last[name]}")

    chart_cols = [c for c in schema if c in rows[0]]
    if chart_cols:
        df = pd.DataFrame(rows)
        if "timestamp_ms" in df.columns:
            df = df.set_index("timestamp_ms")
        sub = df[[c for c in chart_cols if c in df.columns]]
        if not sub.empty:
            st.subheader("Series")
            st.line_chart(sub, height=320)

    with st.expander("Tabla (últimas filas)"):
        st.dataframe(pd.DataFrame(rows[-min(50, len(rows)) :]), use_container_width=True)


main()
