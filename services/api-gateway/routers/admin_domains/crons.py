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

from fastapi import APIRouter, Depends, Header, Request

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
        script = env.get("pm_exec_path")
        out.append(
            {
                "name": name,
                "pm_id": p.get("pm_id"),
                "cron": cron,
                "description": _describe_cron_process(str(name), str(script or "")),
                "status": env.get("status"),
                "restarts": env.get("restart_time"),
                "unstable_restarts": env.get("unstable_restarts"),
                "cwd": env.get("pm_cwd"),
                "interpreter": env.get("exec_interpreter") or None,
                "script": script,
                "created_at": env.get("created_at"),
                "pm_uptime": env.get("pm_uptime"),
            }
        )
    return out


def _describe_cron_process(name: str, script: str) -> str:
    clean = str(name or "").strip()
    match = re.fullmatch(
        r"[a-z]+-([a-z0-9_.-]+)-(buy|sell)-([0-9]+)(?:-shares)?(?:-open)?-([0-9]{8})",
        clean,
        flags=re.IGNORECASE,
    )
    if match:
        ticker, action, quantity, raw_date = match.groups()
        date = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}"
        action_label = "BUY" if action.lower() == "buy" else "SELL"
        return f"{action_label} {quantity} {ticker.upper()} en apertura {date}"
    if script:
        return str(script).rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    return clean or "Cron PM2"


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


def _load_chat_schedules() -> list[dict[str, Any]]:
    """/crons schedules stored per chat in agent_config (hub + vaults), the same rows the
    heartbeat scans. Read-only; PM2 crons are a different thing (list_crons)."""
    from pathlib import Path

    from duckclaw.commands.crons import (
        chat_id_from_goals_cron_wall_key,
        chat_id_from_goals_delta_config_key,
        format_goals_delta_interval_human,
    )
    from duckclaw.duckdb_read_compat import duckclaw_open_for_read_scan
    from duckclaw.gateway_db import iter_goals_ticker_duckdb_paths
    from duckclaw.runtime.scheduling.cron_wall_schedule import format_cron_wall_human, load_wall_items

    out: list[dict[str, Any]] = []
    for path in iter_goals_ticker_duckdb_paths():
        try:
            with duckclaw_open_for_read_scan(path) as db:
                raw = db.query(
                    "SELECT key, value FROM agent_config "
                    "WHERE key LIKE 'chat_%_goals_cron_wall' OR key LIKE 'chat_%_goals_delta_seconds' "
                    "OR key LIKE 'chat_%_goals_proactive_last_fire_epoch' "
                    "OR key LIKE 'chat_%_goals_proactive_tenant_id' OR key LIKE 'chat_%_worker_id'"
                )
        except Exception:
            continue  # vault locked/missing agent_config: skip, like the heartbeat
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        kv = {str(r.get("key")): str(r.get("value") or "").strip() for r in rows if isinstance(r, dict)}
        for key, value in kv.items():
            if not value:
                continue
            entries: list[dict[str, Any]] = []
            if (cid := chat_id_from_goals_cron_wall_key(key)) is not None:
                for spec in load_wall_items(value):
                    entries.append(
                        {
                            "chat_id": cid,
                            "kind": "reloj",
                            "cron_id": str(spec.get("id") or ""),
                            "schedule": format_cron_wall_human(spec),
                            "prompt": str(spec.get("prompt") or "") or "Revisión de /goals",
                            "remove_hint": f"/crons --rm {spec.get('id')}",
                            "_last": spec.get("last_fire"),
                        }
                    )
            elif (cid := chat_id_from_goals_delta_config_key(key)) is not None:
                try:
                    secs = int(value)
                except ValueError:
                    continue
                if secs > 0:
                    entries.append(
                        {
                            "chat_id": cid,
                            "kind": "intervalo",
                            "cron_id": "delta",
                            "schedule": f"Cada {format_goals_delta_interval_human(secs)}",
                            "prompt": "Revisión de /goals",
                            "remove_hint": "/crons --delta off",
                            "_last": None,
                        }
                    )
            for item in entries:
                _append_schedule(out, item, kv, path)
    return out


def _append_schedule(out: list[dict[str, Any]], item: dict[str, Any], kv: dict[str, str], path: str) -> None:
    from pathlib import Path

    cid_key = f"chat_{item['chat_id']}"
    # Per-cron last run (multi-cron); legacy single schedules used the shared key.
    last = str(item.pop("_last", None) or kv.get(f"{cid_key}_goals_proactive_last_fire_epoch") or "")
    item["last_fire_epoch"] = float(last) if last.replace(".", "", 1).isdigit() else None
    item["source"] = Path(path).name
    item["tenant_id"] = kv.get(f"{cid_key}_goals_proactive_tenant_id") or ""
    item["worker_id"] = kv.get(f"{cid_key}_worker_id") or ""
    # Same gates the heartbeat applies before firing (services/heartbeat/main.py).
    if not item["worker_id"] or item["worker_id"].lower() == "manager":
        item["status"], item["status_detail"] = "inactivo", "el chat no tiene un worker asignado"
    elif not item["tenant_id"]:
        item["status"], item["status_detail"] = "inactivo", "falta el tenant de la programación"
    else:
        item["status"], item["status_detail"] = "activo", f"worker {item['worker_id']}"
    out.append(item)


def _skill_descriptions(items: list[dict[str, Any]]) -> None:
    """Description column: the directive skill's own text for "/skill" prompts."""
    from core.admin_identity import open_gateway_db
    from duckclaw.directive_skills import expand_directive_skill

    for item in items:
        prompt = str(item.get("prompt") or "")
        if item["kind"] == "intervalo":
            item["description"] = "Revisión periódica de las metas de /goals"
            continue
        if not prompt.startswith("/"):
            item["description"] = prompt[:160]
            continue
        try:
            with open_gateway_db(read_only=True) as db:
                _msg, rest = expand_directive_skill(db, prompt, tenant_id=item.get("tenant_id") or "default")
                expanded = _msg if rest is not None else ""
        except Exception:
            expanded = ""
        # Expanded = "[DIRECTIVA ACTIVA: /x]\n<texto>": the description is the text.
        body = expanded.split("\n", 1)[1].strip() if "\n" in expanded else ""
        item["description"] = (body[:160] + "…") if len(body) > 160 else (body or "Skill no encontrado en el catálogo")


@router.get("/chat-schedules", dependencies=[Depends(require_admin_key)])
async def list_chat_schedules(request: Request) -> dict[str, Any]:
    items = await asyncio.to_thread(_load_chat_schedules)
    await asyncio.to_thread(_skill_descriptions, items)
    from core.admin_conversations import get_conversation_meta

    redis_client = getattr(request.app.state, "redis", None)
    for item in items:
        title = ""
        try:
            meta = await get_conversation_meta(redis_client, item.get("tenant_id") or "default", item["chat_id"])
            title = str(getattr(meta, "title", "") or "").strip() if meta else ""
        except Exception:
            title = ""
        item["name"] = title or item["chat_id"]
    return {"schedules": items}


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
