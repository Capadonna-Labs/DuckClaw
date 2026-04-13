from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import os
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


def _try_mlx_vlm_local_before_http() -> bool:
    """Evita colgarse en mlx_lm HTTP (texto) con payloads visuales: local primero si mlx_vlm está instalado."""
    global _mlx_vlm_missing_logged
    if not _mlx_vlm_local_enabled():
        return False
    if (os.environ.get("DUCKCLAW_VLM_HTTP_BEFORE_LOCAL") or "").strip().lower() in ("1", "true", "yes"):
        return False
    try:
        import importlib.util

        if importlib.util.find_spec("mlx_vlm") is None:
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
            # region agent log
            try:
                _p = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-adf9d8.log"
                with open(_p, "a", encoding="utf-8") as _df:
                    _df.write(
                        json.dumps(
                            {
                                "sessionId": "adf9d8",
                                "hypothesisId": "H6",
                                "location": "vlm_ingest.py:_post_openai_chat_completions_resilient",
                                "message": "mlx_connect_retry",
                                "data": {
                                    "attempt": attempt + 1,
                                    "max": _MLX_LOOPBACK_CONNECT_ATTEMPTS,
                                },
                                "timestamp": int(__import__("time").time() * 1000),
                            }
                        )
                        + "\n"
                    )
            except Exception:
                pass
            # endregion
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
    """Puerto donde suele escuchar ``mlx_lm server`` (texto), mismo criterio que ``_mlx_http_base_url``."""
    raw = (os.environ.get("VLM_MLX_PORT") or os.environ.get("MLX_PORT") or "8081").strip()
    try:
        return max(1, min(65535, int(raw)))
    except ValueError:
        return 8081


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
        except httpx.RequestError as _req_exc:
            # region agent log
            try:
                _u = httpx.URL(endpoint)
                _p = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-adf9d8.log"
                with open(_p, "a", encoding="utf-8") as _df:
                    _df.write(
                        json.dumps(
                            {
                                "sessionId": "adf9d8",
                                "hypothesisId": "H5",
                                "location": "vlm_ingest.py:_call_openai_vision",
                                "message": "httpx_request_error",
                                "data": {
                                    "endpoint_host": _u.host,
                                    "endpoint_port": _u.port,
                                    "exc_type": type(_req_exc).__name__,
                                    "exc_detail": (str(_req_exc) or "")[:400],
                                },
                                "timestamp": int(__import__("time").time() * 1000),
                            }
                        )
                        + "\n"
                    )
            except Exception:
                pass
            # endregion
            raise
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
        except httpx.RequestError as _req_exc:
            # region agent log
            try:
                _u = httpx.URL(endpoint)
                _p = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-adf9d8.log"
                with open(_p, "a", encoding="utf-8") as _df:
                    _df.write(
                        json.dumps(
                            {
                                "sessionId": "adf9d8",
                                "hypothesisId": "H5",
                                "location": "vlm_ingest.py:_call_openai_vision_multi",
                                "message": "httpx_request_error",
                                "data": {
                                    "endpoint_host": _u.host,
                                    "endpoint_port": _u.port,
                                    "exc_type": type(_req_exc).__name__,
                                    "exc_detail": (str(_req_exc) or "")[:400],
                                },
                                "timestamp": int(__import__("time").time() * 1000),
                            }
                        )
                        + "\n"
                    )
            except Exception:
                pass
            # endregion
            raise
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

        mlx_base = _mlx_http_base_url()
        mlx_model = _mlx_http_vision_model().strip()
        # region agent log
        try:
            _p = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-adf9d8.log"
            _te = _httpx_trust_env_for_openai_base(mlx_base)
            with open(_p, "a", encoding="utf-8") as _df:
                _df.write(
                    json.dumps(
                        {
                            "sessionId": "adf9d8",
                            "hypothesisId": "H3",
                            "location": "vlm_ingest.py:process_visual_payload",
                            "message": "mlx_http_resolve",
                            "data": {
                                "mlx_model": mlx_model,
                                "mlx_base": mlx_base,
                                "trust_env": _te,
                                "env_VLM_MLX_PORT": (os.environ.get("VLM_MLX_PORT") or "").strip(),
                                "env_MLX_PORT": (os.environ.get("MLX_PORT") or "").strip(),
                                "has_DUCKCLAW_VLM_MLX_BASE_URL": bool(
                                    (os.environ.get("DUCKCLAW_VLM_MLX_BASE_URL") or "").strip()
                                ),
                                "has_VLM_MLX_BASE_URL": bool(
                                    (os.environ.get("VLM_MLX_BASE_URL") or "").strip()
                                ),
                            },
                            "timestamp": int(__import__("time").time() * 1000),
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        # endregion
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
                    _log.warning(
                        "VLM vía MLX falló (base_url=%s): %s",
                        mlx_base,
                        vlm_exception_for_log(exc),
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
                # region agent log
                try:
                    _p = "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-adf9d8.log"
                    with open(_p, "a", encoding="utf-8") as _df:
                        _df.write(
                            json.dumps(
                                {
                                    "sessionId": "adf9d8",
                                    "hypothesisId": "H2",
                                    "location": "vlm_ingest.py:process_visual_payload",
                                    "message": "vlm_all_failed",
                                    "data": {"gemini_503": gemini_503_in_chain},
                                    "timestamp": int(__import__("time").time() * 1000),
                                }
                            )
                            + "\n"
                        )
                except Exception:
                    pass
                # endregion
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
                    _log.warning(
                        "VLM (álbum) vía MLX falló (base_url=%s): %s",
                        mlx_base,
                        vlm_exception_for_log(exc),
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
