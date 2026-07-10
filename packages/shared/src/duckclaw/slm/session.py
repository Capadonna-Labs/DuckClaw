"""SLM (MLX-Inference) session resolution and HTTP execution."""

from __future__ import annotations

import os
from typing import Any

from duckclaw.integrations.llm_providers import mlx_openai_compatible_base_url


def slm_base_url_from_env() -> str:
    explicit = (os.environ.get("DUCKCLAW_SLM_BASE_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit if explicit.endswith("/v1") else f"{explicit}/v1"
    return mlx_openai_compatible_base_url()


def slm_model_from_env() -> str:
    return (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()


def slm_adapter_from_env() -> str:
    return (os.environ.get("MLX_ADAPTER_PATH") or "").strip()


def is_slm_enabled_for_chat(db: Any, chat_id: str, *, tenant_id: str = "default") -> bool:
    if db is None:
        return False
    from duckclaw.runtime_session_settings import resolve_session_runtime_setting

    raw = (
        resolve_session_runtime_setting(
            db,
            chat_id,
            "slm_enabled",
            tenant_id=tenant_id,
        )
        or ""
    ).strip()
    return raw.lower() in ("1", "true", "yes", "on")


def resolve_slm_session_for_chat(
    db: Any,
    chat_id: str,
    *,
    tenant_id: str = "default",
) -> dict[str, str]:
    """SLM efectivo para tool execute_slm."""
    base = slm_base_url_from_env()
    model = slm_model_from_env()
    adapter = slm_adapter_from_env()
    enabled = False
    if db is not None and (chat_id or "").strip():
        from duckclaw.runtime_session_settings import resolve_session_runtime_setting

        enabled = is_slm_enabled_for_chat(db, chat_id, tenant_id=tenant_id)
        session_adapter = (
            resolve_session_runtime_setting(
                db,
                chat_id,
                "slm_adapter_path",
                tenant_id=tenant_id,
            )
            or ""
        ).strip()
        session_base = (
            resolve_session_runtime_setting(
                db,
                chat_id,
                "slm_base_url",
                tenant_id=tenant_id,
            )
            or ""
        ).strip()
        if session_adapter:
            adapter = session_adapter
        if session_base:
            base = session_base.rstrip("/")
            if not base.endswith("/v1"):
                base = f"{base}/v1"
    return {
        "enabled": "true" if enabled else "false",
        "base_url": base,
        "model": model,
        "adapter_path": adapter,
    }
