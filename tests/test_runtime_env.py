"""runtime_env — Redis y gateway desde .env."""

from __future__ import annotations

from pathlib import Path

from duckclaw.runtime_env import (
    resolve_agent_chat_url,
    resolve_api_base_url,
    resolve_gateway_http_base,
    resolve_redis_url,
)


def test_resolve_redis_url_from_dotenv(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("REDIS_URL=redis://127.0.0.1:6380/1\n", encoding="utf-8")
    assert resolve_redis_url(tmp_path) == "redis://127.0.0.1:6380/1"


def test_resolve_gateway_http_base_from_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_GATEWAY_URL", raising=False)
    (tmp_path / ".env").write_text(
        "DUCKCLAW_GATEWAY_URL=http://127.0.0.1:9003\nDUCKCLAW_GATEWAY_PORT=8000\n",
        encoding="utf-8",
    )
    assert resolve_gateway_http_base(tmp_path) == "http://127.0.0.1:9003"


def test_resolve_agent_chat_url(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text(
        "DUCKCLAW_GATEWAY_URL=http://127.0.0.1:9010\n", encoding="utf-8"
    )
    assert resolve_agent_chat_url(tmp_path) == "http://127.0.0.1:9010/api/v1/agent/chat"


def test_resolve_api_base_url_aliases_gateway(tmp_path: Path) -> None:
    (tmp_path / ".env").write_text("DUCKCLAW_GATEWAY_URL=http://gw.local:7777\n", encoding="utf-8")
    assert resolve_api_base_url(tmp_path) == "http://gw.local:7777"
