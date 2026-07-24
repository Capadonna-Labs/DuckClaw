from __future__ import annotations

import asyncio
import base64
import gc
import hashlib
import json
import logging
import os
import re
import tempfile
from typing import Any
from urllib.parse import urlparse

import httpx

_log = logging.getLogger("duckclaw.gateway.vlm_ingest")

_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}
_VLM_OPENAI_FIRST = frozenset({"openai", "cloud", "openai_first"})


def _vlm_allow_openai_vision() -> bool:
    """
    OpenAI como backend VLM solo si se opta explícitamente (p. ej. ``DUCKCLAW_VLM_ALLOW_OPENAI_VISION=1``).
    Flujo por defecto en DuckClaw: ``mlx_vlm`` / MLX HTTP → Gemini; sin API OpenAI de visión.
    """
    return (os.environ.get("DUCKCLAW_VLM_ALLOW_OPENAI_VISION") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


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
    Orden de intentos: MLX (HTTP / mismo orden que env), luego Gemini si hay clave.
    OpenAI visión solo con ``DUCKCLAW_VLM_ALLOW_OPENAI_VISION=1`` y ``OPENAI_API_KEY``.
    Con DUCKCLAW_VLM_PRIMARY=openai y clave OpenAI y allow: openai, mlx, gemini (si clave).
    """
    primary = (os.environ.get("DUCKCLAW_VLM_PRIMARY") or "mlx").strip().lower()
    has_oai = bool((os.environ.get("OPENAI_API_KEY") or "").strip()) and _vlm_allow_openai_vision()
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
    "No inventes datos. "
    "Las fechas deben transcribirse exactamente como aparecen en la imagen (día/mes/año legibles). "
    "No completes el año ni el día desde memoria o patrones de entrenamiento; si la fecha no es "
    "claramente visible, di «fecha no legible en la imagen» y no asumas un año. "
    "Salida: solo el resumen visible al usuario en español, sin pasos de razonamiento ni inglés."
)

def _sanitize_vlm_visible_text(raw: str) -> str:
    """
    Quita CoT / marcadores de canal que Gemma multimodal puede filtrar al usuario vía MLX-Vision.
    Evidencia (gateway2026-04-15): ``Contexto visual adjunto: <|channel>thought … <channel|>El texto…``.
    """
    from duckclaw.integrations.llm_providers import strip_gemma_mlx_channel_leak

    original = (raw or "").strip()
    if not original:
        return original
    return strip_gemma_mlx_channel_leak(original)

_mlx_vlm_model_proc: tuple[Any, Any] | None = None


def _suffix_for_mime(mime: str) -> str:
    m = (mime or "image/jpeg").strip().lower()
    if m == "image/png":
        return ".png"
    if m == "image/webp":
        return ".webp"
    return ".jpg"


def _env_flag_disables_truthy(raw: str | None) -> bool:
    return (raw or "").strip().lower() in ("1", "true", "yes", "on")


def _mlx_vlm_local_enabled() -> bool:
    """Local mlx_vlm desactivado con cualquiera de los alias (p. ej. ``VLM_MLX_DISABLE_LOCAL=1``)."""
    if _env_flag_disables_truthy(os.environ.get("DUCKCLAW_VLM_DISABLE_LOCAL_MLX_VLM")):
        return False
    if _env_flag_disables_truthy(os.environ.get("VLM_MLX_DISABLE_LOCAL")):
        return False
    if _env_flag_disables_truthy(os.environ.get("DUCKCLAW_VLM_MLX_DISABLE_LOCAL")):
        return False
    return True


_mlx_vlm_missing_logged = False


def _vlm_gc_before_inference_enabled() -> bool:
    """``DUCKCLAW_VLM_GC_BEFORE_INFERENCE=0`` desactiva ``gc.collect`` previo (solo gateway / RAM Python)."""
    return (os.environ.get("DUCKCLAW_VLM_GC_BEFORE_INFERENCE") or "1").strip().lower() not in (
        "0",
        "false",
        "no",
        "off",
    )


def _vlm_memory_mitigation() -> None:
    """
    Libera presión de heap Python antes/después de VLM (no libera VRAM del proceso MLX-Vision).
    En Mac mini con memoria unificada, menos RAM en el gateway reduce contención con Metal.
    """
    if not _vlm_gc_before_inference_enabled():
        return
    gc.collect(0)
    gc.collect()


async def vlm_post_inference_cooldown() -> None:
    """
    Pausa opcional tras VLM antes de encolar el turno grande al worker (MLX texto).
    ``DUCKCLAW_VLM_POST_INFERENCE_COOLDOWN_MS`` (0–30000): en Mac con RAM unificada puede
    reducir picos cuando MLX-Vision y MLX-Inference compiten por Metal.
    """
    raw = (os.environ.get("DUCKCLAW_VLM_POST_INFERENCE_COOLDOWN_MS") or "0").strip()
    try:
        ms = max(0, min(30_000, int(raw)))
    except ValueError:
        ms = 0
    if ms <= 0:
        return
    await asyncio.sleep(ms / 1000.0)


def _try_mlx_vlm_local_before_http() -> bool:
    """Evita colgarse en mlx_lm HTTP (texto) con payloads visuales: local primero si mlx_vlm está instalado."""
    global _mlx_vlm_missing_logged
    if not _mlx_vlm_local_enabled():
        return False
    http_first = (os.environ.get("DUCKCLAW_VLM_HTTP_BEFORE_LOCAL") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    dedicated_http = _dedicated_loopback_vlm_http_configured()
    if http_first or dedicated_http:
        return False
    try:
        import importlib.util

        mlx_vlm_found = importlib.util.find_spec("mlx_vlm") is not None
        if not mlx_vlm_found:
            if not _mlx_vlm_missing_logged:
                _mlx_vlm_missing_logged = True
                _log.info(
                    "VLM: mlx_vlm no importable en este proceso; se usará MLX HTTP. "
                    "Para Gemma multimodal en local, instala mlx-vlm en el venv del gateway."
                )
            return False
        return True
    except Exception:
        return False


def _mlx_http_timeout_s() -> float:
    # Visión en MLX local suele superar 20s (carga KV / primer token); ReadTimeout si es corto.
    raw = (os.environ.get("DUCKCLAW_VLM_MLX_HTTP_TIMEOUT") or "60").strip()
    try:
        return max(5.0, min(120.0, float(raw)))
    except ValueError:
        return 60.0


def _is_loopback_openai_base(base_url: str) -> bool:
    u = (base_url or "").strip().lower()
    if not u:
        return False
    return "127.0.0.1" in u or "localhost" in u or u.startswith("http://[::1]")


_MLX_LOOPBACK_CONNECT_ATTEMPTS = 3
_MLX_LOOPBACK_RECONNECT_BASE_S = 0.35


async def _post_openai_chat_completions_resilient(
    *,
    client: httpx.AsyncClient,
    endpoint: str,
    payload: dict[str, Any],
    headers: dict[str, str],
    base_url: str,
) -> httpx.Response:
    """
    Reintenta solo ``httpx.ConnectError`` hacia bases loopback (p. ej. Uvicorn + reload
    de MLX-Inference: ventanas sin listener en :8080).
    """
    for attempt in range(_MLX_LOOPBACK_CONNECT_ATTEMPTS):
        try:
            return await client.post(endpoint, json=payload, headers=headers)
        except httpx.ConnectError:
            if not _is_loopback_openai_base(base_url) or attempt >= _MLX_LOOPBACK_CONNECT_ATTEMPTS - 1:
                raise
            await asyncio.sleep(_MLX_LOOPBACK_RECONNECT_BASE_S * (2**attempt))


def _httpx_trust_env_for_openai_base(base_url: str) -> bool:
    """
    httpx usa trust_env=True por defecto; HTTP_PROXY/ALL_PROXY pueden desviar **localhost**
    y provocar ConnectError aunque MLX-Inference escuche en :8080.
    Para bases loopback, desactivar confianza en env de proxy.
    """
    u = (base_url or "").strip().lower()
    if not u:
        return True
    if "127.0.0.1" in u or "localhost" in u or u.startswith("http://[::1]"):
        return False
    return True


def _text_mlx_stack_port() -> int:
    """
    Puerto donde escucha ``mlx_lm server`` (solo texto).

    Debe ser **solo** ``MLX_PORT``: si ``VLM_MLX_PORT`` apunta a otro host para visión HTTP,
    mezclarlo aquí hacía que ``_skip_mlx_openai_vision_same_port_as_text_mlx`` comparara el
    puerto VLM consigo mismo y omitiera MLX HTTP aunque texto y visión fueran distintos.
    """
    raw = (os.environ.get("MLX_PORT") or "8080").strip()
    try:
        return max(1, min(65535, int(raw)))
    except ValueError:
        return 8080


def _dedicated_loopback_vlm_http_configured() -> bool:
    """
    True si la visión OpenAI-compat está pensada para un **puerto loopback distinto** al de
    ``mlx_lm`` (``MLX_PORT``), p. ej. MLX-Vision en :8081 e inferencia texto en :8080.

    En ese caso **no** cargar ``mlx_vlm`` dentro del proceso del gateway: duplica pesos
    multimodales en Metal y suele terminar en ``kIOGPUCommandBufferCallbackErrorOutOfMemory``
    (evidencia en logs PM2 al usar ``/context --add`` + foto).
    """
    text_port = _text_mlx_stack_port()
    raw_base = ""
    for key in ("DUCKCLAW_VLM_MLX_BASE_URL", "VLM_MLX_BASE_URL"):
        v = (os.environ.get(key) or "").strip().rstrip("/")
        if v:
            raw_base = v
            break
    if raw_base:
        if not _is_loopback_openai_base(raw_base):
            return False
        try:
            u = urlparse(raw_base)
            vlm_port = u.port
            if vlm_port is None:
                vlm_port = 80 if (u.scheme or "http").lower() == "http" else 443
        except Exception:
            return False
        return vlm_port != text_port
    raw_vp = (os.environ.get("VLM_MLX_PORT") or "").strip()
    if not raw_vp:
        return False
    try:
        vlm_port = max(1, min(65535, int(raw_vp)))
    except ValueError:
        return False
    if vlm_port == text_port:
        return False
    return _is_loopback_openai_base(f"http://127.0.0.1:{vlm_port}/v1")


def _skip_mlx_openai_vision_same_port_as_text_mlx(mlx_base: str) -> bool:
    """
    ``mlx_lm server`` en ``MLX_PORT`` **no** implementa mensajes user con ``image_url`` en
    ``/v1/chat/completions`` → HTTP **404** mientras el texto en el mismo puerto responde **200**
    (evidencia en logs PM2). No enviar visión OpenAI al mismo puerto loopback que la pila de
    texto, aunque ``VLM_MLX_BASE_URL`` repita esa URL en ``.env``.

    Forzar el intento: ``DUCKCLAW_VLM_MLX_HTTP_ALLOW_DEFAULT_LOOPBACK=1``.
    Visión Gemma local: ``pip install mlx-vlm`` en el venv del gateway y quitar
    ``VLM_MLX_DISABLE_LOCAL`` / alias; o servir visión en **otro** puerto y fijar
    ``VLM_MLX_BASE_URL`` / ``VLM_MLX_PORT``.
    """
    if (os.environ.get("DUCKCLAW_VLM_MLX_HTTP_ALLOW_DEFAULT_LOOPBACK") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return False
    if not _is_loopback_openai_base(mlx_base):
        return False
    try:
        u = urlparse(mlx_base)
        vlm_port = u.port
        if vlm_port is None:
            vlm_port = 80 if (u.scheme or "http").lower() == "http" else 443
    except Exception:
        return False
    return vlm_port == _text_mlx_stack_port()


def _mlx_http_base_url() -> str:
    """
    Servidor OpenAI-compatible para VLM (``/v1/chat/completions``).
    Prioridad: ``DUCKCLAW_VLM_MLX_BASE_URL`` → ``VLM_MLX_BASE_URL`` →
    ``http://127.0.0.1:{VLM_MLX_PORT|MLX_PORT|8081}/v1``.

    Si esa URL usa el **mismo puerto** que ``MLX_PORT`` en loopback, es casi siempre
    ``mlx_lm`` solo texto — ver ``_skip_mlx_openai_vision_same_port_as_text_mlx``.
    """
    for key in ("DUCKCLAW_VLM_MLX_BASE_URL", "VLM_MLX_BASE_URL"):
        v = (os.environ.get(key) or "").strip().rstrip("/")
        if v:
            return v
    raw_port = (os.environ.get("VLM_MLX_PORT") or os.environ.get("MLX_PORT") or "8081").strip()
    try:
        port = max(1, min(65535, int(raw_port)))
    except ValueError:
        port = 8081
    return f"http://127.0.0.1:{port}/v1"


def _mlx_http_vision_model() -> str:
    """
    Modelo para peticiones VLM al servidor OpenAI-compat (mlx_vlm HTTP).

    No usar ``MLX_MODEL_ID`` directamente: en PM2 suele apuntar al LLM de texto (p. ej. Slayer/Llama),
    lo que fuerza un swap a un checkpoint incompatible con ``mlx_vlm`` (error ``mlx_vlm.models.llama``).
    Misma resolución que VLM local: ``DUCKCLAW_VLM_MLX_MODEL`` / ``MLX_VISION_MODEL`` → ``_mlx_vlm_model_id()``.
    """
    for key in ("DUCKCLAW_VLM_MLX_MODEL", "MLX_VISION_MODEL"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    return _mlx_vlm_model_id()


def vlm_exception_for_log(exc: BaseException) -> str:
    """Log de errores HTTP sin query string (evita filtrar ``key=`` de Gemini u otros)."""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        try:
            u = exc.request.url
            return (
                f"HTTPStatusError {exc.response.status_code} "
                f"host={u.host} path={u.path}"
            )
        except Exception:
            pass
    if isinstance(exc, httpx.RequestError):
        try:
            req = getattr(exc, "request", None)
            if req is not None:
                u = req.url
                detail = (str(exc) or "").strip() or "(sin mensaje del cliente HTTP)"
                return f"{type(exc).__name__} host={u.host} path={u.path} {detail}"
        except Exception:
            pass
    msg = (str(exc) or "").strip()
    if msg:
        return msg[:800]
    return f"{type(exc).__name__}(sin mensaje textual)"


class VlmIngestAllFailed(Exception):
    """Ningún backend VLM produjo resumen; ``gemini_503`` si Gemini respondió 503 en la cadena."""

    def __init__(self, cause: BaseException, *, gemini_503: bool = False) -> None:
        self.cause = cause
        self.gemini_503 = bool(gemini_503)
        super().__init__(str(cause))


class VlmMlxDiskUnavailable(Exception):
    """MLX VLM omitido: disco Mac por debajo del umbral (preflight opt-in)."""

    def __init__(self, message: str, *, free_pct: float | None = None) -> None:
        self.free_pct = free_pct
        super().__init__(message)


def _vlm_mlx_disk_health_url() -> str:
    """URL de health disco Mac; vacío = sin preflight (comportamiento legacy)."""
    return (os.environ.get("DUCKCLAW_VLM_MLX_DISK_HEALTH_URL") or "").strip()


def _vlm_mlx_disk_min_free_pct() -> float:
    raw = (os.environ.get("DUCKCLAW_VLM_MLX_DISK_MIN_FREE_PCT") or "10").strip()
    try:
        return float(raw)
    except ValueError:
        return 10.0


def _vlm_mlx_enospc_hint_enabled() -> bool:
    return (os.environ.get("DUCKCLAW_VLM_MLX_ENOSPC_HINT") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _vlm_mlx_exception_with_enospc_hint(exc: BaseException) -> BaseException:
    """Enriquece errores MLX ENOSPC solo con ``DUCKCLAW_VLM_MLX_ENOSPC_HINT=1``."""
    if not _vlm_mlx_enospc_hint_enabled():
        return exc
    body = ""
    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
        try:
            body = exc.response.text or ""
        except Exception:
            body = ""
    msg = str(exc)
    needles = ("No space left on device", "Errno 28")
    if any(n in body or n in msg for n in needles):
        hint = (
            "MLX-Vision en Mac Mini sin espacio en disco (ENOSPC). "
            "Ejecuta drenaje en Mac Mini (macmini_disk_drain.sh) antes de reintentar."
        )
        return RuntimeError(f"{hint} Detalle: {vlm_exception_for_log(exc)}")
    return exc


async def _mlx_disk_preflight_or_raise() -> None:
    """
    Preflight disco Mac Mini antes de MLX HTTP.

    Opt-in: solo si ``DUCKCLAW_VLM_MLX_DISK_HEALTH_URL`` está definida.
    Si el endpoint no responde, no bloquea MLX (fail-open).
    """
    url = _vlm_mlx_disk_health_url()
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(2.0)) as client:
            response = await client.get(url)
            payload = response.json() if response.content else {}
    except Exception as exc:  # noqa: BLE001
        _log.warning("VLM MLX disk preflight no disponible (%s): %s", url, exc)
        return
    if not isinstance(payload, dict):
        return
    if payload.get("ok") is True:
        return
    free_pct_raw = payload.get("free_pct")
    free_pct: float | None
    try:
        free_pct = float(free_pct_raw) if free_pct_raw is not None else None
    except (TypeError, ValueError):
        free_pct = None
    min_pct = _vlm_mlx_disk_min_free_pct()
    free_label = f"{free_pct}%" if free_pct is not None else "desconocido"
    raise VlmMlxDiskUnavailable(
        (
            f"VLM MLX omitido: disco Mac Mini por debajo del umbral "
            f"({free_label} libre, mínimo {min_pct}%). "
            f"Ejecuta macmini_disk_drain.sh en la Mac GPU."
        ),
        free_pct=free_pct,
    )


def _mlx_vlm_model_id() -> str:
    """
    VLM local (mlx_vlm) y el LLM de texto (mlx_lm) usan **identificadores distintos** salvo
    que se alineen por env. Prioridad: overrides explícitos → misma resolución que texto Gemma 4
    (``MLX_GEMMA4_MODEL_PATH``, ``MLX_MODEL_*`` si contiene ``gemma``) →
    ``MLX_GEMMA4_DEFAULT_REPO_ID`` (``mlx-community/gemma-4-e4b-it-4bit``).

    Para forzar otro checkpoint (p. ej. LLaVA Mistral si mlx_vlm lo requiere en tu entorno):
    ``DUCKCLAW_VLM_MLX_VLM_MODEL`` o ``MLX_VLM_MODEL``.
    """
    for key in ("DUCKCLAW_VLM_MLX_VLM_MODEL", "MLX_VLM_MODEL"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    g4 = (os.environ.get("MLX_GEMMA4_MODEL_PATH") or "").strip()
    if g4:
        return g4
    mlx = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
    if mlx and "gemma" in mlx.lower():
        return mlx
    try:
        from duckclaw.integrations.llm_providers import MLX_GEMMA4_DEFAULT_REPO_ID

        return MLX_GEMMA4_DEFAULT_REPO_ID
    except ImportError:
        return "mlx-community/gemma-4-e4b-it-4bit"


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
    # load_tokenizer() hace model_path / "tokenizer.json"; debe ser pathlib.Path, no str
    # (evita TypeError: unsupported operand type(s) for /: 'str' and 'str').
    proc_id = (proc_repo or "").strip()
    mid_s = (mid or "").strip()
    if proc_id == mid_s:
        processor_path = model_path
    else:
        processor_path = get_model_path(proc_id)
    model = load_model(model_path, lazy=False)
    eos_token_id = getattr(model.config, "eos_token_id", None)
    image_processor = load_image_processor(model_path)
    processor = load_processor(
        processor_path, True, eos_token_ids=eos_token_id, trust_remote_code=True
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
    return _sanitize_vlm_visible_text((res.text or "").strip())


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
    from core.telegram_media_download import download_telegram_file_bytes

    return await download_telegram_file_bytes(bot_token, file_id)


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
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(http_timeout_s),
        trust_env=_httpx_trust_env_for_openai_base(base_url),
    ) as client:
        try:
            r = await _post_openai_chat_completions_resilient(
                client=client,
                endpoint=endpoint,
                payload=payload,
                headers=headers,
                base_url=base_url,
            )
        except httpx.RequestError:
            raise
        r.raise_for_status()
        data = r.json() if r.content else {}
    try:
        return _sanitize_vlm_visible_text(
            str(data["choices"][0]["message"]["content"] or "").strip()
        )
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
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(http_timeout_s),
        trust_env=_httpx_trust_env_for_openai_base(base_url),
    ) as client:
        try:
            r = await _post_openai_chat_completions_resilient(
                client=client,
                endpoint=endpoint,
                payload=payload,
                headers=headers,
                base_url=base_url,
            )
        except httpx.RequestError:
            raise
        r.raise_for_status()
        data = r.json() if r.content else {}
    try:
        return _sanitize_vlm_visible_text(
            str(data["choices"][0]["message"]["content"] or "").strip()
        )
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


def _gemini_fallback_model() -> str:
    """Un intento extra si el modelo primario devuelve 503 (sobrecarga / outage regional)."""
    return (os.environ.get("DUCKCLAW_VLM_GEMINI_FALLBACK_MODEL") or "gemini-2.0-flash").strip()


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


def _validate_image_bytes(mime_type: str, image_bytes: bytes) -> str:
    mt = (mime_type or "").strip().lower()
    if mt not in _ALLOWED_MIME:
        raise ValueError(f"MIME no permitido: {mt}")
    if not image_bytes:
        raise RuntimeError("imagen vacía")
    limit = _max_image_bytes()
    if len(image_bytes) > limit:
        raise RuntimeError(f"imagen demasiado grande ({len(image_bytes)} > {limit})")
    return mt


async def run_vlm_on_image_bytes(
    *,
    image_bytes: bytes,
    mime_type: str,
    caption: str,
    media_group_id: str = "",
) -> dict[str, Any]:
    """VLM sobre bytes en memoria (admin UI, tests)."""
    mt = _validate_image_bytes(mime_type, image_bytes)
    return await _run_vlm_single_from_bytes(
        image_bytes=image_bytes,
        mime_type=mt,
        caption=caption,
        media_group_id=media_group_id,
    )


async def run_vlm_on_images_batch(
    *,
    items: list[tuple[str, bytes]],
    caption: str,
    media_group_id: str = "",
) -> dict[str, Any]:
    """Hasta 3 imágenes; un solo VLM multimodal."""
    if not items:
        raise ValueError("items vacío")
    if len(items) > 3:
        items = items[:3]
    dl: list[tuple[str, bytes]] = []
    for mime_type, raw in items:
        mt = _validate_image_bytes(mime_type, raw)
        dl.append((mt, raw))
    return await _run_vlm_album_from_bytes(
        items=dl,
        caption=caption,
        media_group_id=media_group_id,
    )


async def process_visual_payload(
    *,
    bot_token: str,
    file_id: str,
    caption: str,
    mime_type: str,
    media_group_id: str = "",
    image_bytes: bytes | None = None,
) -> dict[str, Any]:
    """
    Descarga media de Telegram (si no hay bytes), ejecuta VLM y purga archivo temporal.
    """
    mt = (mime_type or "").strip().lower()
    if image_bytes is None:
        if mt not in _ALLOWED_MIME:
            raise ValueError(f"MIME no permitido: {mt}")
        if not (file_id or "").strip():
            raise ValueError("file_id vacío")
        image_bytes = await _telegram_download_file_bytes(bot_token, file_id)
    else:
        mt = _validate_image_bytes(mime_type, image_bytes)
    return await _run_vlm_single_from_bytes(
        image_bytes=image_bytes,
        mime_type=mt,
        caption=caption,
        media_group_id=media_group_id,
    )


async def _run_vlm_single_from_bytes(
    *,
    image_bytes: bytes,
    mime_type: str,
    caption: str,
    media_group_id: str = "",
) -> dict[str, Any]:
    mt = (mime_type or "").strip().lower()
    image_hash = hashlib.sha256(image_bytes).hexdigest()

    os.makedirs(_tmp_dir(), exist_ok=True)
    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(
            dir=_tmp_dir(), suffix=_suffix_for_mime(mt), delete=False
        ) as f:
            f.write(image_bytes)
            tmp_path = f.name

        _vlm_memory_mitigation()

        mlx_base = _mlx_http_base_url()
        mlx_model = _mlx_http_vision_model().strip()
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
                _log.warning(
                    "VLM mlx_vlm local-first devolvió texto vacío; se intentará HTTP/cloud. "
                    "Revisa carga del modelo (pesos/processor) y logs anteriores."
                )
            except Exception as exc:  # noqa: BLE001
                _log.warning("VLM mlx_vlm local-first falló, se intentará HTTP: %s", exc)
        mlx_to = _mlx_http_timeout_s()
        cloud_to = _openai_cloud_http_timeout_s()
        gemini_to = _gemini_http_timeout_s()
        summary = ""
        confidence = 0.85
        last_exc: BaseException | None = None
        gemini_503_in_chain = False
        for kind in _vlm_backend_order():
            try:
                if kind == "mlx":
                    if _skip_mlx_openai_vision_same_port_as_text_mlx(mlx_base):
                        _log.info(
                            "VLM: se omite MLX HTTP (mismo puerto que inferencia texto en loopback); "
                            "mlx_lm no acepta image_url ahí (404). Opciones: mlx_vlm en el gateway "
                            "(quitar VLM_MLX_DISABLE_LOCAL), visión en otro puerto + VLM_MLX_BASE_URL, "
                            "o DUCKCLAW_VLM_MLX_HTTP_ALLOW_DEFAULT_LOOPBACK=1."
                        )
                        continue
                    await _mlx_disk_preflight_or_raise()
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
                    prim_g = _gemini_model()
                    fb_g = _gemini_fallback_model()
                    g_key = _vlm_gemini_api_key()
                    try:
                        summary = await _call_gemini_vision(
                            api_key=g_key,
                            model=prim_g,
                            mime_type=mt,
                            image_bytes=image_bytes,
                            user_caption=caption,
                            http_timeout_s=gemini_to,
                        )
                        confidence = 0.74
                    except httpx.HTTPStatusError as g_exc:
                        last_exc = g_exc
                        if g_exc.response is not None and g_exc.response.status_code == 503:
                            gemini_503_in_chain = True
                            _log.warning(
                                "VLM vía Gemini no disponible (503): %s",
                                vlm_exception_for_log(g_exc),
                            )
                            if fb_g and fb_g.lower() != prim_g.lower():
                                _log.info(
                                    "VLM: reintento Gemini con fallback model=%s",
                                    fb_g,
                                )
                                try:
                                    summary = await _call_gemini_vision(
                                        api_key=g_key,
                                        model=fb_g,
                                        mime_type=mt,
                                        image_bytes=image_bytes,
                                        user_caption=caption,
                                        http_timeout_s=gemini_to,
                                    )
                                    confidence = 0.72
                                except Exception as fb_exc:  # noqa: BLE001
                                    last_exc = fb_exc
                                    _log.warning(
                                        "VLM vía Gemini (fallback) falló: %s",
                                        vlm_exception_for_log(fb_exc),
                                    )
                                    continue
                            else:
                                continue
                        else:
                            _log.warning(
                                "VLM vía Gemini falló: %s",
                                vlm_exception_for_log(g_exc),
                            )
                            continue
                    except Exception as g_exc:  # noqa: BLE001
                        last_exc = g_exc
                        _log.warning(
                            "VLM vía Gemini falló: %s",
                            vlm_exception_for_log(g_exc),
                        )
                        continue
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
                last_exc = _vlm_mlx_exception_with_enospc_hint(exc) if kind == "mlx" else exc
                if kind == "mlx":
                    _log.warning(
                        "VLM vía MLX falló (base_url=%s): %s",
                        mlx_base,
                        vlm_exception_for_log(last_exc),
                    )
                    if isinstance(exc, httpx.ConnectError) and _is_loopback_openai_base(mlx_base):
                        _log.info(
                            "VLM diagnóstico: no hay listener en %s (connection refused). "
                            "MLX-Inference en MLX_PORT es mlx_lm (solo texto). Si no ejecutas otro "
                            "servidor OpenAI con visión ahí, **elimina** DUCKCLAW_VLM_MLX_BASE_URL y "
                            "VLM_MLX_BASE_URL del .env para no intentar un puerto muerto; visión local "
                            "usa el paquete mlx-vlm en el venv del gateway (uv sync) con "
                            "VLM_MLX_DISABLE_LOCAL=0.",
                            mlx_base,
                        )
                elif kind == "gemini":
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                        if exc.response.status_code == 503:
                            gemini_503_in_chain = True
                            _log.warning(
                                "VLM vía Gemini no disponible (503): %s",
                                vlm_exception_for_log(exc),
                            )
                        else:
                            _log.warning("VLM vía Gemini falló: %s", vlm_exception_for_log(exc))
                    else:
                        _log.warning("VLM vía Gemini falló: %s", vlm_exception_for_log(exc))
                else:
                    _log.warning("VLM vía OpenAI cloud falló: %s", vlm_exception_for_log(exc))
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
                raise VlmIngestAllFailed(
                    last_exc, gemini_503=gemini_503_in_chain
                ) from last_exc
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
        try:
            del image_bytes
        except Exception:
            pass
        _vlm_memory_mitigation()


async def process_visual_album_batch(
    *,
    bot_token: str,
    items: list[tuple[str, str]],
    caption: str,
    media_group_id: str = "",
    items_bytes: list[tuple[str, bytes]] | None = None,
) -> dict[str, Any]:
    """
    Hasta 3 imágenes por request (Telegram álbum); un solo VLM con varias image_url.
    """
    if items_bytes is not None:
        return await _run_vlm_album_from_bytes(
            items=items_bytes,
            caption=caption,
            media_group_id=media_group_id,
        )
    if not items:
        raise ValueError("items vacío")
    if len(items) > 3:
        items = items[:3]
    dl: list[tuple[str, bytes]] = []
    for file_id, mime_type in items:
        mt = (mime_type or "").strip().lower()
        if mt not in _ALLOWED_MIME:
            raise ValueError(f"MIME no permitido: {mt}")
        if not (file_id or "").strip():
            raise ValueError("file_id vacío")
        image_bytes = await _telegram_download_file_bytes(bot_token, file_id)
        dl.append((mt, image_bytes))
    return await _run_vlm_album_from_bytes(
        items=dl,
        caption=caption,
        media_group_id=media_group_id,
    )


async def _run_vlm_album_from_bytes(
    *,
    items: list[tuple[str, bytes]],
    caption: str,
    media_group_id: str = "",
) -> dict[str, Any]:
    if not items:
        raise ValueError("items vacío")
    if len(items) > 3:
        items = items[:3]
    per_hashes: list[str] = []
    dl: list[tuple[str, bytes]] = []
    tmp_paths: list[str] = []
    composite = ""
    os.makedirs(_tmp_dir(), exist_ok=True)
    try:
        for mime_type, image_bytes in items:
            mt = _validate_image_bytes(mime_type, image_bytes)
            per_hashes.append(hashlib.sha256(image_bytes).hexdigest())
            dl.append((mt, image_bytes))
            with tempfile.NamedTemporaryFile(
                dir=_tmp_dir(), suffix=_suffix_for_mime(mt), delete=False
            ) as f:
                f.write(image_bytes)
                tmp_paths.append(f.name)

        _vlm_memory_mitigation()

        composite = hashlib.sha256("|".join(sorted(per_hashes)).encode("utf-8")).hexdigest()
        mlx_base = _mlx_http_base_url()
        mlx_model = _mlx_http_vision_model().strip()
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
                _log.warning(
                    "VLM mlx_vlm local-first (álbum) devolvió texto vacío; se intentará HTTP/cloud."
                )
            except Exception as exc:  # noqa: BLE001
                _log.warning("VLM mlx_vlm local-first (álbum) falló, se intentará HTTP: %s", exc)
        mlx_multi_to = max(_mlx_http_timeout_s(), 45.0)
        cloud_multi_to = max(_openai_cloud_http_timeout_s(), 90.0)
        gemini_multi_to = max(_gemini_http_timeout_s(), 90.0)
        summary = ""
        confidence = 0.85
        last_exc: BaseException | None = None
        gemini_503_in_chain = False
        for kind in _vlm_backend_order():
            try:
                if kind == "mlx":
                    if _skip_mlx_openai_vision_same_port_as_text_mlx(mlx_base):
                        _log.info(
                            "VLM (álbum): se omite MLX HTTP (mismo puerto que mlx_lm texto); "
                            "mlx_lm no sirve visión OpenAI en ese endpoint."
                        )
                        continue
                    await _mlx_disk_preflight_or_raise()
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
                    prim_ga = _gemini_model()
                    fb_ga = _gemini_fallback_model()
                    g_key_a = _vlm_gemini_api_key()
                    try:
                        summary = await _call_gemini_vision_multi(
                            api_key=g_key_a,
                            model=prim_ga,
                            images=dl,
                            user_caption=caption_use,
                            http_timeout_s=gemini_multi_to,
                        )
                        confidence = 0.74
                    except httpx.HTTPStatusError as g_exc:
                        last_exc = g_exc
                        if g_exc.response is not None and g_exc.response.status_code == 503:
                            gemini_503_in_chain = True
                            _log.warning(
                                "VLM (álbum) Gemini no disponible (503): %s",
                                vlm_exception_for_log(g_exc),
                            )
                            if fb_ga and fb_ga.lower() != prim_ga.lower():
                                _log.info(
                                    "VLM (álbum): reintento Gemini con fallback model=%s",
                                    fb_ga,
                                )
                                try:
                                    summary = await _call_gemini_vision_multi(
                                        api_key=g_key_a,
                                        model=fb_ga,
                                        images=dl,
                                        user_caption=caption_use,
                                        http_timeout_s=gemini_multi_to,
                                    )
                                    confidence = 0.72
                                except Exception as fb_exc:  # noqa: BLE001
                                    last_exc = fb_exc
                                    _log.warning(
                                        "VLM (álbum) Gemini (fallback) falló: %s",
                                        vlm_exception_for_log(fb_exc),
                                    )
                                    continue
                            else:
                                continue
                        else:
                            _log.warning(
                                "VLM (álbum) vía Gemini falló: %s",
                                vlm_exception_for_log(g_exc),
                            )
                            continue
                    except Exception as g_exc:  # noqa: BLE001
                        last_exc = g_exc
                        _log.warning(
                            "VLM (álbum) vía Gemini falló: %s",
                            vlm_exception_for_log(g_exc),
                        )
                        continue
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
                last_exc = _vlm_mlx_exception_with_enospc_hint(exc) if kind == "mlx" else exc
                if kind == "mlx":
                    _log.warning(
                        "VLM (álbum) vía MLX falló (base_url=%s): %s",
                        mlx_base,
                        vlm_exception_for_log(last_exc),
                    )
                    if isinstance(exc, httpx.ConnectError) and _is_loopback_openai_base(mlx_base):
                        _log.info(
                            "VLM (álbum) diagnóstico: sin listener en %s. Misma acción que imagen única: "
                            "quitar URLs VLM MLX del .env si no hay servidor visión dedicado; "
                            "mlx-vlm en el venv del gateway para visión local.",
                            mlx_base,
                        )
                elif kind == "gemini":
                    if isinstance(exc, httpx.HTTPStatusError) and exc.response is not None:
                        if exc.response.status_code == 503:
                            gemini_503_in_chain = True
                            _log.warning(
                                "VLM (álbum) Gemini no disponible (503): %s",
                                vlm_exception_for_log(exc),
                            )
                        else:
                            _log.warning(
                                "VLM (álbum) vía Gemini falló: %s",
                                vlm_exception_for_log(exc),
                            )
                    else:
                        _log.warning(
                            "VLM (álbum) vía Gemini falló: %s",
                            vlm_exception_for_log(exc),
                        )
                else:
                    _log.warning(
                        "VLM (álbum) vía OpenAI cloud falló: %s",
                        vlm_exception_for_log(exc),
                    )
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
                raise VlmIngestAllFailed(
                    last_exc, gemini_503=gemini_503_in_chain
                ) from last_exc
            else:
                raise RuntimeError("VLM: ningún backend produjo resumen")
        return {
            "image_hash": composite,
            "vlm_summary": summary[:4000],
            "confidence_score": float(confidence),
            "media_group_id": (media_group_id or "").strip(),
            "image_count": len(dl),
        }
    finally:
        for p in tmp_paths:
            _secure_wipe_remove(p)
        try:
            dl.clear()
        except Exception:
            pass
        _vlm_memory_mitigation()


_ADMIN_MAX_IMAGES = 15


def decode_admin_image_b64(data_base64: str) -> bytes:
    raw = (data_base64 or "").strip()
    if not raw:
        raise ValueError("data_base64 vacío")
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        return base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise ValueError("data_base64 inválido") from exc


def format_vlm_enrichment_block(out: dict[str, Any], *, user_caption: str) -> str:
    cap = (user_caption or "").strip() or "(sin caption)"
    return (
        f"Usuario dice: {cap}\n"
        f"Contexto visual adjunto: {out['vlm_summary']}\n"
        f"[VLM_CONTEXT image_hash={out.get('image_hash', '')} "
        f"confidence={out.get('confidence_score', 0.0)}]"
    ).strip()


def _persist_admin_images_for_tenant(
    decoded: list[tuple[str, bytes]],
    tenant_id: str,
) -> list[str]:
    """Guarda bytes en el vault inbound del tenant y devuelve rutas absolutas.

    Sin esto, la imagen solo se describe (VLM) y sus bytes se pierden: el Report
    Engine no tendría un path que insertar como InlineImage.
    """
    tid = (tenant_id or "").strip()
    if not tid:
        return []
    from core.comfyui_inbound import save_inbound_bytes_for_tenant

    paths: list[str] = []
    for mime, raw in decoded:
        try:
            saved = save_inbound_bytes_for_tenant(raw, tid, mime_type=mime or "image/jpeg")
            paths.append(str(saved))
        except Exception as exc:  # noqa: BLE001
            _log.warning("No se pudo persistir imagen adjunta (tenant=%s): %s", tid, exc)
    return paths


def format_attached_image_paths_block(paths: list[str], *, report_hints: bool = True) -> str:
    """Bloque legible por el agente con las rutas persistidas."""
    if not paths:
        return ""
    lines = [
        f"imagen_{idx} → {path}"
        for idx, path in enumerate(paths[:_ADMIN_MAX_IMAGES], start=1)
    ]
    listing = "\n".join(lines)
    if report_hints:
        return (
            "[IMAGENES_ADJUNTAS] Archivos guardados en el vault (NO hace falta VLM). "
            "Documento NUEVO: create_blank_document → render. "
            "Documento YA EXISTENTE (agregar más evidencias): list_report_instances → "
            "append_images_to_report(instance_id, image_paths) → render_report_instance. "
            "NO crees un Word nuevo si el usuario pide agregar a uno ya construido.\n"
            f"{listing}"
        )
    return (
        "[IMAGENES_ADJUNTAS] Archivos guardados en el vault. "
        "Usa Contexto visual (si hay) y responde con análisis útil; "
        "no exijas herramientas de informe Word salvo que el usuario las pida.\n"
        f"{listing}"
    )


# Intención de *visión* (analizar). Adjunto documental NO dispara VLM.
_VISION_INTENT_RE = re.compile(
    r"(?is)\b("
    r"analiz[aeo]|describ[ae]|interpret[ae]|explica|explicame|"
    r"qu[eé]\s+ves|qu[eé]\s+hay|qu[eé]\s+dice|lee(r)?\s+(la\s+)?imagen|"
    r"lee(r)?\s+(esto|esta|la\s+foto|la\s+captura)|"
    r"ocr|extrae\s+(el\s+)?texto|transcribe|resume\s+(la\s+)?imagen|"
    r"identifica|reconoce|compar(a|e)\s+(estas\s+)?imagen|"
    r"mira\s+(esto|esta|la)|"
    r"visual\s+context|what\s+do\s+you\s+see|describe\s+(this|the)\s+image|"
    r"analyze\s+(this|the)\s+image|read\s+(this|the)\s+image"
    r")\b"
)
_DOCUMENT_ATTACHMENT_RE = re.compile(
    r"(?is)\b("
    r"documento|informe|word|docx|plantilla|blank|en\s+blanco|"
    r"pon(la|lo|las)?|peg(a|ala|alo)|insert(a|ar)|adjunta|adjunto|"
    r"usa\s+(esta|la)\s+imagen|mete|incluy[ea]|coloca"
    r")\b"
)

# Turno solo-imagen (playground/Telegram): intención explícita para el LLM y user_incoming.
_IMAGE_ONLY_DEFAULT_INTENT = "Analiza esta imagen y responde según el contexto del chat."
_IMAGE_ONLY_DIRECTIVE = (
    "[DIRECTIVA_IMAGEN] Solo imagen(es) sin texto. "
    "Responde con análisis útil (Contexto visual si hay, rutas en [IMAGENES_ADJUNTAS]). "
    "No preguntes qué hacer. "
    "NO invoques create_blank_document ni append_images_to_report salvo que el chat pida informe Word."
)
_EMAIL_DIRECTIVE = (
    "[DIRECTIVA_CORREO] Pide correo/email. Usa Gmail MCP search_threads → get_message/get_thread. "
    "NO uses search_corpus (Workspace) ni extract_document_text en .png/.jpg. "
    "Si VLM no describe la captura, busca is:inbox newer_than:1d o pide remitente/asunto."
)


def first_user_line_from_enriched_message(enriched: str) -> str:
    """Primera línea humana antes de bloques [META]/[IMAGENES_ADJUNTAS]/[Nota]."""
    text = (enriched or "").strip()
    if not text:
        return ""
    return text.split("\n\n[", 1)[0].strip()


def default_intent_for_image_only_turn(enriched: str = "") -> str:
    head = first_user_line_from_enriched_message(enriched)
    return head or _IMAGE_ONLY_DEFAULT_INTENT


def should_run_vlm_for_caption(message: str) -> bool:
    """VLM por defecto cuando hay imagen; solo se omite en adjunto documental puro.

    - Caption vacío / neutro → True (usuario espera que se lea la imagen).
    - Intención visual explícita → True.
    - Solo intención documental (Word/informe/ponla…) sin visión → False.
    """
    text = (message or "").strip()
    if _DOCUMENT_ATTACHMENT_RE.search(text) and not _VISION_INTENT_RE.search(text):
        return False
    return True


def decode_admin_images_payload(
    images: list[dict[str, Any]] | None,
) -> list[tuple[str, bytes]]:
    if not images:
        return []
    if len(images) > _ADMIN_MAX_IMAGES:
        raise ValueError(f"máximo {_ADMIN_MAX_IMAGES} imágenes por mensaje")
    decoded: list[tuple[str, bytes]] = []
    for img in images:
        if not isinstance(img, dict):
            raise ValueError("imagen inválida")
        mime = str(img.get("mime_type") or img.get("mime") or "").strip().lower()
        b64 = str(img.get("data_base64") or img.get("base64") or "")
        raw = decode_admin_image_b64(b64)
        mt = _validate_image_bytes(mime, raw)
        decoded.append((mt, raw))
    return decoded


async def enrich_message_with_admin_images(
    message: str,
    images: list[dict[str, Any]] | None,
    *,
    tenant_id: str = "",
    force_vlm: bool | None = None,
) -> str:
    """
    Carril 1 (siempre): decodifica + persiste bytes → [IMAGENES_ADJUNTAS].
    Carril 2 (default on): VLM salvo caption de adjunto documental puro.

    ``force_vlm``: None = auto por intención; True/False fuerza el carril.
    """
    if not images:
        return (message or "").strip()

    decoded = decode_admin_images_payload(images)
    user_caption = (message or "").strip()
    _email_directive = False
    try:
        from duckclaw.workers.tool_orchestration import incoming_has_email_intent

        _email_directive = incoming_has_email_intent(user_caption)
    except Exception:
        pass
    base = user_caption
    image_only = bool(decoded) and not base
    if image_only:
        base = _IMAGE_ONLY_DEFAULT_INTENT
    run_vlm = should_run_vlm_for_caption(base) if force_vlm is None else bool(force_vlm)

    # Persistencia PRIMERO: si VLM se cancela/falla, el documento aún tiene paths.
    saved_paths = _persist_admin_images_for_tenant(decoded, tenant_id)
    blocks: list[str] = []
    vlm_ok = False

    if run_vlm:
        caption = base or "Analiza esta imagen."
        try:
            if len(decoded) == 1:
                mt, raw = decoded[0]
                out = await run_vlm_on_image_bytes(
                    image_bytes=raw,
                    mime_type=mt,
                    caption=caption,
                )
            else:
                out = await run_vlm_on_images_batch(items=decoded, caption=caption)
            blocks.append(format_vlm_enrichment_block(out, user_caption=base))
            vlm_ok = True
        except VlmIngestAllFailed:
            # Carril documental intacto: paths ya persistidos.
            blocks.append(
                "[Nota: visión (VLM) no disponible; las imágenes quedaron guardadas "
                "y el agente puede usarlas sin descripción visual.]"
            )
        except Exception as exc:  # noqa: BLE001
            _log.warning("VLM falló tras persistir adjuntos: %s", vlm_exception_for_log(exc))
            blocks.append(
                "[Nota: visión (VLM) falló; las imágenes quedaron guardadas "
                "y el agente puede usarlas sin descripción visual.]"
            )

    path_block = format_attached_image_paths_block(saved_paths, report_hints=not image_only)
    if path_block:
        blocks.append(path_block)
    elif tenant_id and decoded:
        blocks.append(
            "[IMAGENES_ADJUNTAS] No se pudieron guardar las rutas (revisa vault del tenant)."
        )
    if image_only and saved_paths:
        blocks.append(_IMAGE_ONLY_DIRECTIVE)
    if _email_directive:
        blocks.append(_EMAIL_DIRECTIVE)

    parts = [p for p in [base, *blocks] if p]
    enriched = "\n\n".join(parts).strip()
    return enriched


async def push_vlm_state_delta_redis(
    redis_client: Any,
    *,
    tenant_id: str,
    image_hash: str,
    vlm_summary: str,
    confidence_score: float,
) -> None:
    """LPUSH JSON StateDelta visual (cola dedicada, no duckdb_write_queue)."""
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
