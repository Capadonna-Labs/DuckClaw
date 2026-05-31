"""
Protocolo DuckClaw Edge Link (DEL) — comunicación entre edge devices (p. ej. dos portátiles).

Capa de transporte: TCP con mensajes enmarcados (cabecera fija + payload).
Payload de telemetría: mismo frame binario de 51 bytes que ``read_sensor_frame`` / serial
(0xAA + device_id + 8 floats + XOR + 0xFF), agnóstico al hardware.
"""

from __future__ import annotations

import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

# Envelope (stream framing)
MAGIC = b"DEDG"
VERSION = 1
HEADER_STRUCT = struct.Struct("!4sBBH")  # magic, version, msg_type, payload_len
HEADER_SIZE = HEADER_STRUCT.size  # 8

# Serial telemetry frame (compatible con edge_core.cpp)
SERIAL_SYNC = 0xAA
SERIAL_FOOTER = 0xFF
SERIAL_FRAME_LEN = 51  # sync + 50 bytes payload body after sync


class MessageType(IntEnum):
    HELLO = 1
    TELEMETRY = 2
    PING = 3
    PONG = 4


@dataclass(frozen=True)
class TelemetryFrame:
    """Telemetría decodificada (equivalente a ``EdgeTelemetry`` en C)."""

    device_id: str
    data: tuple[float, float, float, float, float, float, float, float]
    timestamp_ms: int = 0
    status_code: int = 0


def _xor_checksum(data: bytes) -> int:
    crc = 0
    for b in data:
        crc ^= b
    return crc & 0xFF


def encode_serial_frame(
    *,
    device_id: str,
    data: tuple[float, ...] | list[float],
    timestamp_ms: int = 0,
    status_code: int = 0,
) -> bytes:
    """
  Frame de 51 bytes (wire serial / DEL telemetry payload).

  Nota: ``timestamp_ms`` y ``status_code`` no van en el frame serial de 51 B;
  se envían en mensajes de red solo si se usa :func:`encode_telemetry_message`.
  """
    did = device_id.encode("utf-8", errors="ignore")[:16]
    did_padded = did.ljust(16, b"\x00")[:16]
    floats = list(data)[:8]
    while len(floats) < 8:
        floats.append(0.0)
    body = did_padded + struct.pack("<8f", *floats)
    crc = _xor_checksum(body)
    return bytes([SERIAL_SYNC]) + body + bytes([crc, SERIAL_FOOTER])


def decode_serial_frame(frame: bytes) -> TelemetryFrame:
    """Decodifica un frame de exactamente 51 bytes."""
    if len(frame) != SERIAL_FRAME_LEN:
        raise ValueError(f"frame length must be {SERIAL_FRAME_LEN}, got {len(frame)}")
    if frame[0] != SERIAL_SYNC:
        raise ValueError("invalid sync byte")
    if frame[50] != SERIAL_FOOTER:
        raise ValueError("invalid footer byte")
    body = frame[1:49]
    crc = frame[49]
    if _xor_checksum(body) != crc:
        raise ValueError("checksum mismatch")
    device_id = body[:16].split(b"\x00", 1)[0].decode("utf-8", errors="ignore")
    floats = struct.unpack("<8f", body[16:48])
    return TelemetryFrame(device_id=device_id, data=floats)


def encode_envelope(msg_type: MessageType, payload: bytes) -> bytes:
    if len(payload) > 0xFFFF:
        raise ValueError("payload too large")
    if msg_type not in MessageType:
        raise ValueError("invalid message type")
    return HEADER_STRUCT.pack(MAGIC, VERSION, int(msg_type), len(payload)) + payload


def decode_envelope_header(header: bytes) -> tuple[MessageType, int]:
    if len(header) != HEADER_SIZE:
        raise ValueError("incomplete header")
    magic, version, msg_type, payload_len = HEADER_STRUCT.unpack(header)
    if magic != MAGIC:
        raise ValueError("invalid magic")
    if version != VERSION:
        raise ValueError(f"unsupported version {version}")
    return MessageType(msg_type), payload_len


def encode_hello(device_id: str) -> bytes:
    did = device_id.encode("utf-8", errors="ignore")[:16]
    return encode_envelope(MessageType.HELLO, did.ljust(16, b"\x00")[:16])


def decode_hello(payload: bytes) -> str:
    if len(payload) != 16:
        raise ValueError("hello payload must be 16 bytes")
    return payload.split(b"\x00", 1)[0].decode("utf-8", errors="ignore")


def encode_telemetry_message(
    *,
    device_id: str,
    data: tuple[float, ...] | list[float],
    timestamp_ms: int,
    status_code: int = 0,
) -> bytes:
    """Telemetría en red: frame serial 51 B + metadata (timestamp, status)."""
    serial = encode_serial_frame(device_id=device_id, data=data)
    meta = struct.pack("<q i", int(timestamp_ms), int(status_code))
    return encode_envelope(MessageType.TELEMETRY, serial + meta)


def decode_telemetry_message(payload: bytes) -> TelemetryFrame:
    if len(payload) < SERIAL_FRAME_LEN + 12:
        raise ValueError("telemetry payload too short")
    frame = decode_serial_frame(payload[:SERIAL_FRAME_LEN])
    timestamp_ms, status_code = struct.unpack("<q i", payload[SERIAL_FRAME_LEN : SERIAL_FRAME_LEN + 12])
    return TelemetryFrame(
        device_id=frame.device_id,
        data=frame.data,
        timestamp_ms=int(timestamp_ms),
        status_code=int(status_code),
    )


def encode_ping() -> bytes:
    return encode_envelope(MessageType.PING, b"")


def encode_pong() -> bytes:
    return encode_envelope(MessageType.PONG, b"")


def telemetry_from_ctypes(buf: object) -> TelemetryFrame:
    """Convierte ``EdgeTelemetry`` ctypes a :class:`TelemetryFrame`."""
    device_id = bytes(buf.device_id).split(b"\x00", 1)[0].decode("utf-8", errors="ignore")
    data = tuple(float(buf.data[i]) for i in range(8))
    return TelemetryFrame(
        device_id=device_id,
        data=data,  # type: ignore[arg-type]
        timestamp_ms=int(buf.timestamp_ms),
        status_code=int(buf.status_code),
    )
