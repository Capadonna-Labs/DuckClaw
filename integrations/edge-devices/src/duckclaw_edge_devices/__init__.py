"""DuckClaw edge device integration (libedgecore + tooling)."""

from duckclaw_edge_devices.client import (
    EdgeTelemetry,
    close_serial,
    default_library_candidates,
    integration_root,
    load_edge_core,
    open_serial,
    read_telemetry,
    telemetry_to_metrics,
)

__all__ = [
    "EdgeTelemetry",
    "close_serial",
    "default_library_candidates",
    "integration_root",
    "load_edge_core",
    "open_serial",
    "read_telemetry",
    "telemetry_to_metrics",
]
