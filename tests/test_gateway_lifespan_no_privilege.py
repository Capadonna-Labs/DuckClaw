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


def test_gateway_main_delegates_homeostasis_to_core_module() -> None:
    main = Path("services/api-gateway/main.py").read_text(encoding="utf-8")
    homeostasis_owner = Path("services/api-gateway/core/homeostasis.py").read_text(encoding="utf-8")

    assert "from core.homeostasis import router as homeostasis_router" in main
    assert "app.include_router(homeostasis_router)" in main
    assert "async def homeostasis_status" not in main
    assert "async def homeostasis_ask_task" not in main
    assert "class AskTaskBody" not in main
    assert '@router.get("/api/v1/homeostasis/status")' in homeostasis_owner
    assert "async def homeostasis_ask_task" in homeostasis_owner


def test_gateway_main_delegates_middleware_to_core_module() -> None:
    main = Path("services/api-gateway/main.py").read_text(encoding="utf-8")
    middleware_owner = Path("services/api-gateway/core/middleware.py").read_text(encoding="utf-8")

    assert "from core.middleware import register_gateway_middleware" in main
    assert "register_gateway_middleware(app)" in main
    assert "async def observability_context_middleware" not in main
    assert "def register_gateway_middleware" in middleware_owner


def test_gateway_main_delegates_agent_routes_to_core_module() -> None:
    main = Path("services/api-gateway/main.py").read_text(encoding="utf-8")
    agent_owner = Path("services/api-gateway/core/agent_routes.py").read_text(encoding="utf-8")

    assert "app.include_router(agent_routes_router)" in main
    assert "async def agent_workers" not in main
    assert '@router.get("/api/v1/agent/workers")' in agent_owner


def test_gateway_main_delegates_db_read_to_core_module() -> None:
    main = Path("services/api-gateway/main.py").read_text(encoding="utf-8")
    db_read_owner = Path("services/api-gateway/core/db_read_route.py").read_text(encoding="utf-8")

    assert "app.include_router(db_read_router)" in main
    assert "class ReadRequest" not in main
    assert '@router.post("/api/v1/db/read")' in db_read_owner
