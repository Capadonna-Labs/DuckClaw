"""Correo periódico del Mac: RAM, disco y procesos del servidor.

No escribe DuckDB. La clave de Resend se lee de `.env` y no entra en el cuerpo.
"""

from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import httpx
from dotenv import load_dotenv

from duckclaw.ops.toolchain import pm2_argv

WATCHED_PM2 = (
    "DuckClaw-Gateway",
    "DuckClaw-DB-Writer",
    "DuckClaw-Knowledge-Indexer",
    "DuckClaw-Heartbeat",
    "duckclaw-admin-ui",
)
_MEMORY_FREE_FLOOR = 15
_DISK_USED_CEILING = 85
_DEFAULT_INTERVAL_SECONDS = 3 * 60 * 60
_RESEND_URL = "https://api.resend.com/emails"
_DEFAULT_FROM = "DuckClaw <onboarding@resend.dev>"


@dataclass(frozen=True)
class HostSample:
    memory_free_pct: int
    memory_total_gb: float
    disk_used_pct: int
    processes: tuple[tuple[str, str], ...]
    redis_open: bool
    tailscale: str
    gateway_health: bool
    admin_up: bool

    @property
    def scarce(self) -> bool:
        if self.memory_free_pct <= _MEMORY_FREE_FLOOR or self.disk_used_pct >= _DISK_USED_CEILING:
            return True
        if not self.redis_open or self.tailscale != "Running":
            return True
        if not self.gateway_health or not self.admin_up:
            return True
        return any(status != "online" for _, status in self.processes)


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def parse_memory_pressure(text: str) -> tuple[int, float]:
    """Devuelve (porcentaje libre, GB totales) a partir de `memory_pressure -Q`."""
    free_pct = 0
    total_gb = 0.0
    for line in text.splitlines():
        if line.startswith("The system has "):
            total_gb = int(line.split()[3]) / (1024**3)
        if "memory free percentage:" in line:
            free_pct = int(line.rsplit(":", 1)[1].strip().rstrip("%"))
    return free_pct, round(total_gb, 1)


def is_tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_ok(url: str, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return 200 <= int(response.status) < 500
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def pm2_status_map(raw_json: str) -> dict[str, str]:
    try:
        rows = json.loads(raw_json or "[]")
    except json.JSONDecodeError:
        return {}
    found: dict[str, str] = {}
    if not isinstance(rows, list):
        return found
    for row in rows:
        if not isinstance(row, dict):
            continue
        env = row.get("pm2_env") if isinstance(row.get("pm2_env"), dict) else {}
        name = str(row.get("name") or "")
        if name:
            found[name] = str(env.get("status") or "unknown")
    return found


def disk_used_pct(path: str = "/") -> int:
    usage = shutil.disk_usage(path)
    if usage.total <= 0:
        return 100
    return int((usage.used * 100) / usage.total)


def tailscale_backend_state() -> str:
    try:
        proc = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "missing"
    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        return "unknown"
    state = payload.get("BackendState") if isinstance(payload, dict) else None
    return str(state or "unknown")


def collect_sample() -> HostSample:
    pressure = subprocess.run(
        ["memory_pressure", "-Q"],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    free_pct, total_gb = parse_memory_pressure(pressure.stdout or "")
    pm2 = subprocess.run(
        pm2_argv("jlist"),
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )
    statuses = pm2_status_map(pm2.stdout or "")
    watched = tuple((name, statuses.get(name, "missing")) for name in WATCHED_PM2)
    return HostSample(
        memory_free_pct=free_pct,
        memory_total_gb=total_gb,
        disk_used_pct=disk_used_pct("/"),
        processes=watched,
        redis_open=is_tcp_open("127.0.0.1", 6379),
        tailscale=tailscale_backend_state(),
        gateway_health=http_ok("http://127.0.0.1:8000/health"),
        admin_up=http_ok("http://127.0.0.1:3001/login"),
    )


def render_mail(sample: HostSample) -> tuple[str, str]:
    state = "escasa de recursos" if sample.scarce else "ok"
    lines = [
        f"Mac mini — {state}",
        f"Memoria libre: {sample.memory_free_pct}% de {sample.memory_total_gb} GB",
        f"Disco /: {sample.disk_used_pct}% usado",
        f"Gateway /health: {'ok' if sample.gateway_health else 'caido'}",
        f"Admin :3001: {'ok' if sample.admin_up else 'caido'}",
        f"Redis :6379: {'abierto' if sample.redis_open else 'cerrado'}",
        f"Tailscale: {sample.tailscale}",
    ]
    lines.extend(f"{name}: {status}" for name, status in sample.processes)
    return f"DuckClaw Mac mini {state}", "\n".join(lines)


def send_resend(subject: str, body: str) -> int:
    api_key = (os.environ.get("RESEND_API_KEY") or "").strip()
    recipient = (os.environ.get("HOST_STATUS_MAIL_TO") or os.environ.get("DUCKCLAW_ADMIN_EMAIL") or "").strip()
    sender = (os.environ.get("HOST_STATUS_MAIL_FROM") or _DEFAULT_FROM).strip()
    if not api_key or not recipient:
        raise RuntimeError("Faltan RESEND_API_KEY y el destinatario (HOST_STATUS_MAIL_TO o DUCKCLAW_ADMIN_EMAIL)")
    response = httpx.post(
        _RESEND_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"from": sender, "to": [recipient], "subject": subject, "text": body},
        timeout=20.0,
    )
    if response.status_code >= 400:
        raise RuntimeError(f"Resend HTTP {response.status_code}: {response.text[:300]}")
    return response.status_code


def _sleep_until_next(interval_seconds: int) -> None:
    deadline = time.monotonic() + interval_seconds
    while time.monotonic() < deadline:
        time.sleep(min(30.0, deadline - time.monotonic()))


def run_forever() -> None:
    load_dotenv(repo_root() / ".env", override=False)
    interval = int(os.environ.get("HOST_STATUS_INTERVAL_SECONDS") or _DEFAULT_INTERVAL_SECONDS)
    while True:
        try:
            subject, body = render_mail(collect_sample())
            send_resend(subject, body)
            print(f"HOST_STATUS_SENT {subject}", flush=True)
        except Exception as exc:  # noqa: BLE001 — el bucle no debe morir por un fallo de red
            print(f"HOST_STATUS_ERROR {exc}", flush=True)
        _sleep_until_next(interval)


if __name__ == "__main__":
    run_forever()
