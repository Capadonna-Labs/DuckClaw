"""ctypes bindings for libedgecore (read_system_frame / serial sensor protocol)."""

from __future__ import annotations

import ctypes
import os
from pathlib import Path
from typing import Optional, Tuple

__all__ = [
    "EdgeTelemetry",
    "integration_root",
    "default_library_candidates",
    "load_edge_core",
    "open_serial",
    "close_serial",
    "read_telemetry",
]


def integration_root() -> Path:
    """Root of the `integrations/edge-devices` project (contains `native/`)."""
    return Path(__file__).resolve().parents[2]


class EdgeTelemetry(ctypes.Structure):
    _fields_ = [
        ("device_id", ctypes.c_char * 16),
        ("data", ctypes.c_float * 8),
        ("timestamp_ms", ctypes.c_longlong),
        ("status_code", ctypes.c_int),
    ]


def default_library_candidates() -> list[Path]:
    """Search order for libedgecore when ``lib_path`` is not passed to ``load_edge_core``."""
    raw = (os.environ.get("DUCKCLAW_EDGE_LIB_PATH") or "").strip()
    out: list[Path] = []
    if raw:
        out.append(Path(raw))
    out.append(Path.cwd() / "libedgecore.so")
    out.append(Path.cwd() / "libedgecore.dylib")
    root = integration_root()
    out.append(root / "native" / "libedgecore.so")
    out.append(root / "native" / "libedgecore.dylib")
    # ``*.so`` is gitignored; many checkouts keep a prior build next to the old Python tree.
    try:
        monorepo_root = root.parents[1]
        out.append(monorepo_root / "duckclaw" / "libedgecore.so")
        out.append(monorepo_root / "duckclaw" / "forge" / "skills" / "libedgecore.so")
    except IndexError:
        pass
    return out


def load_edge_core(lib_path: Optional[str] = None) -> Optional[ctypes.CDLL]:
    """
    Load ``libedgecore`` and configure ctypes signatures.

    If ``lib_path`` is None, uses ``DUCKCLAW_EDGE_LIB_PATH`` then :func:`default_library_candidates`.
    """
    candidates: list[Path] = []
    if lib_path:
        candidates.append(Path(lib_path))
    else:
        candidates.extend(default_library_candidates())

    chosen: Optional[Path] = None
    for p in candidates:
        if p.is_file():
            chosen = p
            break
    if chosen is None:
        return None

    lib = ctypes.CDLL(str(chosen))
    lib.init_serial_port.argtypes = [ctypes.c_char_p, ctypes.c_int]
    lib.init_serial_port.restype = ctypes.c_int
    lib.read_sensor_frame.argtypes = [ctypes.c_int, ctypes.POINTER(EdgeTelemetry)]
    lib.read_sensor_frame.restype = ctypes.c_int
    lib.read_system_frame.argtypes = [ctypes.POINTER(EdgeTelemetry)]
    lib.read_system_frame.restype = ctypes.c_int
    lib.close_serial_port.argtypes = [ctypes.c_int]
    lib.close_serial_port.restype = None
    return lib


def open_serial(lib: ctypes.CDLL, port: str, baud_rate: int) -> int:
    """Open serial port; returns fd (>=0) or negative error code from native layer."""
    return int(lib.init_serial_port(port.encode("utf-8"), int(baud_rate)))


def close_serial(lib: ctypes.CDLL, fd: int) -> None:
    if fd >= 0:
        lib.close_serial_port(fd)


def read_telemetry(lib: ctypes.CDLL, *, system: bool, fd: int) -> Tuple[int, EdgeTelemetry]:
    """
    Read one frame. ``system=True`` uses ``read_system_frame``; else ``read_sensor_frame(fd, ...)``.
    """
    buf = EdgeTelemetry()
    if system:
        rc = int(lib.read_system_frame(ctypes.byref(buf)))
    else:
        rc = int(lib.read_sensor_frame(fd, ctypes.byref(buf)))
    return rc, buf


def telemetry_to_metrics(buf: EdgeTelemetry, schema: list[str]) -> dict[str, float]:
    """Map ``data[0..7]`` to schema names (same convention as ``edge_bridge``)."""
    return {
        name: round(float(buf.data[i]), 4)
        for i, name in enumerate(schema)
        if i < 8 and name
    }
