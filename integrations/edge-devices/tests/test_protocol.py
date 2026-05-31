from __future__ import annotations

import struct

import pytest

from duckclaw_edge_devices.protocol import (
    HEADER_SIZE,
    MessageType,
    decode_envelope_header,
    decode_serial_frame,
    decode_telemetry_message,
    encode_envelope,
    encode_hello,
    encode_serial_frame,
    encode_telemetry_message,
)


def test_serial_frame_roundtrip() -> None:
    data = (1.0, 2.5, 0.0, 0.0, 100.0, 50.0, 0.0, 0.0)
    raw = encode_serial_frame(device_id="NODE-01", data=data)
    assert len(raw) == 51
    frame = decode_serial_frame(raw)
    assert frame.device_id == "NODE-01"
    assert frame.data[0] == pytest.approx(1.0)
    assert frame.data[1] == pytest.approx(2.5)


def test_envelope_telemetry_roundtrip() -> None:
    pkt = encode_telemetry_message(
        device_id="LAPTOP-A",
        data=[0.1] * 8,
        timestamp_ms=1_700_000_000_000,
        status_code=0,
    )
    assert pkt[:4] == b"DEDG"
    msg_type, plen = decode_envelope_header(pkt[:HEADER_SIZE])
    assert msg_type == MessageType.TELEMETRY
    assert plen == 51 + 12
    frame = decode_telemetry_message(pkt[HEADER_SIZE:])
    assert frame.device_id == "LAPTOP-A"
    assert frame.timestamp_ms == 1_700_000_000_000


def test_hello_envelope() -> None:
    pkt = encode_hello("peer-1")
    msg_type, plen = decode_envelope_header(pkt[:HEADER_SIZE])
    assert msg_type == MessageType.HELLO
    assert plen == 16
