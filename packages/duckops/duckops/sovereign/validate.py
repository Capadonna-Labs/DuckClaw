"""Validaciones (spec §6 — puerto, permisos)."""

from __future__ import annotations

import os
import socket
from pathlib import Path


def is_port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        try:
            return s.connect_ex((host, port)) == 0
        except OSError:
            return False


def suggest_gateway_port(host: str, start: int = 8282, *, max_tries: int = 50) -> int:
    p = start
    for _ in range(max_tries):
        if not is_port_in_use(host, p):
            return p
        p += 1
    return start


def private_db_dir_writable(repo_root: Path) -> bool:
    d = (repo_root / "db" / "private").resolve()
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False
    return os.access(d, os.W_OK)


def redis_ping_url(url: str) -> tuple[bool, str]:
    try:
        import redis as redis_sync  # noqa: PLC0415
    except ImportError:
        return False, "paquete redis no instalado en este entorno"
    try:
        r = redis_sync.Redis.from_url(url, socket_connect_timeout=2)
        if r.ping():
            return True, "PONG"
        return False, "sin PING"
    except Exception as e:
        return False, str(e)[:200]
