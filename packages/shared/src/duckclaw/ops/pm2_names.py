"""Resolución de nombres PM2 con alias legacy (p. ej. duckclaw-gateway vs DuckClaw-Gateway)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

GATEWAY_PM2_CANDIDATES: tuple[str, ...] = (
    "DuckClaw-Gateway",
    "duckclaw-gateway",
    "DuckClaw-API",
)

DB_WRITER_PM2_CANDIDATES: tuple[str, ...] = (
    "DuckClaw-DB-Writer",
    "duckclaw-db-writer",
)


def _pm2_jlist_names(*, cwd: Path | None = None) -> set[str]:
    from duckclaw.ops.toolchain import pm2_argv

    try:
        proc = subprocess.run(
            pm2_argv("jlist"),
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            timeout=12,
        )
    except (subprocess.TimeoutExpired, OSError):
        return set()
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return set()
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return set()
    if not isinstance(data, list):
        return set()
    names: set[str] = set()
    for item in data:
        if isinstance(item, dict):
            raw = (item.get("name") or "").strip()
            if raw:
                names.add(raw)
    return names


def resolve_pm2_app_name(
    candidates: tuple[str, ...],
    *,
    env_var: str = "",
    cwd: Path | None = None,
) -> str:
    """Devuelve el primer candidato registrado en PM2; si ninguno, el primero de la lista."""
    names = _pm2_jlist_names(cwd=cwd)
    if env_var:
        preferred = (os.environ.get(env_var) or "").strip()
        if preferred and (not names or preferred in names):
            return preferred
    for candidate in candidates:
        if candidate in names:
            return candidate
    return candidates[0]


def resolve_gateway_pm2_name(*, cwd: Path | None = None) -> str:
    return resolve_pm2_app_name(
        GATEWAY_PM2_CANDIDATES,
        env_var="DUCKCLAW_PM2_PROCESS_NAME",
        cwd=cwd,
    )


def resolve_db_writer_pm2_name(*, cwd: Path | None = None) -> str:
    return resolve_pm2_app_name(DB_WRITER_PM2_CANDIDATES, cwd=cwd)


def apply_pm2_name_to_argv(op_id: str, argv: list[str], *, cwd: Path | None = None) -> list[str]:
    """Sustituye nombres canónicos por el proceso PM2 real en argv de ops."""
    gateway_ops = {"pm2_restart_gateway", "pm2_start_gateway", "pm2_logs_gateway"}
    writer_ops = {"pm2_restart_db_writer", "pm2_start_db_writer"}
    if op_id in gateway_ops:
        resolved = resolve_gateway_pm2_name(cwd=cwd)
        replace_set = set(GATEWAY_PM2_CANDIDATES)
    elif op_id in writer_ops:
        resolved = resolve_db_writer_pm2_name(cwd=cwd)
        replace_set = set(DB_WRITER_PM2_CANDIDATES)
    else:
        return argv
    return [resolved if token in replace_set else token for token in argv]
