"""Fal.ai Bridge — generacion multimedia cloud (Flux, Kling, ComfyUI serverless)."""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Literal, Optional

import httpx

from duckclaw.media_generation_models import (
    DEFAULT_FLUX_DEV_ENDPOINT,
    DEFAULT_FLUX_IMG2IMG_ENDPOINT,
    DEFAULT_FLUX_KONTEXT_PRO_ENDPOINT,
    DEFAULT_KLING_VIDEO_ENDPOINT,
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

_FAL_QUEUE_BASE = "https://queue.fal.run"
_MAX_B64_IN_TOOL_RESPONSE = 500_000
_POLL_INTERVAL_SEC = 2.0
_DEFAULT_IMAGE_TIMEOUT_SEC = 120.0
_DEFAULT_VIDEO_TIMEOUT_SEC = 300.0


def _fal_key(token_env: str | None = None) -> str:
    from duckclaw.fal_env import resolve_fal_api_key

    return resolve_fal_api_key(token_env)


def _poll_timeout_sec(media_type: str) -> float:
    if (media_type or "").strip().lower() == "video":
        try:
            return float(os.environ.get("FAL_POLL_TIMEOUT_VIDEO_SEC") or str(_DEFAULT_VIDEO_TIMEOUT_SEC))
        except (TypeError, ValueError):
            return _DEFAULT_VIDEO_TIMEOUT_SEC
    try:
        return float(os.environ.get("FAL_POLL_TIMEOUT_SEC") or str(_DEFAULT_IMAGE_TIMEOUT_SEC))
    except (TypeError, ValueError):
        return _DEFAULT_IMAGE_TIMEOUT_SEC


def _aspect_to_image_size(aspect_ratio: str) -> str:
    ar = (aspect_ratio or "16:9").strip()
    if ar == "1:1":
        return "square_hd"
    if ar == "9:16":
        return "portrait_16_9"
    return "landscape_16_9"


def _run_async_from_sync(coro) -> Any:
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
    from duckclaw.capadonna_plugin import load_capadonna_lib

    _qtc = load_capadonna_lib("quant_tool_context")
    tenant_id = _qtc.get_quant_tool_tenant_id() if _qtc is not None else "default"
    user_id = _qtc.get_quant_tool_user_id() if _qtc is not None else "default"
    chat_id = _qtc.get_quant_tool_chat_id() if _qtc is not None else ""
    worker_id = ""
    if _qtc is not None:
        _gw = getattr(_qtc, "get_quant_tool_worker_id", None)
        if callable(_gw):
            worker_id = str(_gw() or "")
    return {
        "tenant_id": tenant_id or "default",
        "user_id": user_id or "default",
        "chat_id": chat_id or "",
        "worker_id": worker_id or "",
    }


def _state_delta_base() -> dict[str, str]:
    from duckclaw.forge.skills.comfyui_bridge import _state_delta_base as _comfy_base

    return _comfy_base()


def _fal_queue_urls_from_submit(data: dict[str, Any], endpoint: str, request_id: str) -> tuple[str, str]:
    """Usa status_url/response_url del submit (Fal omite subpaths como /dev en la cola)."""
    status_url = str(data.get("status_url") or "").strip()
    response_url = str(data.get("response_url") or "").strip()
    if not status_url or not response_url:
        base = (endpoint or "").strip().rstrip("/")
        if "/" in base:
            base = base.rsplit("/", 1)[0]
        status_url = status_url or f"{_FAL_QUEUE_BASE}/{base}/requests/{request_id}/status"
        response_url = response_url or f"{_FAL_QUEUE_BASE}/{base}/requests/{request_id}"
    return status_url, response_url


async def _fal_submit(endpoint: str, payload: dict[str, Any], api_key: str) -> dict[str, str]:
    url = f"{_FAL_QUEUE_BASE}/{endpoint.lstrip('/')}"
    headers = {"Authorization": f"Key {api_key}", "Content-Type": "application/json"}
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(url, json=payload, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    request_id = str(data.get("request_id") or data.get("requestId") or "").strip()
    if not request_id:
        raise ValueError("Fal.ai no devolvio request_id.")
    status_url, response_url = _fal_queue_urls_from_submit(data, endpoint, request_id)
    return {
        "request_id": request_id,
        "status_url": status_url,
        "response_url": response_url,
    }


async def _fal_poll(
    *,
    status_url: str,
    response_url: str,
    request_id: str,
    api_key: str,
    timeout_sec: float,
) -> dict[str, Any]:
    headers = {"Authorization": f"Key {api_key}"}
    deadline = time.monotonic() + timeout_sec
    last_status: dict[str, Any] = {}
    async with httpx.AsyncClient(timeout=60.0) as client:
        while time.monotonic() < deadline:
            resp = await client.get(status_url, headers=headers)
            resp.raise_for_status()
            last_status = resp.json()
            status = str(last_status.get("status") or "").upper()
            if status == "COMPLETED":
                break
            if status in ("FAILED", "ERROR"):
                raise ValueError(f"Fal.ai job failed: {last_status.get('error') or last_status}")
            await asyncio.sleep(_POLL_INTERVAL_SEC)
        else:
            raise TimeoutError(f"Fal.ai no completo en {timeout_sec:.0f}s (request_id={request_id}).")

        result_url = str(last_status.get("response_url") or response_url or "").strip()
        if not result_url:
            raise ValueError("Fal.ai COMPLETED sin response_url.")
        result_resp = await client.get(result_url, headers=headers)
        if result_resp.status_code == 400:
            detail = ""
            try:
                detail = str((result_resp.json() or {}).get("detail") or "")
            except (json.JSONDecodeError, TypeError, ValueError):
                detail = result_resp.text[:200]
            if "still in progress" in detail.lower():
                raise TimeoutError(
                    f"Fal.ai status COMPLETED pero resultado pendiente (request_id={request_id})."
                )
        result_resp.raise_for_status()
        payload = result_resp.json()
        return payload if isinstance(payload, dict) else {"payload": payload}


def _extract_media_url(result: dict[str, Any], media_type: str) -> str:
    payload = result.get("response") or result.get("payload") or result
    if not isinstance(payload, dict):
        raise ValueError("Respuesta Fal sin payload JSON.")
    if (media_type or "").strip().lower() == "video":
        video = payload.get("video")
        if isinstance(video, dict) and video.get("url"):
            return str(video["url"])
        if isinstance(video, str) and video.startswith("http"):
            return video
        videos = payload.get("videos")
        if isinstance(videos, list) and videos:
            first = videos[0]
            if isinstance(first, dict) and first.get("url"):
                return str(first["url"])
    images = payload.get("images")
    if isinstance(images, list) and images:
        first = images[0]
        if isinstance(first, dict) and first.get("url"):
            return str(first["url"])
        if isinstance(first, str) and first.startswith("http"):
            return first
    image = payload.get("image")
    if isinstance(image, dict) and image.get("url"):
        return str(image["url"])
    for key in ("url", "output", "result"):
        val = payload.get(key)
        if isinstance(val, str) and val.startswith("http"):
            return val
    raise ValueError("No se encontro media_url en la respuesta Fal.")


async def _download_media_bytes(url: str) -> bytes:
    async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
        resp = await client.get(url)
        resp.raise_for_status()
        return resp.content


def _guess_ext(data: bytes, media_type: str) -> str:
    if (media_type or "").strip().lower() == "video":
        return ".mp4"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if len(data) >= 2 and data[:2] == b"\xff\xd8":
        return ".jpg"
    return ".png"


def _denoise_to_strength(denoise: float | None) -> float:
    """Mapea denoise ComfyUI (0.35-0.75) a strength Fal img2img (0.5-0.98)."""
    den = 0.55 if denoise is None else float(denoise)
    return max(0.5, min(0.98, 0.5 + den * 0.65))


def _is_kontext_edit_endpoint(endpoint: str) -> bool:
    """True si el endpoint Fal es de la familia FLUX Kontext (edicion in-context)."""
    ep = (endpoint or "").strip().lower()
    return "kontext" in ep


def _enrich_kontext_edit_prompt(edit_prompt: str) -> str:
    """Envuelve el prompt del usuario para ediciones locales sin regenerar toda la escena."""
    user_text = (edit_prompt or "").strip()
    return (
        f"Edit the image: {user_text}. "
        "Keep the same person, face, pose, and background. "
        "Only apply the requested change."
    )


def _kontext_guidance_scale(fal_config: dict[str, Any], endpoint: str) -> float:
    """CFG por defecto segun tier Kontext (pro=3.5, dev=2.5)."""
    raw = fal_config.get("kontext_guidance_scale")
    if raw is not None:
        try:
            return max(1.0, min(20.0, float(raw)))
        except (TypeError, ValueError):
            pass
    if "flux-kontext/dev" in (endpoint or "").lower():
        return 2.5
    return 3.5


def _build_fal_edit_request_body(
    *,
    endpoint: str,
    image_uri: str,
    edit_prompt: str,
    denoise: float | None,
    fal_config: dict[str, Any],
) -> dict[str, Any]:
    """Arma el body Fal segun familia: Kontext (edicion local) vs legacy img2img."""
    if _is_kontext_edit_endpoint(endpoint):
        body: dict[str, Any] = {
            "image_url": image_uri,
            "prompt": _enrich_kontext_edit_prompt(edit_prompt),
            "num_images": 1,
            "output_format": "jpeg",
            "guidance_scale": _kontext_guidance_scale(fal_config, endpoint),
        }
        if "flux-kontext/dev" in endpoint.lower():
            body["resolution_mode"] = str(
                fal_config.get("kontext_resolution_mode") or "match_input"
            )
        return body
    return {
        "image_url": image_uri,
        "prompt": edit_prompt,
        "strength": _denoise_to_strength(denoise),
        "num_images": 1,
        "output_format": "jpeg",
    }


def _mime_for_image_path(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".png":
        return "image/png"
    if ext in (".jpg", ".jpeg"):
        return "image/jpeg"
    if ext == ".webp":
        return "image/webp"
    return "image/jpeg"


def _local_image_to_data_uri(path: Path) -> str:
    """Codifica imagen local como data URI para image_url de Fal.ai."""
    raw = path.read_bytes()
    mime = _mime_for_image_path(path)
    b64 = base64.b64encode(raw).decode("ascii")
    return f"data:{mime};base64,{b64}"


def _comfy_fallback_available(comfyui_config: Optional[dict]) -> bool:
    """True si ComfyUI local puede usarse como fallback de edicion."""
    cfg = comfyui_config if isinstance(comfyui_config, dict) else {}
    if cfg.get("enabled") is False:
        return False
    from duckclaw.forge.skills.comfyui_bridge import _comfy_base_url

    return bool(_comfy_base_url())


def _persist_fal_artifact(
    *,
    media_bytes: bytes,
    media_url: str,
    prompt: str,
    aspect_ratio: str,
    model_endpoint: str,
    media_type: str,
    request_id: str,
    duckclaw_db: Any,
    ctx: dict[str, str],
    operation: str | None = None,
    source_image_path: str | None = None,
) -> tuple[str, str]:
    from duckclaw.forge.skills.comfyui_bridge import tenant_artifacts_dir
    from duckclaw.forge.skills.visual_state_delta import push_visual_state_delta_sync

    tenant_id = ctx.get("tenant_id") or "default"
    artifact_id = str(uuid.uuid4())
    ext = _guess_ext(media_bytes, media_type)
    out_path = tenant_artifacts_dir(tenant_id) / f"fal_{artifact_id}{ext}"
    out_path.write_bytes(media_bytes)
    file_path = str(out_path.resolve())
    base = _state_delta_base()
    mutation = {
        "id": artifact_id,
        "prompt": prompt,
        "negative_prompt": "",
        "file_path": file_path,
        "aspect_ratio": aspect_ratio,
        "prompt_id_comfy": request_id,
        "operation": operation or f"fal_{media_type}",
        "source_image_path": source_image_path or media_url.split("?")[0],
    }
    if base.get("target_db_path"):
        push_visual_state_delta_sync(
            {**base, "delta_type": "VISUAL_ASSET_UPSERT", "mutation": mutation},
            duckclaw_db=duckclaw_db,
        )
    return file_path, artifact_id


def _finish_response(
    *,
    media_url: str,
    file_path: str,
    latency_sec: float,
    cost_usd: float,
    model_endpoint: str,
    media_type: str,
    media_bytes: bytes,
    message: str,
    artifact_id: str = "",
) -> str:
    resp = MediaGenerationResponse(
        success=True,
        media_url=media_url,
        file_path=file_path,
        latency_sec=round(latency_sec, 3),
        cost_usd=round(cost_usd, 6),
        model_endpoint=model_endpoint,
        media_type=media_type,  # type: ignore[arg-type]
        message=message,
    )
    payload: dict[str, Any] = resp.model_dump()
    payload["ok"] = True
    payload["artifacts"] = [file_path]
    if artifact_id:
        payload["artifact_id"] = artifact_id
    if len(media_bytes) <= _MAX_B64_IN_TOOL_RESPONSE:
        payload["figure_base64"] = base64.b64encode(media_bytes).decode("ascii")
    return json.dumps(payload, ensure_ascii=False)


async def _fal_generate_async(
    *,
    endpoint: str,
    body: dict[str, Any],
    prompt: str,
    aspect_ratio: str,
    media_type: str,
    duration_sec: float,
    token_env: str,
    duckclaw_db: Any,
    persist_operation: str | None = None,
    source_image_path: str | None = None,
    success_message: str | None = None,
) -> str:
    api_key = _fal_key(token_env)
    if not api_key:
        return _error_json(
            "API key Fal no configurada. Define FAL_API_KEY o FAL_KEY en .env del gateway."
        )

    ctx = _tool_context()
    usage_db = _usage_db(duckclaw_db)
    projected = estimate_media_cost_usd(endpoint, media_type=media_type, duration_sec=duration_sec)
    try:
        assert_media_budget_ok(usage_db, ctx["tenant_id"], projected_cost_usd=projected)
    except MediaBudgetExceededError as exc:
        return _error_json(str(exc))

    t0 = time.monotonic()
    try:
        submit = await _fal_submit(endpoint, body, api_key)
        result = await _fal_poll(
            status_url=submit["status_url"],
            response_url=submit["response_url"],
            request_id=submit["request_id"],
            api_key=api_key,
            timeout_sec=_poll_timeout_sec(media_type),
        )
        media_url = _extract_media_url(result, media_type)
        media_bytes = await _download_media_bytes(media_url)
    except (httpx.HTTPError, ValueError, TimeoutError, OSError) as exc:
        _log.warning("fal_generate failed endpoint=%s: %s", endpoint, exc)
        return _error_json(str(exc))

    latency = time.monotonic() - t0
    cost = estimate_media_cost_usd(endpoint, media_type=media_type, duration_sec=duration_sec)
    file_path, artifact_id = _persist_fal_artifact(
        media_bytes=media_bytes,
        media_url=media_url,
        prompt=prompt,
        aspect_ratio=aspect_ratio,
        model_endpoint=endpoint,
        media_type=media_type,
        request_id=submit["request_id"],
        duckclaw_db=duckclaw_db,
        ctx=ctx,
        operation=persist_operation,
        source_image_path=source_image_path,
    )
    try:
        append_media_usage_log(
            usage_db,
            tenant_id=ctx["tenant_id"],
            session_id=ctx.get("chat_id") or "",
            worker_id=ctx.get("worker_id") or "",
            model_endpoint=endpoint,
            media_type=media_type,
            cost_usd=cost,
            latency_sec=latency,
            media_url=media_url,
        )
    except Exception:
        _log.debug("append_media_usage_log failed", exc_info=True)

    return _finish_response(
        media_url=media_url,
        file_path=file_path,
        latency_sec=latency,
        cost_usd=cost,
        model_endpoint=endpoint,
        media_type=media_type,
        media_bytes=media_bytes,
        message=success_message or "Media generada via Fal.ai y registrada.",
        artifact_id=artifact_id,
    )


@log_tool_execution_sync(name="generate_flux_image")
def _generate_flux_image_impl(
    prompt: str,
    aspect_ratio: str = "16:9",
    model_endpoint: str = DEFAULT_FLUX_DEV_ENDPOINT,
    *,
    fal_config: Optional[dict] = None,
    duckclaw_db: Any = None,
) -> str:
    pos = (prompt or "").strip()
    if not pos:
        return _error_json("El parametro prompt no puede estar vacio.")
    cfg = fal_config if isinstance(fal_config, dict) else {}
    endpoint = str(cfg.get("default_image_endpoint") or model_endpoint or DEFAULT_FLUX_DEV_ENDPOINT).strip()
    token_env = str(cfg.get("token_env") or "FAL_KEY")
    body = {
        "prompt": pos,
        "image_size": _aspect_to_image_size(aspect_ratio),
        "num_images": 1,
    }
    return _run_async_from_sync(
        _fal_generate_async(
            endpoint=endpoint,
            body=body,
            prompt=pos,
            aspect_ratio=aspect_ratio,
            media_type="image",
            duration_sec=1.0,
            token_env=token_env,
            duckclaw_db=duckclaw_db,
        )
    )


@log_tool_execution_sync(name="generate_kling_video")
def _generate_kling_video_impl(
    prompt: str,
    aspect_ratio: str = "16:9",
    duration_sec: float = 5.0,
    model_endpoint: str = DEFAULT_KLING_VIDEO_ENDPOINT,
    *,
    fal_config: Optional[dict] = None,
    duckclaw_db: Any = None,
) -> str:
    pos = (prompt or "").strip()
    if not pos:
        return _error_json("El parametro prompt no puede estar vacio.")
    cfg = fal_config if isinstance(fal_config, dict) else {}
    endpoint = str(cfg.get("default_video_endpoint") or model_endpoint or DEFAULT_KLING_VIDEO_ENDPOINT).strip()
    token_env = str(cfg.get("token_env") or "FAL_KEY")
    ar = (aspect_ratio or "16:9").strip()
    ratio = "9:16" if ar == "9:16" else ("1:1" if ar == "1:1" else "16:9")
    body = {
        "prompt": pos,
        "aspect_ratio": ratio,
        "duration": str(int(max(1, min(30, duration_sec)))),
    }
    return _run_async_from_sync(
        _fal_generate_async(
            endpoint=endpoint,
            body=body,
            prompt=pos,
            aspect_ratio=aspect_ratio,
            media_type="video",
            duration_sec=float(duration_sec),
            token_env=token_env,
            duckclaw_db=duckclaw_db,
        )
    )


@log_tool_execution_sync(name="edit_visual_asset")
def _fal_edit_visual_asset_impl(
    source_image_path: str,
    edit_prompt: str,
    negative_prompt: str = "blurry, distorted, low quality, deformed face",
    denoise: float | None = None,
    *,
    fal_config: Optional[dict] = None,
    duckclaw_db: Any = None,
) -> str:
    """Edicion via Fal.ai: FLUX Kontext [pro] por defecto; legacy img2img si el manifest lo indica."""
    del negative_prompt  # Kontext y Flux img2img Fal no usan negative_prompt en estos endpoints
    cfg = fal_config if isinstance(fal_config, dict) else {}
    edit_text = (edit_prompt or "").strip()
    if not edit_text:
        return _error_json("edit_prompt no puede estar vacio.")

    base = _state_delta_base()
    tenant_id = base["tenant_id"]
    from duckclaw.forge.skills.comfyui_bridge import validate_source_image_path

    try:
        src = validate_source_image_path(source_image_path, tenant_id)
    except ValueError as e:
        return _error_json(str(e))

    endpoint = str(
        cfg.get("default_image_edit_endpoint") or DEFAULT_FLUX_KONTEXT_PRO_ENDPOINT
    ).strip()
    token_env = str(cfg.get("token_env") or "FAL_KEY")
    try:
        image_uri = _local_image_to_data_uri(src)
    except OSError as exc:
        return _error_json(f"No se pudo leer imagen fuente: {exc}")

    body = _build_fal_edit_request_body(
        endpoint=endpoint,
        image_uri=image_uri,
        edit_prompt=edit_text,
        denoise=denoise,
        fal_config=cfg,
    )
    persist_op = "fal_kontext_edit" if _is_kontext_edit_endpoint(endpoint) else "fal_img2img_edit"
    return _run_async_from_sync(
        _fal_generate_async(
            endpoint=endpoint,
            body=body,
            prompt=edit_text,
            aspect_ratio="source",
            media_type="image",
            duration_sec=1.0,
            token_env=token_env,
            duckclaw_db=duckclaw_db,
            persist_operation=persist_op,
            source_image_path=str(src),
            success_message="Imagen editada via Fal.ai Kontext y registrada.",
        )
    )


def _edit_visual_asset_with_fallback(
    source_image_path: str,
    edit_prompt: str,
    negative_prompt: str = "blurry, distorted, low quality, deformed face",
    denoise: float | None = None,
    *,
    fal_config: Optional[dict] = None,
    comfyui_config: Optional[dict] = None,
    duckclaw_db: Any = None,
) -> str:
    """Fal img2img primero; fallback ComfyUI local si Fal falla."""
    fal_result = _fal_edit_visual_asset_impl(
        source_image_path,
        edit_prompt,
        negative_prompt=negative_prompt,
        denoise=denoise,
        fal_config=fal_config,
        duckclaw_db=duckclaw_db,
    )
    try:
        parsed = json.loads(fal_result)
        if isinstance(parsed, dict) and parsed.get("ok"):
            return fal_result
        fal_error = str(parsed.get("error") or "Fal.ai edit failed")
    except (json.JSONDecodeError, TypeError):
        fal_error = "Fal.ai edit devolvio respuesta invalida"
        parsed = {}

    if not _comfy_fallback_available(comfyui_config):
        return fal_result

    _log.warning("Fal edit failed (%s); falling back to ComfyUI local", fal_error)
    from duckclaw.forge.skills.comfyui_bridge import _edit_visual_asset_impl

    comfy_result = _edit_visual_asset_impl(
        source_image_path,
        edit_prompt,
        negative_prompt=negative_prompt,
        denoise=denoise,
        comfyui_config=comfyui_config,
        duckclaw_db=duckclaw_db,
    )
    try:
        comfy_parsed = json.loads(comfy_result)
        if isinstance(comfy_parsed, dict) and comfy_parsed.get("ok"):
            return comfy_result
    except (json.JSONDecodeError, TypeError):
        pass

    return _error_json(
        f"Fal.ai: {fal_error}. ComfyUI fallback tambien fallo."
    )


@log_tool_execution_sync(name="execute_comfy_workflow")
def _execute_comfy_workflow_impl(
    comfy_workflow_json: dict[str, Any],
    prompt: str = "",
    *,
    fal_config: Optional[dict] = None,
    duckclaw_db: Any = None,
) -> str:
    if not isinstance(comfy_workflow_json, dict) or not comfy_workflow_json:
        return _error_json("comfy_workflow_json debe ser un objeto JSON no vacio.")
    cfg = fal_config if isinstance(fal_config, dict) else {}
    endpoint = str(cfg.get("comfy_endpoint") or "fal-ai/comfy").strip()
    token_env = str(cfg.get("token_env") or "FAL_KEY")
    pos = (prompt or "").strip() or "ComfyUI serverless workflow"
    body = {"workflow": comfy_workflow_json}
    if pos:
        body["prompt"] = pos
    return _run_async_from_sync(
        _fal_generate_async(
            endpoint=endpoint,
            body=body,
            prompt=pos,
            aspect_ratio="16:9",
            media_type="image",
            duration_sec=1.0,
            token_env=token_env,
            duckclaw_db=duckclaw_db,
        )
    )


def register_fal_skill(
    tools_list: list[Any],
    fal_config: Optional[dict] = None,
    *,
    duckclaw_db: Any = None,
    comfyui_config: Optional[dict] = None,
) -> None:
    cfg = fal_config if isinstance(fal_config, dict) else {}
    if cfg.get("enabled") is False:
        return
    token_env = str(cfg.get("token_env") or "FAL_KEY")
    if not _fal_key(token_env):
        _log.warning("Fal.ai disabled: missing %s", token_env)
        return
    try:
        from langchain_core.tools import StructuredTool
    except ImportError:
        return

    def _flux(prompt: str, aspect_ratio: str = "16:9", model_endpoint: str = DEFAULT_FLUX_DEV_ENDPOINT) -> str:
        return _generate_flux_image_impl(
            prompt,
            aspect_ratio=aspect_ratio,
            model_endpoint=model_endpoint,
            fal_config=cfg,
            duckclaw_db=duckclaw_db,
        )

    def _kling(
        prompt: str,
        aspect_ratio: str = "16:9",
        duration_sec: float = 5.0,
        model_endpoint: str = DEFAULT_KLING_VIDEO_ENDPOINT,
    ) -> str:
        return _generate_kling_video_impl(
            prompt,
            aspect_ratio=aspect_ratio,
            duration_sec=duration_sec,
            model_endpoint=model_endpoint,
            fal_config=cfg,
            duckclaw_db=duckclaw_db,
        )

    def _comfy(comfy_workflow_json: dict[str, Any], prompt: str = "") -> str:
        return _execute_comfy_workflow_impl(
            comfy_workflow_json,
            prompt=prompt,
            fal_config=cfg,
            duckclaw_db=duckclaw_db,
        )

    def _edit(
        source_image_path: str,
        edit_prompt: str,
        negative_prompt: str = "blurry, distorted, low quality, deformed face",
        denoise: float = 0.55,
    ) -> str:
        return _edit_visual_asset_with_fallback(
            source_image_path,
            edit_prompt,
            negative_prompt=negative_prompt,
            denoise=denoise,
            fal_config=cfg,
            comfyui_config=comfyui_config,
            duckclaw_db=duckclaw_db,
        )

    tools_list.append(
        StructuredTool.from_function(
            _flux,
            name="generate_flux_image",
            description=(
                "Genera imagen fotorrealista via Fal.ai (Flux Dev/Pro). "
                "Parametros: prompt, aspect_ratio (1:1, 16:9, 9:16), model_endpoint opcional."
            ),
        )
    )
    tools_list.append(
        StructuredTool.from_function(
            _kling,
            name="generate_kling_video",
            description=(
                "Genera video via Fal.ai (Kling/Wan). "
                "Parametros: prompt, aspect_ratio, duration_sec (1-30)."
            ),
        )
    )
    tools_list.append(
        StructuredTool.from_function(
            _comfy,
            name="execute_comfy_workflow",
            description=(
                "Ejecuta un workflow_api.json de ComfyUI en GPUs serverless de Fal.ai. "
                "Parametro comfy_workflow_json obligatorio."
            ),
        )
    )
    tools_list.append(
        StructuredTool.from_function(
            _edit,
            name="edit_visual_asset",
            description=(
                "Edita una foto existente via Fal.ai FLUX Kontext [pro] (fallback ComfyUI local si Fal falla). "
                "Parametros: source_image_path (ruta absoluta en inbound/ o artifacts/ del tenant), "
                "edit_prompt (instrucciones en espanol), negative_prompt (opcional, solo fallback Comfy), "
                "denoise (0.35-0.75, solo legacy img2img o fallback Comfy; ignorado en Kontext). "
                "Usar cuando el mensaje incluya [COMFYUI_EDIT ...] o el usuario pida modificar una foto enviada."
            ),
        )
    )
    _log.info("Fal.ai: registered 4 media tools")
