"""Static guardrails: gateway lifespan must not run privileged deploy subprocesses."""

from __future__ import annotations

from pathlib import Path


def test_gateway_lifespan_has_no_redis_config_set_or_docker() -> None:
    source = Path("services/api-gateway/core/lifespan.py").read_text(encoding="utf-8")
    lifespan_start = source.index("async def lifespan")
    lifespan_end = source.index("await app.state.redis.aclose()")
    block = source[lifespan_start:lifespan_end]

    assert "config_set" not in block
    assert "docker" not in block.lower()
    assert "subprocess.run" not in block
    assert "assert_gateway_startup_ready" in block


def test_gateway_main_delegates_lifespan_to_core_module() -> None:
    main = Path("services/api-gateway/main.py").read_text(encoding="utf-8")

    assert "from core.lifespan import lifespan" in main
    assert "async def lifespan" not in main
    assert "assert_gateway_startup_ready" not in main


def test_gateway_main_delegates_health_to_core_module() -> None:
    main = Path("services/api-gateway/main.py").read_text(encoding="utf-8")
    health_owner = Path("services/api-gateway/core/health.py").read_text(encoding="utf-8")

    assert "from core.health import router as health_router" in main
    assert "app.include_router(health_router)" in main
    assert "async def root()" not in main
    assert "async def health()" not in main
    assert "async def system_health()" not in main
    assert "_telegram_path_route_count" not in main
    assert '@router.get("/health")' in health_owner
    assert "async def system_health" in health_owner
