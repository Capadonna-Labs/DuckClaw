"""HTTP client for MLX-Inference (OpenAI-compatible)."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from duckclaw.integrations.llm_providers import mlx_openai_compatible_model_name
from duckclaw.slm.models import ExecuteSLMRequest

_log = logging.getLogger(__name__)


def validate_slm_xml_output(text: str) -> dict[str, Any]:
    """Heurística mínima: presencia de thought y/o tool_call XML."""
    body = (text or "").strip()
    has_thought = "<thought>" in body and "</thought>" in body
    has_tool = "<tool_call>" in body and "</tool_call>" in body
    return {
        "ok": has_thought or has_tool,
        "has_thought": has_thought,
        "has_tool_call": has_tool,
    }


def execute_slm_http(
    request: ExecuteSLMRequest,
    *,
    base_url: str,
    model: str,
    timeout_sec: float = 120.0,
) -> str:
    """
    Ejecuta inferencia SLM vía POST /v1/chat/completions.
    Retorna texto formateado para el LLM evaluador (profesor).
    """
    base = (base_url or "").strip().rstrip("/")
    if not base:
        return "🔴 Ceguera Sensorial (SLM Crash): DUCKCLAW_SLM_BASE_URL no configurado."
    url = f"{base}/chat/completions" if base.endswith("/v1") else f"{base}/v1/chat/completions"
    resolved_model = mlx_openai_compatible_model_name(model or "gemma4")
    payload = {
        "model": resolved_model,
        "messages": [{"role": "user", "content": request.prompt}],
        "temperature": float(request.temperature),
        "max_tokens": int(request.max_tokens),
    }
    try:
        with httpx.Client(timeout=timeout_sec) as client:
            response = client.post(url, json=payload)
            if response.status_code >= 400:
                detail = response.text[:500]
                return (
                    f"🔴 Ceguera Sensorial (SLM Crash): HTTP {response.status_code} — {detail}"
                )
            data = response.json()
            choices = data.get("choices") or []
            if not choices:
                return "🔴 Ceguera Sensorial (SLM Crash): respuesta vacía del MLX-Inference."
            message = choices[0].get("message") or {}
            content = (message.get("content") or "").strip()
            if not content:
                return "🔴 Ceguera Sensorial (SLM Crash): contenido vacío en message.content."
            adapter_note = ""
            if request.adapter_path and request.adapter_path != "default":
                adapter_note = (
                    f"\n(adapter solicitado: {request.adapter_path}; "
                    "aplicar vía MLX_ADAPTER_PATH + pm2 restart MLX-Inference)"
                )
            return f"SLM Output:\n{content}{adapter_note}"
    except httpx.TimeoutException:
        return "🔴 Ceguera Sensorial (SLM Crash): timeout esperando MLX-Inference."
    except Exception as exc:
        _log.debug("execute_slm_http failed", exc_info=True)
        return f"🔴 Ceguera Sensorial (SLM Crash): {exc}"


def execute_slm_http_json(
    request: ExecuteSLMRequest,
    *,
    base_url: str,
    model: str,
    timeout_sec: float = 120.0,
) -> dict[str, Any]:
    """Variante estructurada para tests."""
    text = execute_slm_http(
        request,
        base_url=base_url,
        model=model,
        timeout_sec=timeout_sec,
    )
    ok = not text.startswith("🔴")
    validation = validate_slm_xml_output(text) if ok else {"ok": False}
    return {
        "ok": ok and validation.get("ok", False),
        "text": text,
        "validation": validation,
    }
