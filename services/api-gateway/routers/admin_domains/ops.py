from __future__ import annotations

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel

from routers.admin_domains.admin_common import admin_audit, problem, require_admin_key as _require_admin_key_impl
from duckclaw.ops.pm2_names import apply_pm2_name_to_argv

router = APIRouter(prefix="/ops", tags=["admin-ops"])

_REPO_ROOT = Path(__file__).resolve().parents[4]

from duckclaw.ops.pm2_recycle import pm2_recycle_db_writer_bash_lc, pm2_recycle_gateway_bash_lc

_PM2_RECYCLE_GATEWAY = pm2_recycle_gateway_bash_lc()
_PM2_RECYCLE_DB_WRITER = pm2_recycle_db_writer_bash_lc()

_OPS_ALLOWLIST: dict[str, list[str]] = {
    "pm2_list": ["pm2", "list"],
    "pm2_status": ["pm2", "status"],
    "pm2_restart_gateway": ["bash", "-lc", _PM2_RECYCLE_GATEWAY],
    "pm2_restart_db_writer": ["bash", "-lc", _PM2_RECYCLE_DB_WRITER],
    "pm2_start_db_writer": ["bash", "-lc", _PM2_RECYCLE_DB_WRITER],
    "pm2_start_gateway": ["bash", "-lc", _PM2_RECYCLE_GATEWAY],
    "pm2_logs_gateway": ["pm2", "logs", "DuckClaw-Gateway", "--lines", "40", "--nostream"],
    "pm2_start_mcp": ["pm2", "start", "config/ecosystem.mcp.config.cjs"],
    "pm2_restart_mcp": ["pm2", "restart", "DuckClaw-MCP", "--update-env"],
    "pm2_logs_mcp": ["pm2", "logs", "DuckClaw-MCP", "--lines", "40", "--nostream"],
    "pm2_start_comfyui": ["pm2", "start", "config/ecosystem.comfyui.config.cjs", "--update-env"],
    "pm2_restart_comfyui": ["pm2", "restart", "ComfyUI", "--update-env"],
    "pm2_logs_comfyui": ["pm2", "logs", "ComfyUI", "--lines", "40", "--nostream"],
    "build_edge_native": ["bash", "scripts/build_edge_native.sh"],
    "pm2_start_edge_streamlit": ["pm2", "start", "config/ecosystem.edge-devices.config.cjs", "--update-env"],
    "pm2_restart_edge_streamlit": ["pm2", "restart", "Edge-Streamlit", "--update-env"],
    "pm2_logs_edge_streamlit": ["pm2", "logs", "Edge-Streamlit", "--lines", "40", "--nostream"],
    "android_adb_status": ["__android_adb_status__"],
    "android_adb_connect": ["__android_adb_connect__"],
    "android_expand_notifications": ["__android_expand_notifications__"],
    "android_collapse_notifications": ["__android_collapse_notifications__"],
    "pm2_start_android_mcp": ["pm2", "start", "config/ecosystem.android-mcp.config.cjs", "--update-env"],
    "pm2_restart_android_mcp": ["pm2", "restart", "Android-MCP", "--update-env"],
    "doctor": ["uv", "run", "duckops", "doctor"],
    "bootstrap_dbs": ["uv", "run", "duckops", "db", "bootstrap"],
}


class OpsRunBody(BaseModel):
    op_id: str
    params: dict[str, Any] | None = None


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
        return "DuckClaw-Gateway" in stdout or "duckclaw-gateway" in stdout
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
        "build_edge_native": "Compilar libedgecore (integrations/edge-devices/native)",
        "pm2_start_edge_streamlit": "Iniciar dashboard Edge (Streamlit :8501)",
        "pm2_restart_edge_streamlit": "Reiniciar dashboard Edge (Streamlit)",
        "pm2_logs_edge_streamlit": "Últimas líneas log Edge Streamlit",
        "android_adb_status": "Estado ADB + Android MCP",
        "android_adb_connect": "Conectar ADB wireless (ANDROID_ADB_HOST)",
        "android_expand_notifications": "Abrir panel notificaciones (ADB expand-notifications)",
        "android_collapse_notifications": "Cerrar panel notificaciones (ADB collapse)",
        "pm2_start_android_mcp": "Iniciar Android-MCP (ecosystem.android-mcp.config.cjs)",
        "pm2_restart_android_mcp": "Reiniciar Android-MCP",
        "doctor": "Diagnóstico local (duckops doctor)",
        "bootstrap_dbs": "Bootstrap DuckDB (uv run duckops db bootstrap)",
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
    if op_id == "restart_stack":
        from duckclaw.spawn_profile import spawn_inline_writes_enabled

        if spawn_inline_writes_enabled():
            from duckclaw.desktop_sidecar_restart import restart_desktop_sidecar

            result = await restart_desktop_sidecar()
            _admin_audit("ops.run", op_id, "desktop sidecar restart", actor=actor, meta=result)
            return {"op_id": op_id, **result}

    if op_id in ("android_adb_status", "android_adb_connect"):
        from duckclaw.mcp_android_adb import android_adb_connect, android_device_status

        if op_id == "android_adb_status":
            payload = android_device_status()
        else:
            params = body.params or {}
            host = str(params.get("host") or "").strip() or None
            debug_port = params.get("debug_port")
            if debug_port is not None:
                debug_port = str(debug_port).strip() or None
            payload = android_adb_connect(host=host, debug_port=debug_port)
        ok = bool(payload.get("ok"))
        result = {
            "exit_code": 0 if ok else 1,
            "stdout": json.dumps(payload, ensure_ascii=False),
            "stderr": str(payload.get("error") or payload.get("stderr") or "")[:8000],
        }
        _admin_audit("ops.run", op_id, op_id, actor=actor, meta={"ok": ok})
        return {"ok": ok, "op_id": op_id, **result}

    if op_id in ("android_expand_notifications", "android_collapse_notifications"):
        from duckclaw.mcp_android_adb import (
            android_collapse_statusbar,
            android_expand_notifications,
        )

        payload = (
            android_expand_notifications()
            if op_id == "android_expand_notifications"
            else android_collapse_statusbar()
        )
        ok = bool(payload.get("ok"))
        result = {
            "exit_code": 0 if ok else 1,
            "stdout": json.dumps(payload, ensure_ascii=False),
            "stderr": str(payload.get("error") or payload.get("stderr") or "")[:8000],
        }
        _admin_audit("ops.run", op_id, op_id, actor=actor, meta={"ok": ok})
        return {"ok": ok, "op_id": op_id, **result}

    argv = _OPS_ALLOWLIST.get(op_id)
    if not argv:
        raise _problem(400, "Comando no permitido", op_id)

    resolved = _resolve_ops_argv(argv)
    resolved = apply_pm2_name_to_argv(op_id, resolved, cwd=_repo_root())

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
