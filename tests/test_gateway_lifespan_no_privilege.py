"""Static guardrails: gateway lifespan must not run privileged deploy subprocesses."""

from __future__ import annotations

from pathlib import Path


def test_gateway_lifespan_has_no_redis_config_set_or_docker() -> None:
    source = Path("services/api-gateway/main.py").read_text(encoding="utf-8")
    lifespan_start = source.index("async def lifespan")
    lifespan_end = source.index("@app.get(\"/health\")")
    block = source[lifespan_start:lifespan_end]

    assert "config_set" not in block
    assert "docker" not in block.lower()
    assert "subprocess.run" not in block
    assert "assert_gateway_startup_ready" in block
