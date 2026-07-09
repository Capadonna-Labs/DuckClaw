"""Higgsfield Bridge — generacion de video/imagen via Higgsfield REST API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional

import httpx

from duckclaw.media_generation_models import (
    DEFAULT_HIGGSFIELD_I2V_ENDPOINT,
    DEFAULT_HIGGSFIELD_T2I_ENDPOINT,
    MediaGenerationResponse,
)
from duckclaw.media_usage_log import (
    MediaBudgetExceededError,
    append_media_usage_log,
    assert_media_budget_ok,
    estimate_media_cost_usd,
)
from duckclaw.utils.logger import log_tool_execution_sync

_log = logging.getLogger(__name__)

_HIGGSFIELD_API_BASE = "https://api.higgsfield.ai"
_POLL_INTERVAL_SEC = 3.0
_DEFAULT_VIDEO_TIMEOUT_SEC = 300.0
_DEFAULT_IMAGE_TIMEOUT_SEC = 120.0


def _hf_key(token_env: str | None = None) -> str:
    from duckclaw.higgsfield_env import resolve_higgsfield_api_key

    return resolve_higgsfield_api_key(token_env)


def _poll_timeout_sec(media_type: str) -> float:
    if (media_type or "").strip().lower() == "video":
        try:
            return float(
                os.environ.get("HIGGSFIELD_POLL_TIMEOUT_VIDEO_SEC")
                or str(_DEFAULT_VIDEO_TIMEOUT_SEC)
            )
        except (TypeError, ValueError):
            return _DEFAULT_VIDEO_TIMEOUT_SEC
    try:
        return float(
            os.environ.get("HIGGSFIELD_POLL_TIMEOUT_SEC")
            or str(_DEFAULT_IMAGE_TIMEOUT_SEC)
        )
    except (TypeError, ValueError):
        return _DEFAULT_IMAGE_TIMEOUT_SEC


def _run_async_from_sync(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _error_json(message: str) -> str:
    return json.dumps({"ok": False, "error": message, "success": False}, ensure_ascii=False)


def _usage_db(duckclaw_db: Any) -> Any:
    try:
        from duckclaw.forge.skills.visual_state_delta import get_visual_state_delta_hub_db

        hub = get_visual_state_delta_hub_db()
        if hub is not None:
            return hub
    except Exception:
        pass
    return duckclaw_db


def _tool_context() -> dict[str, str]:
    from duckclaw.runtime_tool_context import merge_tool_context

    return merge_tool_context()


# ── Higgsfield REST helpers ──────────────────────────────────────────────────


async def _hf_submit(
    endpoint: str,
    payload: dict[str, Any],
    api_key: str,
) -> dict[str, str]:
    """POST /v1/generations — submit a generation job."""
    url = f"{_HIGGSFIELD_API_BASE}{endpoint}"
    headers = {
        "Authorization": f"Key {api_key}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    gen_id = str(data.get("id") or data.get("generation_id") or "").strip()
    if not gen_id:
        raise ValueError("Higgsfield no devolvio generation id.")
    return {"generation_id": gen_id}


async def _hf_poll(
    *,
    generation_id: str,
    api_key: str,
    timeout_sec: float,
) -> dict[str, Any]:
    """GET /v1/generations/{id} — poll until completed or failed."""
    url = f"{_HIGGSFIELD_API_BASE}/v1/generations/{generation_id}"
    headers = {"Authorization": f"Key {api_key}"}
    deadline = time.monotonic() + timeout_sec
    last_status: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=60.0) as client:
        while time.monotonic() < deadline:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            last_status = resp.json()
            status = str(last_status.get("status") or "").lower()
            if status in ("completed", "done", "succeeded"):
                return last_status
            if status in ("failed", "error", "cancelled"):
                raise ValueError(
                    f"Higgsfield job failed: {last_status.get('error') or last_status}"
                )
            await asyncio.sleep(_POLL_INTERVAL_SEC)
    raise TimeoutError(
        f"Higgsfield no completo en {timeout_sec:.0f}s (id={generation_id})."
    )


def _extract_media_url(result: dict[str, Any], media_type: str) -> str:
    """Extract output URL from Higgsfield generation result."""
    output = result.get("output") or result.get("result") or result
    if isinstance(output, dict):
        for key in ("url", "video_url", "image_url", "media_url"):
            val = output.get(key)
            if isinstance(val, str) and val.startswith("http"):
                return val
    if isinstance(output, str) and output.startswith("http"):
        return output
    for key in ("url", "video_url", "image_url", "media_url", "output_url"):
        val = result.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
    assets = result.get("assets") or result.get("outputs") or []
    if isinstance(assets, list) and assets:
        first = assets[0]
        if isinstance(first, dict):
            for k in ("url", "video_url", "image_url"):
                v = first.get(k)
                if isinstance(v, str) and v.startswith("http"):
                    return v
        if isinstance(first, str) and first.startswith("http"):
            return first
    raise ValueError("No se encontro media_url en la respuesta Higgsfield.")


async def _download_media_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


# ── Core generation flow ─────────────────────────────────────────────────────


async def _higgsfield_generate_async(
    *,
    endpoint: str,
    body: dict[str, Any],
    prompt: str,
    aspect_ratio: str,
    media_type: str,
    duration_sec: float,
    token_env: str,
    duckclaw_db: Any,
    model_slug: str,
) -> str:
    api_key = _hf_key(token_env)
    if not api_key:
        return _error_json(
            "API key Higgsfield no configurada. Define HIGGSFIELD_API_KEY en .env del gateway."
        )

    ctx = _tool_context()
    usage_db = _usage_db(duckclaw_db)
    projected = estimate_media_cost_usd(model_slug, media_type=media_type, duration_sec=duration_sec)
    try:
        assert_media_budget_ok(usage_db, ctx["tenant_id"], projected_cost_usd=projected)
    except MediaBudgetExceededError as exc:
        return _error_json(str(exc))

    t0 = time.monotonic()
    try:
        submit = await _hf_submit(endpoint, body, api_key)
        result = await _hf_poll(
            generation_id=submit["generation_id"],
            api_key=api_key,
            timeout_sec=_poll_timeout_sec(media_type),
        )
        media_url = _extract_media_url(result, media_type)
        media_bytes = await _download_media_bytes(media_url)
    except (httpx.HTTPError, ValueError, TimeoutError, OSError) as exc:
        _log.warning("higgsfield_generate failed endpoint=%s: %s", endpoint, exc)
        return _error_json(str(exc))

    latency = time.monotonic() - t0
    cost = estimate_media_cost_usd(model_slug, media_type=media_type, duration_sec=duration_sec)

    from duckclaw.forge.skills.fal_bridge import _persist_fal_artifact

    file_path, artifact_id = _persist_fal_artifact(
        media_bytes=media_bytes,
        media_url=media_url,
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        model_endpoint=model_slug,
        media_type=media_type,
        request_id=submit["generation_id"],
        duckclaw_db=duckclaw_db,
        ctx=ctx,
    )
    try:
        append_media_usage_log(
            usage_db,
            tenant_id=ctx["tenant_id"],
            session_id=ctx.get("chat_id") or "",
            worker_id=ctx.get("worker_id") or "",
            model_endpoint=model_slug,
            media_type=media_type,
            cost_usd=cost,
            latency_sec=latency,
            media_url=media_url,
            provider="higgsfield",
        )
    except Exception:
        _log.debug("append_media_usage_log failed", exc_info=True)

    resp = MediaGenerationResponse(
        success=True,
        media_url=media_url,
        file_path=file_path,
        latency_sec=round(latency, 3),
        cost_usd=round(cost, 6),
        model_endpoint=model_slug,
        media_type=media_type,  # type: ignore[arg-type]
        message="Media generada via Higgsfield y registrada.",
    )
    payload: dict[str, Any] = resp.model_dump()
    payload["ok"] = True
    payload["artifacts"] = [file_path]
    if artifact_id:
        payload["artifact_id"] = artifact_id
    return json.dumps(payload, ensure_ascii=False)


# ── Tool implementations ─────────────────────────────────────────────────────


@log_tool_execution_sync(name="generate_higgsfield_video")
def _generate_higgsfield_video_impl(
    prompt: str,
    image_url: str = "",
    aspect_ratio: str = "16:9",
    duration_sec: float = 5.0,
    model: str = "dop-turbo",
    *,
    higgsfield_config: Optional[dict] = None,
    duckclaw_db: Any = None,
) -> str:
    pos = (prompt or "").strip()
    if not pos:
        return _error_json("El parametro prompt no puede estar vacio.")
    cfg = higgsfield_config if isinstance(higgsfield_config, dict) else {}
    token_env = str(cfg.get("token_env") or "HIGGSFIELD_API_KEY")
    model_name = str(cfg.get("default_video_model") or model).strip()
    model_slug = str(cfg.get("default_video_endpoint") or DEFAULT_HIGGSFIELD_I2V_ENDPOINT).strip()

    body: dict[str, Any] = {
        "model": model_name,
        "prompt": pos,
    }
    if image_url.strip():
        body["task"] = "image-to-video"
        body["input_images"] = [{"type": "image_url", "image_url": image_url.strip()}]
    else:
        body["task"] = "text-to-video"
    if duration_sec and duration_sec > 0:
        body["duration"] = int(duration_sec)

    return _run_async_from_sync(
        _higgsfield_generate_async(
            endpoint="/v1/generations",
            body=body,
            prompt=pos,
            aspect_ratio=aspect_ratio,
            media_type="video",
            duration_sec=duration_sec,
            token_env=token_env,
            duckclaw_db=duckclaw_db,
            model_slug=model_slug,
        )
    )


@log_tool_execution_sync(name="generate_higgsfield_image")
def _generate_higgsfield_image_impl(
    prompt: str,
    aspect_ratio: str = "16:9",
    *,
    higgsfield_config: Optional[dict] = None,
    duckclaw_db: Any = None,
) -> str:
    pos = (prompt or "").strip()
    if not pos:
        return _error_json("El parametro prompt no puede estar vacio.")
    cfg = higgsfield_config if isinstance(higgsfield_config, dict) else {}
    token_env = str(cfg.get("token_env") or "HIGGSFIELD_API_KEY")
    model_slug = str(cfg.get("default_image_endpoint") or DEFAULT_HIGGSFIELD_T2I_ENDPOINT).strip()

    body: dict[str, Any] = {
        "task": "text-to-image",
        "prompt": pos,
    }

    return _run_async_from_sync(
        _higgsfield_generate_async(
            endpoint="/v1/generations",
            body=body,
            prompt=pos,
            aspect_ratio=aspect_ratio,
            media_type="image",
            duration_sec=0,
            token_env=token_env,
            duckclaw_db=duckclaw_db,
            model_slug=model_slug,
        )
    )


# ── Registrar ─────────────────────────────────────────────────────────────────


def register_higgsfield_skill(
    tools_list: list[Any],
    higgsfield_config: Optional[dict] = None,
    *,
    duckclaw_db: Any = None,
    worker_id: str = "",
    tenant_id: str = "default",
) -> None:
    cfg = higgsfield_config if isinstance(higgsfield_config, dict) else {}
    if cfg.get("enabled") is False:
        return
    try:
        from duckclaw.forge.skills.mcp_connector_bridge import worker_has_mcp_connector

        if worker_has_mcp_connector(worker_id=worker_id, tenant_id=tenant_id):
            _log.info(
                "Higgsfield: skipping REST tools for worker=%s (MCP connector active)",
                worker_id or "?",
            )
            return
    except Exception:
        _log.debug("Higgsfield MCP preference check skipped", exc_info=True)
    token_env = str(cfg.get("token_env") or "HIGGSFIELD_API_KEY")
    if not _hf_key(token_env):
        _log.warning("Higgsfield disabled: missing %s", token_env)
        return
    try:
        from langchain_core.tools import StructuredTool
    except ImportError:
        return

    def _video(
        prompt: str,
        image_url: str = "",
        aspect_ratio: str = "16:9",
        duration_sec: float = 5.0,
        model: str = "dop-turbo",
    ) -> str:
        return _generate_higgsfield_video_impl(
            prompt,
            image_url=image_url,
            aspect_ratio=aspect_ratio,
            duration_sec=duration_sec,
            model=model,
            higgsfield_config=cfg,
            duckclaw_db=duckclaw_db,
        )

    def _image(prompt: str, aspect_ratio: str = "16:9") -> str:
        return _generate_higgsfield_image_impl(
            prompt,
            aspect_ratio=aspect_ratio,
            higgsfield_config=cfg,
            duckclaw_db=duckclaw_db,
        )

    tools_list.append(
        StructuredTool.from_function(
            _video,
            name="generate_higgsfield_video",
            description=(
                "Genera video via Higgsfield (DoP model). "
                "Parametros: prompt (descripcion), image_url (opcional, image-to-video), "
                "aspect_ratio (16:9, 9:16, 1:1), duration_sec (1-30), model (dop-turbo)."
            ),
        )
    )
    tools_list.append(
        StructuredTool.from_function(
            _image,
            name="generate_higgsfield_image",
            description=(
                "Genera imagen via Higgsfield. "
                "Parametros: prompt (descripcion), aspect_ratio (16:9, 9:16, 1:1)."
            ),
        )
    )
    _log.info("Higgsfield: registered 2 media tools")
