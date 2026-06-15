from __future__ import annotations

import asyncio
import json
import os
import re
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter(prefix="/comfyui", tags=["admin-visual-assets"])

_REPO_ROOT = Path(__file__).resolve().parents[4]
_COMFYUI_API_URL_ENV_KEY = "COMFYUI_API_URL"
_COMFYUI_TIMEOUT_SEC_ENV_KEY = "COMFYUI_TIMEOUT_SEC"
_COMFYUI_DOMAIN = "comfyui"
_COMFYUI_API_URL_KEY = "api_url"
_COMFYUI_TIMEOUT_SEC_KEY = "timeout_sec"


class ComfyuiGenerateBody(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    negative_prompt: str = Field(default="", max_length=2000)
    aspect_ratio: str = Field(default="1:1", max_length=16)
    template: str = Field(default="comfy_default", max_length=64)
    tenant_id: str | None = Field(default=None, max_length=64)


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    expected = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DUCKCLAW_ADMIN_API_KEY no configurada en el gateway",
        )
    if (x_admin_key or "").strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin key inválida")


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


def _problem(status_code: int, title: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"type": "about:blank", "title": title, "status": status_code, "detail": detail},
    )


def _admin_audit(
    action: str,
    resource: str,
    detail: str,
    *,
    actor: str = "admin-ui",
    meta: dict[str, Any] | None = None,
) -> None:
    from routers import admin as admin_router

    admin_router._admin_audit(action, resource, detail, actor=actor, meta=meta)


def _gateway_effective_tenant_id(request_tenant: str | None) -> str:
    import main as gateway_main

    raw = (request_tenant or "").strip() or "default"
    return gateway_main._effective_tenant_id(raw)


def _comfyui_runtime_settings() -> dict[str, str]:
    """Configuración ComfyUI DB-first con fallback `.env` bootstrap."""
    raw_api_env = (os.environ.get(_COMFYUI_API_URL_ENV_KEY) or "http://127.0.0.1:8188").strip()
    raw_timeout_env = (os.environ.get(_COMFYUI_TIMEOUT_SEC_ENV_KEY) or "300").strip()

    def _resolve(key: str, env_key: str, default: str) -> tuple[str, str]:
        try:
            from core.admin_identity import open_gateway_db
            from duckclaw.admin_runtime_settings import resolve_runtime_setting

            with open_gateway_db(read_only=True) as db:
                resolved = resolve_runtime_setting(
                    db,
                    tenant_id="global",
                    actor_email="",
                    domain=_COMFYUI_DOMAIN,
                    key=key,
                    env_key=env_key,
                    default=default,
                )
            return str(resolved.get("value") or default).strip(), str(resolved.get("source") or "default")
        except Exception:
            env_value = os.environ.get(env_key)
            return (env_value or default).strip(), "env" if env_value is not None else "default"

    api_url, api_source = _resolve(
        _COMFYUI_API_URL_KEY,
        _COMFYUI_API_URL_ENV_KEY,
        raw_api_env or "http://127.0.0.1:8188",
    )
    timeout_sec, timeout_source = _resolve(
        _COMFYUI_TIMEOUT_SEC_KEY,
        _COMFYUI_TIMEOUT_SEC_ENV_KEY,
        raw_timeout_env or "300",
    )
    api_url = (api_url or "http://127.0.0.1:8188").rstrip("/")
    if not re.fullmatch(r"\d{1,5}(\.\d+)?", timeout_sec or ""):
        timeout_sec = "300"
        timeout_source = "default"
    return {
        "api_url": api_url,
        "source": api_source,
        "timeout_sec": timeout_sec,
        "timeout_source": timeout_source,
    }


def _list_comfyui_templates() -> list[dict[str, Any]]:
    from duckclaw.forge import WORKFLOWS_DIR

    workflows_dir = WORKFLOWS_DIR
    templates: list[dict[str, Any]] = []
    if not workflows_dir.is_dir():
        return templates
    for path in sorted(workflows_dir.glob("*.json")):
        if path.name.endswith(".meta.json"):
            continue
        stem = path.stem
        meta_path = workflows_dir / f"{stem}.meta.json"
        aspect_presets: list[str] = []
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                presets = meta.get("aspect_presets") if isinstance(meta, dict) else None
                if isinstance(presets, dict):
                    aspect_presets = sorted(presets.keys())
            except (OSError, json.JSONDecodeError):
                pass
        templates.append(
            {
                "id": stem,
                "label": stem.replace("_", " ").title(),
                "aspect_ratios": aspect_presets or ["1:1", "16:9", "9:16", "4:3", "3:4"],
            }
        )
    return templates


@router.get("/status", dependencies=[Depends(require_admin_key)])
async def comfyui_status() -> dict[str, Any]:
    import httpx

    runtime = _comfyui_runtime_settings()
    base = runtime["api_url"]
    if not base:
        return {"ok": False, "url": "", "error": "COMFYUI_API_URL no configurada"}
    url = f"{base}/system_stats"
    started = time.perf_counter()
    try:
        checkpoints: list[str] = []
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            try:
                oi = await client.get(f"{base}/object_info/CheckpointLoaderSimple")
                if oi.status_code == 200:
                    body = oi.json()
                    node = body.get("CheckpointLoaderSimple") if isinstance(body, dict) else {}
                    req = node.get("input", {}).get("required", {}) if isinstance(node, dict) else {}
                    ckpt_cfg = req.get("ckpt_name") if isinstance(req, dict) else None
                    if isinstance(ckpt_cfg, list) and ckpt_cfg and isinstance(ckpt_cfg[0], list):
                        checkpoints = [str(x) for x in ckpt_cfg[0] if str(x).strip()]
            except Exception:
                checkpoints = []
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return {
            "ok": True,
            "url": base,
            "source": runtime["source"],
            "runtime_key": "comfyui.api_url",
            "timeout_sec": runtime["timeout_sec"],
            "timeout_source": runtime["timeout_source"],
            "latency_ms": latency_ms,
            "system": data if isinstance(data, dict) else {},
            "checkpoints": checkpoints,
            "checkpoints_ready": len(checkpoints) > 0,
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": base,
            "source": runtime["source"],
            "runtime_key": "comfyui.api_url",
            "timeout_sec": runtime["timeout_sec"],
            "timeout_source": runtime["timeout_source"],
            "error": str(exc)[:500],
            "checkpoints": [],
            "checkpoints_ready": False,
        }


@router.get("/templates", dependencies=[Depends(require_admin_key)])
async def comfyui_templates() -> dict[str, Any]:
    items = _list_comfyui_templates()
    return {"templates": items, "default": "comfy_default"}


@router.post("/generate", dependencies=[Depends(require_admin_key)])
async def comfyui_generate(
    body: ComfyuiGenerateBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.forge.skills.comfyui_bridge import (
        _generate_visual_asset_impl,
        configure_visual_generation_context,
    )

    tenant_id = _gateway_effective_tenant_id((body.tenant_id or "default").strip() or "default")
    configure_visual_generation_context(
        tenant_id=tenant_id,
        user_id=(actor or "admin-ui").strip() or "admin-ui",
    )

    runtime = _comfyui_runtime_settings()
    cfg = {
        "enabled": True,
        "template": (body.template or "comfy_default").strip() or "comfy_default",
        "api_url": runtime["api_url"],
        "timeout_sec": runtime["timeout_sec"],
    }

    def _run() -> str:
        return _generate_visual_asset_impl(
            body.prompt.strip(),
            negative_prompt=body.negative_prompt or "",
            aspect_ratio=body.aspect_ratio or "1:1",
            comfyui_config=cfg,
        )

    try:
        raw = await asyncio.to_thread(_run)
    except TimeoutError as exc:
        raise _problem(
            504,
            f"Timeout generando en ComfyUI ({exc}). Aumenta COMFYUI_TIMEOUT_SEC si usas MPS.",
            "",
        ) from exc
    except Exception as exc:
        raise _problem(
            502,
            f"Error inesperado en bridge ComfyUI: {type(exc).__name__}: {exc}",
            "",
        ) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise _problem(502, "Respuesta inválida del bridge ComfyUI", raw[:500]) from None
    if not isinstance(payload, dict):
        raise _problem(502, "Respuesta inválida del bridge ComfyUI", "")
    if not payload.get("ok"):
        raise _problem(400, str(payload.get("error") or "Error ComfyUI"), "")
    _admin_audit(
        "comfyui.generate",
        tenant_id,
        f"template={cfg['template']}",
        actor=actor,
    )
    return payload
