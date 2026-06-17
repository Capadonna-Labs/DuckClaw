"""Carga y caché de LLM / metadatos para ``graph_server`` (sin abrir el vault del gateway)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

_graph_state: dict[str, Any] = {}


def get_graph_state() -> dict[str, Any]:
    """Estado compartido LLM + studio (mutación solo vía helpers de este paquete)."""
    return _graph_state


def _ensure_llm_config() -> None:
    """Carga y cachea LLM y metadatos. No abre el .duckdb del gateway."""
    from duckclaw.integrations.llm_providers import (
        _ensure_duckclaw_llm_env_from_legacy_llm_vars,
        build_llm,
    )
    from duckclaw.gateway_db import get_gateway_db_path

    # Misma fusión LLM_* → DUCKCLAW_* que build_llm (evita leer solo DUCKCLAW_* obsoleto).
    _ensure_duckclaw_llm_env_from_legacy_llm_vars()

    provider = os.environ.get("DUCKCLAW_LLM_PROVIDER", "mlx").strip().lower()
    model = os.environ.get("DUCKCLAW_LLM_MODEL", "").strip()
    base_url = os.environ.get("DUCKCLAW_LLM_BASE_URL", "http://127.0.0.1:8080/v1").strip()
    fingerprint = (provider, model, base_url)

    if _graph_state.get("llm") is not None and _graph_state.get("_llm_env_fingerprint") == fingerprint:
        return

    # Proveedor/modelo/base cambiaron: el grafo Studio y el LLM global deben reconstruirse.
    if _graph_state.get("llm") is not None:
        try:
            _sd = _graph_state.get("studio_db")
            if _sd is not None and hasattr(_sd, "close"):
                _sd.close()
        except Exception:
            pass
        _graph_state.pop("studio_graph", None)
        _graph_state.pop("studio_db", None)
        _graph_state.pop("_llm_env_fingerprint", None)
        _graph_state.pop("llm", None)

    db_path = get_gateway_db_path()
    os.makedirs(str(Path(db_path).parent), exist_ok=True)

    system_prompt = os.environ.get(
        "DUCKCLAW_SYSTEM_PROMPT",
        "Eres un asistente útil con acceso a una base de datos.",
    ).strip()

    llm = build_llm(provider, model, base_url)
    if llm is None:
        raise RuntimeError(
            "No se pudo inicializar el LLM. "
            "Configura DUCKCLAW_LLM_PROVIDER y DUCKCLAW_LLM_BASE_URL en .env."
        )

    _graph_state["llm"] = llm
    _graph_state["_llm_env_fingerprint"] = fingerprint
    _graph_state["provider"] = provider
    _graph_state["model"] = model
    _graph_state["base_url"] = base_url
    _graph_state["db_path"] = db_path
    _graph_state["system_prompt"] = system_prompt


def _resolve_display_model() -> str:
    provider = os.environ.get("DUCKCLAW_LLM_PROVIDER", "mlx")
    if provider == "mlx":
        mid = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
        if mid:
            return f"mlx:{mid.rstrip('/').rsplit('/', 1)[-1]}"
        return "mlx:local"
    model = os.environ.get("DUCKCLAW_LLM_MODEL", "")
    return f"{provider}:{model}" if model else provider
