"""PM2 process health for admin stack overview (short timeout, no blocking)."""

from __future__ import annotations

import json
import os
import re
from typing import Any

PM2_JLIST_TIMEOUT_SEC = 2

TRACKED_PM2_PROCESSES: tuple[str, ...] = (
    "DuckClaw-Gateway",
    "DuckClaw-DB-Writer",
    "DuckClaw-Knowledge-Indexer",
    "DuckClaw-Heartbeat",
)

_PM2_DISPLAY_LABELS: dict[str, str] = {
    "DuckClaw-Gateway": "Gateway",
    "DuckClaw-DB-Writer": "DB-Writer",
    "DuckClaw-Knowledge-Indexer": "Indexer",
    "DuckClaw-Heartbeat": "Heartbeat",
}


def _bytes_to_mb(value: int | float) -> float:
    return round(float(value) / (1024 * 1024), 1)


def _parse_mb_string(value: object) -> float | None:
    if isinstance(value, (int, float)):
        return round(float(value), 1)
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    match = re.match(r"^([\d.]+)\s*(MiB|MB|Mi|KB|KiB|GB|GiB)?$", text, re.IGNORECASE)
    if not match:
        return None
    amount = float(match.group(1))
    unit = (match.group(2) or "MiB").lower()
    if unit in {"kb", "kib"}:
        return round(amount / 1024, 1)
    if unit in {"gb", "gib"}:
        return round(amount * 1024, 1)
    return round(amount, 1)


def _rss_mb_from_item(item: dict[str, Any]) -> float | None:
    monit = item.get("monit")
    if isinstance(monit, dict):
        memory = monit.get("memory")
        if isinstance(memory, (int, float)) and memory >= 0:
            return _bytes_to_mb(memory)
    return None


def _heap_mb_from_item(item: dict[str, Any]) -> float | None:
    env = item.get("pm2_env")
    if not isinstance(env, dict):
        return None
    axm = env.get("axm_monitor")
    if not isinstance(axm, dict):
        return None
    for key in ("Used Heap Size", "Heap Size", "heapUsed", "heap_used"):
        parsed = _parse_mb_string(axm.get(key))
        if parsed is not None:
            return parsed
    return None


def parse_pm2_jlist(payload: object) -> list[dict[str, Any]]:
    """Normaliza ``pm2 jlist`` JSON a filas de procesos DuckClaw rastreados."""
    if not isinstance(payload, list):
        return []

    by_name: dict[str, dict[str, Any]] = {}
    for raw in payload:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("name") or "").strip()
        if name not in TRACKED_PM2_PROCESSES:
            continue
        env = raw.get("pm2_env") if isinstance(raw.get("pm2_env"), dict) else {}
        pid = raw.get("pid")
        by_name[name] = {
            "name": name,
            "label": _PM2_DISPLAY_LABELS.get(name, name),
            "status": str(env.get("status") or "unknown"),
            "pid": int(pid) if isinstance(pid, int) and pid > 0 else None,
            "rss_mb": _rss_mb_from_item(raw),
            "heap_mb": _heap_mb_from_item(raw),
        }

    rows: list[dict[str, Any]] = []
    for name in TRACKED_PM2_PROCESSES:
        if name in by_name:
            rows.append(by_name[name])
            continue
        rows.append(
            {
                "name": name,
                "label": _PM2_DISPLAY_LABELS.get(name, name),
                "status": "missing",
                "pid": None,
                "rss_mb": None,
                "heap_mb": None,
            }
        )
    return rows


def _skip_pm2_jlist_self_probe() -> bool:
    # ponytail: proceso DuckClaw bajo PM2 no debe invocar `pm2 jlist` (bloqueo/deadlock Windows).
    if (os.environ.get("DUCKCLAW_PM2_MATCHED_APP_NAME") or "").strip():
        return True
    if not (os.environ.get("DUCKCLAW_PM2_PROCESS_NAME") or "").strip():
        return False
    try:
        from duckclaw.process_role import is_gateway_process

        return is_gateway_process()
    except Exception:
        return False


def collect_pm2_stack_health(*, timeout_sec: int = PM2_JLIST_TIMEOUT_SEC) -> list[dict[str, Any]]:
    """Ejecuta ``pm2 jlist`` con timeout corto; devuelve [] si PM2 no está disponible."""
    if _skip_pm2_jlist_self_probe():
        return []
    try:
        from duckclaw.ops.toolchain import run_pm2

        proc = run_pm2("jlist", timeout=timeout_sec)
    except Exception:
        return []

    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return []

    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []

    return parse_pm2_jlist(payload)
