"""Unit tests for playground SLM settings (sin TestClient completo)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from gateway_import import ensure_gateway_on_sys_path

ensure_gateway_on_sys_path()

from routers.admin_domains.playground.slm_settings import (
    discover_slm_adapters,
    resolved_slm_for_playground,
    slm_base_url,
)


def test_slm_base_url_prefers_duckclaw_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_SLM_BASE_URL", "http://100.x.x.x:8080/v1")
    assert slm_base_url() == "http://100.x.x.x:8080/v1"


def test_resolved_slm_defaults_disabled(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLX_MODEL_ID", "gemma4-e4b")
    monkeypatch.setenv("DUCKCLAW_SLM_BASE_URL", "http://127.0.0.1:8080/v1")
    payload = resolved_slm_for_playground(
        chat_id="no-db-chat",
        tenant_id="default",
        repo_root=tmp_path,
    )
    assert payload["enabled"] is False
    assert payload["pm2_name"] == "MLX-Inference"
    assert payload["model"] == "gemma4-e4b"


def test_resolved_slm_async_probe(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncio

    from routers.admin_domains.playground.slm_settings import resolved_slm_for_playground_async

    monkeypatch.setenv("MLX_MODEL_ID", "test-model")

    async def _run() -> dict:
        with patch(
            "routers.admin_domains.playground.slm_settings.probe_mlx_inference_status",
            new=AsyncMock(return_value="online"),
        ):
            return await resolved_slm_for_playground_async(
                chat_id="x",
                tenant_id="default",
                repo_root=tmp_path,
            )

    payload = asyncio.run(_run())
    assert payload["mlx_status"] == "online"


def test_discover_slm_adapters_empty_repo(tmp_path: Path) -> None:
    assert discover_slm_adapters(tmp_path, active_adapter="") == []
