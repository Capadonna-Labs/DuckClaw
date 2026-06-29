from __future__ import annotations

import asyncio
import os
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from routers.admin_domains.admin_common import admin_audit, problem, require_admin_key as _require_admin_key_impl

router = APIRouter(prefix="/ops", tags=["admin-ops"])

_REPO_ROOT = Path(__file__).resolve().parents[4]

_OPS_ALLOWLIST: dict[str, list[str]] = {
    "pm2_list": ["pm2", "list"],
    "pm2_status": ["pm2", "status"],
    "pm2_restart_gateway": ["pm2", "restart", "DuckClaw-Gateway", "--update-env"],
    "pm2_restart_db_writer": ["pm2", "restart", "DuckClaw-DB-Writer", "--update-env"],
    "pm2_start_db_writer": ["pm2", "start", "config/ecosystem.db-writer.config.cjs", "--update-env"],
    "pm2_start_gateway": [
        "pm2",
        "start",
        "config/ecosystem.api.config.cjs",
        "--only",
        "DuckClaw-Gateway",
        "--update-env",
    ],
    "pm2_logs_gateway": ["pm2", "logs", "DuckClaw-Gateway", "--lines", "40", "--nostream"],
    "pm2_start_mcp": ["pm2", "start", "config/ecosystem.mcp.config.cjs"],
    "pm2_restart_mcp": ["pm2", "restart", "DuckClaw-MCP", "--update-env"],
    "pm2_logs_mcp": ["pm2", "logs", "DuckClaw-MCP", "--lines", "40", "--nostream"],
    "pm2_start_comfyui": ["pm2", "start", "config/ecosystem.comfyui.config.cjs", "--update-env"],
    "pm2_restart_comfyui": ["pm2", "restart", "ComfyUI", "--update-env"],
    "pm2_logs_comfyui": ["pm2", "logs", "ComfyUI", "--lines", "40", "--nostream"],
    "doctor": ["uv", "run", "python", "scripts/doctor.py"],
    "bootstrap_dbs": ["uv", "run", "python", "scripts/bootstrap_dbs.py"],
}


class OpsRunBody(BaseModel):
    op_id: str


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    _require_admin_key_impl(x_admin_key)


def actor_from_header(x_actor: str | None = Header(None, alias="X-Duckclaw-Actor")) -> str:
    raw = (x_actor or "").strip()[:128]
    if raw and raw != "admin-ui":
        return raw
    admin_email = os.environ.get("DUCKCLAW_ADMIN_EMAIL", "").strip()
    if admin_email and "@" in admin_email:
        return admin_email[:128]
    return raw or "admin-ui"


def _repo_root() -> Path:
    raw = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    return Path(raw) if raw else _REPO_ROOT


def _problem(status_code: int, title: str, detail: str):
    return problem(status_code, title, detail)


def _admin_audit(
    action: str,
    resource: str,
    detail: str,
    *,
    actor: str = "admin-ui",
    meta: dict[str, Any] | None = None,
) -> None:
    admin_audit(action, resource, detail, actor=actor, meta=meta)


def _pm2_restart_interrupted(op_id: str, exit_code: int, stdout: str) -> bool:
    """PM2 reinició el gateway y mató el proceso que ejecutaba el comando (SIGINT → -2)."""
    if exit_code != -2:
        return False
    if "Applying action restartProcessId" not in stdout:
        return False
    if op_id == "pm2_restart_gateway":
        return "DuckClaw-Gateway" in stdout
    return False


def _normalize_ops_result(op_id: str, result: dict[str, Any]) -> dict[str, Any]:
    exit_code = int(result.get("exit_code") or 1)
    stdout = str(result.get("stdout") or "")
    if _pm2_restart_interrupted(op_id, exit_code, stdout):
        return {**result, "exit_code": 0}
    return result


@router.get("/commands", dependencies=[Depends(require_admin_key)])
async def list_ops_commands() -> dict[str, Any]:
    labels = {
        "pm2_list": "PM2 — listar procesos",
        "pm2_status": "PM2 — estado",
        "pm2_restart_gateway": "Reiniciar DuckClaw-Gateway",
        "pm2_restart_db_writer": "Reiniciar DuckClaw-DB-Writer",
        "pm2_start_db_writer": "Iniciar DuckClaw-DB-Writer",
        "pm2_start_gateway": "Iniciar DuckClaw-Gateway",
        "pm2_logs_gateway": "Últimas líneas log Gateway",
        "pm2_start_mcp": "Iniciar DuckClaw-MCP (ecosystem.mcp.config.cjs)",
        "pm2_restart_mcp": "Reiniciar DuckClaw-MCP",
        "pm2_logs_mcp": "Últimas líneas log MCP",
        "pm2_start_comfyui": "Iniciar ComfyUI (ecosystem.comfyui.config.cjs)",
        "pm2_restart_comfyui": "Reiniciar ComfyUI",
        "pm2_logs_comfyui": "Últimas líneas log ComfyUI",
        "doctor": "Diagnóstico local (doctor.py)",
        "bootstrap_dbs": "Bootstrap DuckDB (tablas agent_config, etc.)",
    }
    return {
        "commands": [
            {"id": k, "label": labels.get(k, k), "argv": v}
            for k, v in _OPS_ALLOWLIST.items()
        ]
    }


def _resolve_ops_argv(argv: list[str]) -> list[str]:
    if not argv:
        return argv
    if argv[0] == "pm2":
        from duckclaw.ops.toolchain import pm2_argv

        return pm2_argv(*argv[1:])
    if argv[0] == "uv":
        from duckclaw.ops.toolchain import resolve_uv

        uv = resolve_uv()
        if uv:
            return [uv, *argv[1:]]
    return argv


@router.post("/run", dependencies=[Depends(require_admin_key)])
async def run_ops_command(
    body: OpsRunBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    op_id = (body.op_id or "").strip()
    argv = _OPS_ALLOWLIST.get(op_id)
    if not argv:
        raise _problem(400, "Comando no permitido", op_id)

    resolved = _resolve_ops_argv(argv)

    def _run() -> dict[str, Any]:
        proc = subprocess.run(
            resolved,
            cwd=str(_repo_root()),
            capture_output=True,
            text=True,
            timeout=90,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[-12000:],
            "stderr": (proc.stderr or "")[-8000:],
        }

    try:
        result = await asyncio.to_thread(_run)
    except subprocess.TimeoutExpired:
        raise _problem(408, "Timeout ejecutando comando", op_id) from None
    except Exception as exc:
        raise _problem(500, "Error ejecutando comando", str(exc)) from exc

    result = _normalize_ops_result(op_id, result)
    if op_id in ("pm2_start_comfyui", "pm2_restart_comfyui") and result.get("exit_code") == 0:
        import time

        from duckclaw.forge.skills.comfyui_bridge import clear_all_comfy_generations, reset_comfyui_runtime

        clear_all_comfy_generations()
        await asyncio.sleep(6)
        comfy_reset = await asyncio.to_thread(reset_comfyui_runtime)
        result["comfyui_reset"] = comfy_reset
    _admin_audit("ops.run", op_id, " ".join(argv), actor=actor, meta=result)
    return {"ok": result.get("exit_code") == 0, "op_id": op_id, **result}
