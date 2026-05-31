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
from duckclaw_edge_devices.link import EdgeLinkPeer
from duckclaw_edge_devices.protocol import (
    MessageType,
    TelemetryFrame,
    decode_serial_frame,
    encode_serial_frame,
    encode_telemetry_message,
)

__all__ = [
    "EdgeTelemetry",
    "EdgeLinkPeer",
    "MessageType",
    "TelemetryFrame",
    "close_serial",
    "decode_serial_frame",
    "default_library_candidates",
    "encode_serial_frame",
    "encode_telemetry_message",
    "integration_root",
    "load_edge_core",
    "open_serial",
    "read_telemetry",
    "telemetry_to_metrics",
]
