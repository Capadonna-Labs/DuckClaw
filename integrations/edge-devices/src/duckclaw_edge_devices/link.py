"""
Enlace TCP entre dos edge devices (DEL — DuckClaw Edge Link).

Uso típico (dos portátiles en la misma LAN o Tailscale):

  # Portátil A
  uv run python -m duckclaw_edge_devices.link --device-id LAPTOP-A --listen 9870 --stream

  # Portátil B
  uv run python -m duckclaw_edge_devices.link --device-id LAPTOP-B --connect 192.168.1.10:9870 --stream
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import socket
from typing import Awaitable, Callable, Optional

from duckclaw_edge_devices.client import (
    close_serial,
    load_edge_core,
    open_serial,
    read_telemetry,
)
from duckclaw_edge_devices.protocol import (
    HEADER_SIZE,
    MessageType,
    TelemetryFrame,
    decode_envelope_header,
    decode_hello,
    decode_telemetry_message,
    encode_hello,
    encode_ping,
    encode_pong,
    encode_telemetry_message,
    telemetry_from_ctypes,
)

_log = logging.getLogger(__name__)

OnTelemetry = Callable[[TelemetryFrame, str], Awaitable[None] | None]


class EdgeLinkPeer:
    """Un extremo del enlace: escucha, conecta y envía/recibe telemetría DEL."""

    def __init__(
        self,
        device_id: str,
        *,
        on_telemetry: Optional[OnTelemetry] = None,
    ) -> None:
        self.device_id = device_id[:16]
        self._on_telemetry = on_telemetry
        self._remote_id: Optional[str] = None
        self._writer: Optional[asyncio.StreamWriter] = None
        self._reader: Optional[asyncio.StreamReader] = None

    @property
    def remote_id(self) -> Optional[str]:
        return self._remote_id

    async def _read_exactly(self, n: int) -> bytes:
        assert self._reader is not None
        buf = b""
        while len(buf) < n:
            chunk = await self._reader.read(n - len(buf))
            if not chunk:
                raise ConnectionError("peer closed connection")
            buf += chunk
        return buf

    async def _read_message(self) -> tuple[MessageType, bytes]:
        header = await self._read_exactly(HEADER_SIZE)
        msg_type, payload_len = decode_envelope_header(header)
        payload = await self._read_exactly(payload_len) if payload_len else b""
        return msg_type, payload

    async def _write_message(self, data: bytes) -> None:
        if self._writer is None:
            raise RuntimeError("not connected")
        self._writer.write(data)
        await self._writer.drain()

    async def handshake(self) -> None:
        await self._write_message(encode_hello(self.device_id))
        msg_type, payload = await self._read_message()
        if msg_type != MessageType.HELLO:
            raise ProtocolError(f"expected HELLO, got {msg_type}")
        self._remote_id = decode_hello(payload)
        _log.info("peer hello: %s", self._remote_id)

    async def send_telemetry(self, frame: TelemetryFrame) -> None:
        pkt = encode_telemetry_message(
            device_id=frame.device_id,
            data=frame.data,
            timestamp_ms=frame.timestamp_ms,
            status_code=frame.status_code,
        )
        await self._write_message(pkt)

    async def _handle_telemetry(self, payload: bytes, peer_addr: str) -> None:
        frame = decode_telemetry_message(payload)
        if self._on_telemetry:
            result = self._on_telemetry(frame, peer_addr)
            if asyncio.iscoroutine(result):
                await result
        else:
            _log.info(
                "[%s] ts=%s metrics=%s",
                frame.device_id,
                frame.timestamp_ms,
                list(frame.data),
            )

    async def _recv_loop(self, peer_addr: str) -> None:
        while True:
            msg_type, payload = await self._read_message()
            if msg_type == MessageType.TELEMETRY:
                await self._handle_telemetry(payload, peer_addr)
            elif msg_type == MessageType.PING:
                await self._write_message(encode_pong())
            elif msg_type == MessageType.PONG:
                continue
            elif msg_type == MessageType.HELLO:
                self._remote_id = decode_hello(payload)
            else:
                _log.warning("unknown message type %s", msg_type)

    async def attach_streams(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        peer_addr: str,
    ) -> asyncio.Task[None]:
        self._reader = reader
        self._writer = writer
        await self.handshake()
        return asyncio.create_task(self._recv_loop(peer_addr))

    async def connect(self, host: str, port: int) -> asyncio.Task[None]:
        reader, writer = await asyncio.open_connection(host, port)
        addr = f"{host}:{port}"
        _log.info("connected to %s", addr)
        return await self.attach_streams(reader, writer, addr)

    async def run_server(self, host: str, port: int) -> None:
        async def _client(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
            peer = writer.get_extra_info("peername")
            addr = f"{peer[0]}:{peer[1]}" if peer else "?"
            _log.info("incoming connection from %s", addr)
            recv_task: Optional[asyncio.Task[None]] = None
            try:
                recv_task = await self.attach_streams(reader, writer, addr)
                await recv_task
            except Exception as exc:  # noqa: BLE001
                _log.warning("session ended: %s", exc)
            finally:
                if recv_task and not recv_task.done():
                    recv_task.cancel()
                writer.close()
                await writer.wait_closed()

        server = await asyncio.start_server(_client, host, port)
        addrs = ", ".join(str(s.getsockname()) for s in server.sockets or [])
        _log.info("DEL listening on %s (device_id=%s)", addrs, self.device_id)
        async with server:
            await server.serve_forever()


class ProtocolError(Exception):
    pass


async def stream_local_system(
    peer: EdgeLinkPeer,
    *,
    interval_sec: float,
    lib_path: Optional[str] = None,
) -> None:
    """Lee ``read_system_frame`` vía libedgecore y publica al peer conectado."""
    lib = load_edge_core(lib_path)
    if lib is None:
        raise RuntimeError("libedgecore not found; set DUCKCLAW_EDGE_LIB_PATH")
    while True:
        rc, buf = read_telemetry(lib, system=True, fd=-1)
        if rc == 0:
            frame = telemetry_from_ctypes(buf)
            if not frame.device_id.strip():
                frame = TelemetryFrame(
                    device_id=peer.device_id,
                    data=frame.data,
                    timestamp_ms=frame.timestamp_ms,
                    status_code=frame.status_code,
                )
            await peer.send_telemetry(frame)
        await asyncio.sleep(interval_sec)


async def stream_local_serial(
    peer: EdgeLinkPeer,
    *,
    port: str,
    baud: int,
    interval_sec: float,
    lib_path: Optional[str] = None,
) -> None:
    lib = load_edge_core(lib_path)
    if lib is None:
        raise RuntimeError("libedgecore not found")
    fd = open_serial(lib, port, baud)
    if fd < 0:
        raise RuntimeError(f"cannot open serial port {port!r} (code {fd})")
    try:
        while True:
            rc, buf = read_telemetry(lib, system=False, fd=fd)
            if rc == 0:
                await peer.send_telemetry(telemetry_from_ctypes(buf))
            await asyncio.sleep(interval_sec)
    finally:
        close_serial(lib, fd)


def _default_device_id() -> str:
    return (os.environ.get("DUCKCLAW_EDGE_DEVICE_ID") or socket.gethostname())[:16]


async def _main_async(args: argparse.Namespace) -> None:
    peer = EdgeLinkPeer(args.device_id or _default_device_id())

    tasks: list[asyncio.Task[None]] = []

    if args.listen:
        host, _, port_s = args.listen.partition(":")
        port = int(port_s or "9870")
        tasks.append(asyncio.create_task(peer.run_server(host or "0.0.0.0", port)))

    async def _connect() -> None:
        host, _, port_s = args.connect.rpartition(":")
        port = int(port_s or "9870")
        recv = await peer.connect(host, port)
        await recv

    if args.connect:
        tasks.append(asyncio.create_task(_connect()))

    if args.stream:
        interval = float(args.interval)
        lib_path = (args.lib or "").strip() or None

        async def _wait_writer_then_stream() -> None:
            for _ in range(300):
                if peer._writer is not None:
                    break
                await asyncio.sleep(0.1)
            if args.mode == "system":
                await stream_local_system(peer, interval_sec=interval, lib_path=lib_path)
            else:
                await stream_local_serial(
                    peer,
                    port=args.serial_port,
                    baud=args.baud,
                    interval_sec=interval,
                    lib_path=lib_path,
                )

        tasks.append(asyncio.create_task(_wait_writer_then_stream()))

    if not tasks:
        raise SystemExit("use --listen and/or --connect")

    await asyncio.gather(*tasks)


def main() -> None:
    parser = argparse.ArgumentParser(description="DuckClaw Edge Link (peer TCP)")
    parser.add_argument("--device-id", default="", help="ID local (16 chars max)")
    parser.add_argument(
        "--listen",
        metavar="HOST:PORT",
        default="",
        help="Escuchar (ej. 0.0.0.0:9870)",
    )
    parser.add_argument(
        "--connect",
        metavar="HOST:PORT",
        help="Conectar a otro edge device",
    )
    parser.add_argument(
        "--stream",
        action="store_true",
        help="Enviar telemetría local periódicamente",
    )
    parser.add_argument("--interval", type=float, default=2.0)
    parser.add_argument("--mode", choices=("system", "serial"), default="system")
    parser.add_argument("--serial-port", default="/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--lib", default="", help="Ruta a libedgecore")
    args = parser.parse_args()

    if args.listen and ":" not in args.listen:
        args.listen = f"{args.listen}:9870"

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    try:
        asyncio.run(_main_async(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
