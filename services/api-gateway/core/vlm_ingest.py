from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
import tempfile
from typing import Any

import httpx

_log = logging.getLogger("duckclaw.gateway.vlm_ingest")

_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
_VLM_OPENAI_FIRST = frozenset({"openai", "cloud", "openai_first"})


def _vlm_gemini_api_key() -> str:
    for raw in (
        os.environ.get("DUCKCLAW_VLM_GEMINI_API_KEY"),
        os.environ.get("GEMINI_API_KEY"),
        os.environ.get("GOOGLE_API_KEY"),
    ):
        k = (raw or "").strip()
        if k:
            return k
    return ""


def _vlm_backend_order() -> list[str]:
    """
    Orden de intentos: por defecto MLX HTTP, luego Gemini (si hay clave), luego OpenAI.
    Con DUCKCLAW_VLM_PRIMARY=openai y OPENAI_API_KEY: openai, mlx, gemini (si clave).
    """
    primary = (os.environ.get("DUCKCLAW_VLM_PRIMARY") or "mlx").strip().lower()
    has_oai = bool((os.environ.get("OPENAI_API_KEY") or "").strip())
    has_gem = bool(_vlm_gemini_api_key())
    if primary in _VLM_OPENAI_FIRST and has_oai:
        seq = ["openai", "mlx"]
    else:
        seq = ["mlx"]
        if has_oai:
            seq.append("openai")
    if has_gem:
        try:
            i = seq.index("mlx") + 1
            seq.insert(i, "gemini")
        except ValueError:
            seq.append("gemini")
    return seq


_VLM_SYSTEM_PROMPT = (
    "Describe los datos financieros, texto o código presentes en esta imagen de forma concisa. "
    "No inventes datos."
)

_mlx_vlm_model_proc: tuple[Any, Any] | None = None


def _suffix_for_mime(mime: str) -> str:
    m = (mime or "image/jpeg").strip().lower()
    if m == "image/png":
        return ".png"
    if m == "image/webp":
        return ".webp"
    return ".jpg"


def _mlx_vlm_local_enabled() -> bool:
    return (os.environ.get("DUCKCLAW_VLM_DISABLE_LOCAL_MLX_VLM") or "").strip().lower() not in (
        "1",
        "true",
        "yes",
    )


def _try_mlx_vlm_local_before_http() -> bool:
    """Evita colgarse en mlx_lm HTTP (texto) con payloads visuales: local primero si mlx_vlm está instalado."""
    if not _mlx_vlm_local_enabled():
        return False
    if (os.environ.get("DUCKCLAW_VLM_HTTP_BEFORE_LOCAL") or "").strip().lower() in ("1", "true", "yes"):
        return False
    try:
        import importlib.util

        return importlib.util.find_spec("mlx_vlm") is not None
    except Exception:
        return False


def _mlx_http_timeout_s() -> float:
    raw = (os.environ.get("DUCKCLAW_VLM_MLX_HTTP_TIMEOUT") or "20").strip()
    try:
        return max(5.0, min(120.0, float(raw)))
    except ValueError:
        return 20.0


def _mlx_vlm_model_id() -> str:
    # Qwen2-VL snapshots en mlx-community a veces no traen image_processor_type compatible
    # con transformers instalado; LLaVA v1.6 Mistral 4bit es estable en mlx_vlm.
    return (
        os.environ.get("DUCKCLAW_VLM_MLX_VLM_MODEL")
        or os.environ.get("MLX_VLM_MODEL")
        or "mlx-community/llava-v1.6-mistral-7b-4bit"
    ).strip()


def _mlx_vlm_processor_repo(weights_id: str) -> str:
    """
    Repositorio HF completo para AutoProcessor + tokenizer.
    Los snapshots mlx-community suelen omitir preprocessor_config válido para AutoProcessor;
    los pesos MLX se cargan desde weights_id y el processor desde aquí.
    """
    explicit = (os.environ.get("DUCKCLAW_VLM_MLX_VLM_PROCESSOR_REPO") or "").strip()
    if explicit:
        return explicit
    w = (weights_id or "").strip().lower()
    if "llava-v1.6-mistral" in w or "llava_v1.6_mistral" in w:
        return "llava-hf/llava-v1.6-mistral-7b-hf"
    if "qwen2-vl" in w:
        if "2b" in w:
            return "Qwen/Qwen2-VL-2B-Instruct"
        return "Qwen/Qwen2-VL-7B-Instruct"
    return weights_id.strip()


def _get_mlx_vlm_loaded() -> tuple[Any, Any]:
    """Cache modelo+processor en el proceso del gateway (primera inferencia descarga/carga)."""
    global _mlx_vlm_model_proc
    if _mlx_vlm_model_proc is not None:
        return _mlx_vlm_model_proc
    try:
        from mlx_vlm.utils import (
            get_model_path,
            load_config,
            load_image_processor,
            load_model,
            load_processor,
        )
    except ImportError as exc:
        raise RuntimeError(
            "mlx_vlm no está instalado (solo macOS: dependencia opcional en pyproject)."
        ) from exc
    mid = _mlx_vlm_model_id()
    proc_repo = _mlx_vlm_processor_repo(mid)
    _log.info(
        "VLM mlx_vlm local: pesos=%s processor_hf=%s (primera vez puede tardar)",
        mid,
        proc_repo,
    )
    model_path = get_model_path(mid)
    model = load_model(model_path, lazy=False)
    eos_token_id = getattr(model.config, "eos_token_id", None)
    image_processor = load_image_processor(model_path)
    processor = load_processor(
        proc_repo, True, eos_token_ids=eos_token_id, trust_remote_code=True
    )
    if image_processor is not None:
        processor.image_processor = image_processor
    _mlx_vlm_model_proc = (model, processor)
    return _mlx_vlm_model_proc


def _mlx_vlm_caption_paths_sync(paths: list[str], prompt: str, *, max_tokens: int) -> str:
    from mlx_vlm import generate

    if not paths:
        raise ValueError("paths vacío")
    model, processor = _get_mlx_vlm_loaded()
    img_arg: str | list[str] = paths[0] if len(paths) == 1 else paths
    res = generate(
        model,
        processor,
        prompt=prompt,
        image=img_arg,
        max_tokens=max_tokens,
        verbose=False,
    )
    return (res.text or "").strip()


async def _try_mlx_vlm_caption_paths(paths: list[str], prompt: str) -> str:
    raw_max = (os.environ.get("DUCKCLAW_VLM_MLX_VLM_MAX_TOKENS") or "512").strip()
    try:
        max_tokens = max(64, min(4096, int(raw_max)))
    except ValueError:
        max_tokens = 512
    return await asyncio.to_thread(_mlx_vlm_caption_paths_sync, paths, prompt, max_tokens=max_tokens)


def _tmp_dir() -> str:
    return (os.environ.get("DUCKCLAW_VLM_TMP_DIR") or "/tmp/duckclaw_vlm").strip() or "/tmp/duckclaw_vlm"


def _max_image_bytes() -> int:
    raw = (os.environ.get("DUCKCLAW_VLM_MAX_IMAGE_BYTES") or "12582912").strip()
    try:
        return max(1_048_576, int(raw))
    except ValueError:
        return 12_582_912


def _secure_wipe_remove(tmp_path: str) -> None:
    if not tmp_path:
        return
    try:
        with open(tmp_path, "r+b") as f:
            size = f.seek(0, os.SEEK_END)
            f.seek(0)
            f.write(b"\x00" * min(size, 1024 * 1024))
    except Exception:
        pass
    try:
        os.remove(tmp_path)
    except Exception:
        pass


async def _telegram_download_file_bytes(bot_token: str, file_id: str) -> bytes:
    api = f"https://api.telegram.org/bot{bot_token}"
    async with httpx.AsyncClient(timeout=httpx.Timeout(60.0)) as client:
        r = await client.get(f"{api}/getFile", params={"file_id": file_id})
        r.raise_for_status()
        data = r.json() if r.content else {}
        if not data.get("ok") or not isinstance(data.get("result"), dict):
            raise RuntimeError("Telegram getFile failed")
        file_path = str(data["result"].get("file_path") or "").strip()
        if not file_path:
            raise RuntimeError("Telegram file_path vacío")
        rf = await client.get(f"https://api.telegram.org/file/bot{bot_token}/{file_path}")
        rf.raise_for_status()
        data = bytes(rf.content or b"")
    limit = _max_image_bytes()
    if len(data) > limit:
        raise RuntimeError(f"imagen demasiado grande ({len(data)} > {limit})")
    return data


async def _call_openai_vision(
    *,
    base_url: str,
    api_key: str,
    model: str,
    mime_type: str,
    image_bytes: bytes,
    user_caption: str,
    http_timeout_s: float = 120.0,
) -> str:
    img_b64 = base64.b64encode(image_bytes).decode("ascii")
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _VLM_SYSTEM_PROMPT},
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": user_caption or "Analiza esta imagen."},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{img_b64}"}},
                ],
            },
        ],
        "temperature": 0.0,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    endpoint = base_url.rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=httpx.Timeout(http_timeout_s)) as client:
        r = await client.post(endpoint, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json() if r.content else {}
    try:
        return str(data["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Respuesta VLM inválida: {exc}") from exc


async def _call_openai_vision_multi(
    *,
    base_url: str,
    api_key: str,
    model: str,
    images: list[tuple[str, bytes]],
    user_caption: str,
    http_timeout_s: float = 120.0,
) -> str:
    parts: list[dict[str, Any]] = [{"type": "text", "text": user_caption or "Analiza estas imágenes (máx. 3)."}]
    for mime_type, image_bytes in images:
        mt = (mime_type or "image/jpeg").strip().lower()
        img_b64 = base64.b64encode(image_bytes).decode("ascii")
        parts.append({"type": "image_url", "image_url": {"url": f"data:{mt};base64,{img_b64}"}})
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": _VLM_SYSTEM_PROMPT},
            {"role": "user", "content": parts},
        ],
        "temperature": 0.0,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    endpoint = base_url.rstrip("/") + "/chat/completions"
    async with httpx.AsyncClient(timeout=httpx.Timeout(http_timeout_s)) as client:
        r = await client.post(endpoint, json=payload, headers=headers)
        r.raise_for_status()
        data = r.json() if r.content else {}
    try:
        return str(data["choices"][0]["message"]["content"] or "").strip()
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Respuesta VLM inválida: {exc}") from exc


def _openai_cloud_http_timeout_s() -> float:
    raw = (os.environ.get("DUCKCLAW_VLM_OPENAI_HTTP_TIMEOUT") or "90").strip()
    try:
        return max(15.0, min(180.0, float(raw)))
    except ValueError:
        return 90.0


def _gemini_model() -> str:
    return (os.environ.get("DUCKCLAW_VLM_GEMINI_MODEL") or "gemini-2.5-flash").strip()


def _gemini_http_timeout_s() -> float:
    raw = (os.environ.get("DUCKCLAW_VLM_GEMINI_HTTP_TIMEOUT") or "90").strip()
    try:
        return max(15.0, min(180.0, float(raw)))
    except ValueError:
        return 90.0


def _gemini_text_from_response(data: dict[str, Any]) -> str:
    cands = data.get("candidates")
    if not isinstance(cands, list) or not cands:
        err = data.get("error")
        if isinstance(err, dict):
            msg = err.get("message") or err.get("status") or str(err)
            raise RuntimeError(f"Gemini API error: {msg}")
        raise RuntimeError("Gemini: sin candidates (¿bloqueo de seguridad o respuesta vacía?)")
    first = cands[0]
    content = first.get("content") if isinstance(first, dict) else None
    parts = content.get("parts") if isinstance(content, dict) else None
    if not isinstance(parts, list):
        raise RuntimeError("Gemini: content.parts inválido")
    texts: list[str] = []
    for p in parts:
        if isinstance(p, dict) and p.get("text"):
            texts.append(str(p["text"]))
    out = "".join(texts).strip()
    if not out:
        raise RuntimeError("Gemini: texto vacío en parts")
    return out


async def _call_gemini_vision(
    *,
    api_key: str,
    model: str,
    mime_type: str,
    image_bytes: bytes,
    user_caption: str,
    http_timeout_s: float = 90.0,
) -> str:
    img_b64 = base64.b64encode(image_bytes).decode("ascii")
    mt = (mime_type or "image/jpeg").strip().lower()
    payload: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": _VLM_SYSTEM_PROMPT}]},
        "contents": [
            {
                "role": "user",
                "parts": [
                    {"text": user_caption or "Analiza esta imagen."},
                    {"inline_data": {"mime_type": mt, "data": img_b64}},
                ],
            }
        ],
        "generationConfig": {"temperature": 0.0},
    }
    model_id = model.strip()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + model_id
        + ":generateContent"
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(http_timeout_s)) as client:
        r = await client.post(url, params={"key": api_key}, json=payload)
        r.raise_for_status()
        data = r.json() if r.content else {}
    return _gemini_text_from_response(data if isinstance(data, dict) else {})


async def _call_gemini_vision_multi(
    *,
    api_key: str,
    model: str,
    images: list[tuple[str, bytes]],
    user_caption: str,
    http_timeout_s: float = 90.0,
) -> str:
    user_parts: list[dict[str, Any]] = [
        {"text": user_caption or "Analiza estas imágenes (máx. 3)."}
    ]
    for mime_type, image_bytes in images:
        mt = (mime_type or "image/jpeg").strip().lower()
        img_b64 = base64.b64encode(image_bytes).decode("ascii")
        user_parts.append({"inline_data": {"mime_type": mt, "data": img_b64}})
    payload: dict[str, Any] = {
        "systemInstruction": {"parts": [{"text": _VLM_SYSTEM_PROMPT}]},
        "contents": [{"role": "user", "parts": user_parts}],
        "generationConfig": {"temperature": 0.0},
    }
    model_id = model.strip()
    url = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        + model_id
        + ":generateContent"
    )
    async with httpx.AsyncClient(timeout=httpx.Timeout(http_timeout_s)) as client:
        r = await client.post(url, params={"key": api_key}, json=payload)
        r.raise_for_status()
        data = r.json() if r.content else {}
    return _gemini_text_from_response(data if isinstance(data, dict) else {})


async def process_visual_payload(
    *,
    bot_token: str,
    file_id: str,
    caption: str,
    mime_type: str,
    media_group_id: str = "",
) -> dict[str, Any]:
    """
    Descarga media de Telegram, ejecuta VLM (MLX, Gemini, OpenAI según env) y purga archivo temporal.
    """
    mt = (mime_type or "").strip().lower()
    if mt not in _ALLOWED_MIME:
        raise ValueError(f"MIME no permitido: {mt}")
    if not (file_id or "").strip():
        raise ValueError("file_id vacío")

    image_bytes = await _telegram_download_file_bytes(bot_token, file_id)
    if not image_bytes:
        raise RuntimeError("imagen vacía")
    image_hash = hashlib.sha256(image_bytes).hexdigest()

    os.makedirs(_tmp_dir(), exist_ok=True)
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            dir=_tmp_dir(), suffix=_suffix_for_mime(mt), delete=False
        ) as f:
            f.write(image_bytes)
            tmp_path = f.name

        mlx_base = (os.environ.get("DUCKCLAW_VLM_MLX_BASE_URL") or "http://127.0.0.1:8081/v1").strip()
        mlx_model = (
            os.environ.get("DUCKCLAW_VLM_MLX_MODEL")
            or os.environ.get("MLX_VISION_MODEL")
            or os.environ.get("MLX_MODEL_ID")
            or "Qwen2-VL-2B-Instruct-4bit"
        ).strip()
        fb_model = (os.environ.get("DUCKCLAW_VLM_FALLBACK_MODEL") or "gpt-4o-mini").strip()
        prompt_use = (caption or "").strip() or _VLM_SYSTEM_PROMPT
        if _try_mlx_vlm_local_before_http():
            try:
                summary_l = await _try_mlx_vlm_caption_paths([tmp_path], prompt_use)
                if (summary_l or "").strip():
                    return {
                        "image_hash": image_hash,
                        "vlm_summary": summary_l[:2000],
                        "confidence_score": 0.82,
                        "media_group_id": (media_group_id or "").strip(),
                    }
            except Exception as exc:  # noqa: BLE001
                _log.warning("VLM mlx_vlm local-first falló, se intentará HTTP: %s", exc)
        mlx_to = _mlx_http_timeout_s()
        cloud_to = _openai_cloud_http_timeout_s()
        gemini_to = _gemini_http_timeout_s()
        summary = ""
        confidence = 0.85
        last_exc: BaseException | None = None
        for kind in _vlm_backend_order():
            try:
                if kind == "mlx":
                    summary = await _call_openai_vision(
                        base_url=mlx_base,
                        api_key=(os.environ.get("DUCKCLAW_VLM_MLX_API_KEY") or "").strip(),
                        model=mlx_model,
                        mime_type=mt,
                        image_bytes=image_bytes,
                        user_caption=caption,
                        http_timeout_s=mlx_to,
                    )
                    confidence = 0.85
                elif kind == "gemini":
                    summary = await _call_gemini_vision(
                        api_key=_vlm_gemini_api_key(),
                        model=_gemini_model(),
                        mime_type=mt,
                        image_bytes=image_bytes,
                        user_caption=caption,
                        http_timeout_s=gemini_to,
                    )
                    confidence = 0.74
                else:
                    fb_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
                    summary = await _call_openai_vision(
                        base_url="https://api.openai.com/v1",
                        api_key=fb_key,
                        model=fb_model,
                        mime_type=mt,
                        image_bytes=image_bytes,
                        user_caption=caption,
                        http_timeout_s=cloud_to,
                    )
                    confidence = 0.75
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if kind == "mlx":
                    _log.warning("VLM vía MLX falló (base_url=%s): %s", mlx_base, exc)
                elif kind == "gemini":
                    _log.warning("VLM vía Gemini falló: %s", exc)
                else:
                    _log.warning("VLM vía OpenAI cloud falló: %s", exc)
                continue
        else:
            summary_fb = ""
            if _mlx_vlm_local_enabled() and tmp_path:
                try:
                    summary_fb = await _try_mlx_vlm_caption_paths([tmp_path], prompt_use)
                except Exception as loc_exc:  # noqa: BLE001
                    _log.warning("VLM mlx_vlm local (1 imagen) falló: %s", loc_exc)
            if summary_fb:
                summary = summary_fb
                confidence = 0.82
            elif last_exc is not None:
                raise last_exc
            else:
                raise RuntimeError("VLM: ningún backend produjo resumen")
        return {
            "image_hash": image_hash,
            "vlm_summary": summary[:2000],
            "confidence_score": float(confidence),
            "media_group_id": (media_group_id or "").strip(),
        }
    finally:
        _secure_wipe_remove(tmp_path)


async def process_visual_album_batch(
    *,
    bot_token: str,
    items: list[tuple[str, str]],
    caption: str,
    media_group_id: str = "",
) -> dict[str, Any]:
    """
    Hasta 3 imágenes por request (Telegram álbum); un solo VLM con varias image_url.
    """
    if not items:
        raise ValueError("items vacío")
    if len(items) > 3:
        items = items[:3]
    per_hashes: list[str] = []
    dl: list[tuple[str, bytes]] = []
    tmp_paths: list[str] = []
    os.makedirs(_tmp_dir(), exist_ok=True)
    try:
        for file_id, mime_type in items:
            mt = (mime_type or "").strip().lower()
            if mt not in _ALLOWED_MIME:
                raise ValueError(f"MIME no permitido: {mt}")
            if not (file_id or "").strip():
                raise ValueError("file_id vacío")
            image_bytes = await _telegram_download_file_bytes(bot_token, file_id)
            if not image_bytes:
                raise RuntimeError("imagen vacía")
            per_hashes.append(hashlib.sha256(image_bytes).hexdigest())
            dl.append((mt, image_bytes))
            with tempfile.NamedTemporaryFile(
                dir=_tmp_dir(), suffix=_suffix_for_mime(mt), delete=False
            ) as f:
                f.write(image_bytes)
                tmp_paths.append(f.name)

        composite = hashlib.sha256("|".join(sorted(per_hashes)).encode("utf-8")).hexdigest()
        mlx_base = (os.environ.get("DUCKCLAW_VLM_MLX_BASE_URL") or "http://127.0.0.1:8081/v1").strip()
        mlx_model = (
            os.environ.get("DUCKCLAW_VLM_MLX_MODEL")
            or os.environ.get("MLX_VISION_MODEL")
            or os.environ.get("MLX_MODEL_ID")
            or "Qwen2-VL-2B-Instruct-4bit"
        ).strip()
        fb_model = (os.environ.get("DUCKCLAW_VLM_FALLBACK_MODEL") or "gpt-4o-mini").strip()
        caption_use = (caption or "").strip() or "Analiza estas imágenes relacionadas."
        if _try_mlx_vlm_local_before_http() and tmp_paths:
            try:
                summary_l = await _try_mlx_vlm_caption_paths(tmp_paths, caption_use)
                if (summary_l or "").strip():
                    return {
                        "image_hash": composite,
                        "vlm_summary": summary_l[:4000],
                        "confidence_score": 0.82,
                        "media_group_id": (media_group_id or "").strip(),
                        "image_count": len(items),
                    }
            except Exception as exc:  # noqa: BLE001
                _log.warning("VLM mlx_vlm local-first (álbum) falló, se intentará HTTP: %s", exc)
        mlx_multi_to = max(_mlx_http_timeout_s(), 45.0)
        cloud_multi_to = max(_openai_cloud_http_timeout_s(), 90.0)
        gemini_multi_to = max(_gemini_http_timeout_s(), 90.0)
        summary = ""
        confidence = 0.85
        last_exc: BaseException | None = None
        for kind in _vlm_backend_order():
            try:
                if kind == "mlx":
                    summary = await _call_openai_vision_multi(
                        base_url=mlx_base,
                        api_key=(os.environ.get("DUCKCLAW_VLM_MLX_API_KEY") or "").strip(),
                        model=mlx_model,
                        images=dl,
                        user_caption=caption_use,
                        http_timeout_s=mlx_multi_to,
                    )
                    confidence = 0.85
                elif kind == "gemini":
                    summary = await _call_gemini_vision_multi(
                        api_key=_vlm_gemini_api_key(),
                        model=_gemini_model(),
                        images=dl,
                        user_caption=caption_use,
                        http_timeout_s=gemini_multi_to,
                    )
                    confidence = 0.74
                else:
                    fb_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
                    summary = await _call_openai_vision_multi(
                        base_url="https://api.openai.com/v1",
                        api_key=fb_key,
                        model=fb_model,
                        images=dl,
                        user_caption=caption_use,
                        http_timeout_s=cloud_multi_to,
                    )
                    confidence = 0.75
                break
            except Exception as exc:  # noqa: BLE001
                last_exc = exc
                if kind == "mlx":
                    _log.warning("VLM (álbum) vía MLX falló (base_url=%s): %s", mlx_base, exc)
                elif kind == "gemini":
                    _log.warning("VLM (álbum) vía Gemini falló: %s", exc)
                else:
                    _log.warning("VLM (álbum) vía OpenAI cloud falló: %s", exc)
                continue
        else:
            summary_fb = ""
            if _mlx_vlm_local_enabled() and tmp_paths:
                try:
                    summary_fb = await _try_mlx_vlm_caption_paths(tmp_paths, caption_use)
                except Exception as loc_exc:  # noqa: BLE001
                    _log.warning("VLM mlx_vlm local (álbum) falló: %s", loc_exc)
            if summary_fb:
                summary = summary_fb
                confidence = 0.82
            elif last_exc is not None:
                raise last_exc
            else:
                raise RuntimeError("VLM: ningún backend produjo resumen")
        return {
            "image_hash": composite,
            "vlm_summary": summary[:4000],
            "confidence_score": float(confidence),
            "media_group_id": (media_group_id or "").strip(),
            "image_count": len(items),
        }
    finally:
        for p in tmp_paths:
            _secure_wipe_remove(p)


async def push_vlm_state_delta_redis(
    redis_client: Any,
    *,
    tenant_id: str,
    image_hash: str,
    vlm_summary: str,
    confidence_score: float,
) -> None:
    """LPUSH JSON al estilo StateDelta de specs/features/VLM INTEGRATION.md (cola dedicada, no duckdb_write_queue)."""
    if redis_client is None:
        return
    key = (os.environ.get("DUCKCLAW_VLM_STATE_DELTA_QUEUE") or "duckclaw:state_delta:vlm").strip()
    payload = {
        "tenant_id": str(tenant_id or "").strip() or "default",
        "delta_type": "VLM_CONTEXT_EXTRACTED",
        "mutation": {
            "image_hash": image_hash,
            "vlm_summary": vlm_summary[:4000],
            "confidence_score": float(confidence_score),
        },
    }
    try:
        await redis_client.lpush(key, json.dumps(payload, ensure_ascii=False))
    except Exception as exc:  # noqa: BLE001
        _log.warning("VLM state_delta redis omitido: %s", exc)
