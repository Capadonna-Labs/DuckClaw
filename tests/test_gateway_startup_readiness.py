"""Gateway startup readiness (Redis + schema fail-fast)."""

from __future__ import annotations

import asyncio

import pytest


def test_assert_gateway_startup_ready_fails_without_redis(monkeypatch) -> None:
    from duckclaw.infra.readiness import assert_gateway_startup_ready

    monkeypatch.delenv("LITE_MODE", raising=False)
    monkeypatch.delenv("DUCKCLAW_SPAWN_PROFILE", raising=False)
    monkeypatch.delenv("DUCKCLAW_SPAWN_USE_DB_WRITER", raising=False)
    monkeypatch.setenv("DUCKCLAW_DEV_MODE", "1")

    async def _run() -> None:
        await assert_gateway_startup_ready(
            redis_url="redis://127.0.0.1:6399/0",
            gateway_db_path="db/missing.duckdb",
        )

    with pytest.raises(RuntimeError, match="Redis unreachable|duckclaw-healthcheck"):
        asyncio.run(_run())


def test_assert_gateway_startup_ready_fails_on_pending_schema(monkeypatch, tmp_path) -> None:
    from duckclaw.infra.readiness import assert_gateway_startup_ready

    db_path = str(tmp_path / "missing" / "hub.duckdb")

    monkeypatch.setattr(
        "duckclaw.infra.readiness.check_redis_readiness",
        lambda url, timeout_sec=2.0: (True, "ok"),
    )

    async def _run() -> None:
        await assert_gateway_startup_ready(
            redis_url="redis://127.0.0.1:6379/0",
            gateway_db_path=db_path,
        )

    with pytest.raises(RuntimeError, match="duckclaw-migrate"):
        asyncio.run(_run())


def test_gateway_settings_require_production_secrets(monkeypatch) -> None:
    from duckclaw.gateway.settings import GatewaySettings, reset_gateway_settings_cache

    reset_gateway_settings_cache()
    monkeypatch.delenv("DUCKCLAW_DEV_MODE", raising=False)
    monkeypatch.delenv("DUCKCLAW_ADMIN_API_KEY", raising=False)
    settings = GatewaySettings(
        DUCKCLAW_DEV_MODE=False,
        DUCKCLAW_ADMIN_API_KEY="",
        DUCKCLAW_LLM_PROVIDER="openrouter",
        OPENROUTER_API_KEY="",
    )
    with pytest.raises(RuntimeError, match="DUCKCLAW_ADMIN_API_KEY"):
        settings.require_production_secrets()


def test_gateway_settings_dev_mode_skips_secrets() -> None:
    from duckclaw.gateway.settings import GatewaySettings

    settings = GatewaySettings(DUCKCLAW_DEV_MODE=True, DUCKCLAW_ADMIN_API_KEY="")
    settings.require_production_secrets()


def test_gateway_settings_local_llm_requires_base_url(monkeypatch) -> None:
    from duckclaw.gateway.settings import GatewaySettings, reset_gateway_settings_cache

    reset_gateway_settings_cache()
    monkeypatch.delenv("DUCKCLAW_DEV_MODE", raising=False)
    settings = GatewaySettings(
        DUCKCLAW_DEV_MODE=False,
        DUCKCLAW_ADMIN_API_KEY="admin-ok",
        DUCKCLAW_LLM_PROVIDER="mlx",
        DUCKCLAW_LLM_BASE_URL="",
    )
    with pytest.raises(RuntimeError, match="DUCKCLAW_LLM_BASE_URL"):
        settings.require_production_secrets()

    settings_ok = GatewaySettings(
        DUCKCLAW_DEV_MODE=False,
        DUCKCLAW_ADMIN_API_KEY="admin-ok",
        DUCKCLAW_LLM_PROVIDER="mlx",
        DUCKCLAW_LLM_BASE_URL="http://127.0.0.1:8080/v1",
    )
    settings_ok.require_production_secrets()
