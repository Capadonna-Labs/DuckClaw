"""Admin domain: manage PM2 cron-scheduled jobs (list/status/logs/trigger/start/stop).

Generic — filters to whatever PM2 processes declare a ``cron_restart`` schedule on
*this* machine, no hardcoded job names or paths. Any vertical's own cron jobs show up
here automatically once registered in PM2; nothing vertical-specific lives in this
module.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

_ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE_RE.sub("", text or "")

from fastapi import APIRouter, Depends, Header

from duckclaw.ops.toolchain import ToolchainError, run_pm2
from routers.admin_domains.admin_common import admin_audit, problem
from routers.admin_domains.admin_common import require_admin_key as _require_admin_key_impl

router = APIRouter(prefix="/crons", tags=["admin-crons"])


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    _require_admin_key_impl(x_admin_key)


def actor_from_header(x_actor: str | None = Header(None, alias="X-Duckclaw-Actor")) -> str:
    raw = (x_actor or "").strip()[:128]
    return raw or "admin-ui"


async def _run_pm2(*args: str, timeout: int = 60):
    try:
        return await asyncio.to_thread(run_pm2, *args, timeout=timeout)
    except ToolchainError as exc:
        raise problem(503, "PM2 no disponible", str(exc)) from exc


def _cron_processes_from_jlist(stdout: str) -> list[dict[str, Any]]:
    try:
        procs = json.loads(stdout or "[]")
    except json.JSONDecodeError as exc:
        raise problem(500, "Salida de PM2 inválida", str(exc)) from exc
    out: list[dict[str, Any]] = []
    if not isinstance(procs, list):
        return out
    for p in procs:
        if not isinstance(p, dict):
            continue
        env = p.get("pm2_env") or {}
        cron = str(env.get("cron_restart") or "").strip()
        if not cron:
            continue
        name = p.get("name")
        if not name:
            continue
        out.append(
            {
                "name": name,
                "pm_id": p.get("pm_id"),
                "cron": cron,
                "status": env.get("status"),
                "restarts": env.get("restart_time"),
                "unstable_restarts": env.get("unstable_restarts"),
                "cwd": env.get("pm_cwd"),
                "interpreter": env.get("exec_interpreter") or None,
                "script": env.get("pm_exec_path"),
                "created_at": env.get("created_at"),
                "pm_uptime": env.get("pm_uptime"),
            }
        )
    return out


async def _list_cron_processes() -> list[dict[str, Any]]:
    proc = await _run_pm2("jlist", timeout=30)
    if proc.returncode != 0:
        raise problem(500, "PM2 no respondió", (proc.stderr or proc.stdout or "").strip())
    return _cron_processes_from_jlist(proc.stdout or "[]")


async def _guard_known_cron(name: str) -> None:
    """Only allow start/stop/run/logs on processes that currently declare a cron schedule.

    Prevents this endpoint from being used to control arbitrary PM2 processes
    (e.g. the Gateway itself) — the allow-list is the live cron_restart set, not
    anything hardcoded.
    """
    clean = (name or "").strip()
    known = {p["name"] for p in await _list_cron_processes()}
    if not clean or clean not in known:
        raise problem(404, "Cron no encontrado", f"'{clean}' no tiene cron_restart configurado en PM2.")


def _tail(text: str | None, n: int = 4000) -> str:
    return (text or "")[-n:]


@router.get("", dependencies=[Depends(require_admin_key)])
async def list_crons() -> dict[str, Any]:
    return {"crons": await _list_cron_processes()}


@router.post("/{name}/run", dependencies=[Depends(require_admin_key)])
async def run_cron_now(name: str, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    await _guard_known_cron(name)
    proc = await _run_pm2("restart", name)
    ok = proc.returncode == 0
    admin_audit("crons.run", name, "pm2 restart (trigger now)", actor=actor, meta={"ok": ok})
    return {"ok": ok, "stdout": _tail(proc.stdout), "stderr": _tail(proc.stderr)}


@router.post("/{name}/stop", dependencies=[Depends(require_admin_key)])
async def stop_cron(name: str, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    await _guard_known_cron(name)
    proc = await _run_pm2("stop", name)
    ok = proc.returncode == 0
    admin_audit("crons.stop", name, "pm2 stop", actor=actor, meta={"ok": ok})
    return {"ok": ok, "stdout": _tail(proc.stdout), "stderr": _tail(proc.stderr)}


@router.post("/{name}/start", dependencies=[Depends(require_admin_key)])
async def start_cron(name: str, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    await _guard_known_cron(name)
    proc = await _run_pm2("start", name)
    ok = proc.returncode == 0
    admin_audit("crons.start", name, "pm2 start", actor=actor, meta={"ok": ok})
    return {"ok": ok, "stdout": _tail(proc.stdout), "stderr": _tail(proc.stderr)}


@router.get("/{name}/logs", dependencies=[Depends(require_admin_key)])
async def cron_logs(name: str, lines: int = 100) -> dict[str, Any]:
    await _guard_known_cron(name)
    n = max(1, min(int(lines), 1000))
    proc = await _run_pm2("logs", name, "--lines", str(n), "--nostream", timeout=30)
    return {
        "ok": proc.returncode == 0,
        "stdout": _strip_ansi(proc.stdout or ""),
        "stderr": _strip_ansi(proc.stderr or ""),
    }
