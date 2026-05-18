"""Barrel env_config — imports públicos."""

from duckclaw import env_config


def test_env_config_exports() -> None:
    assert env_config.resolve_gateway_port is not None
    assert env_config.resolve_redis_url is not None
    assert env_config.is_secret_env_key("TELEGRAM_BOT_TOKEN")
    assert env_config.DEFAULT_GATEWAY_PORT == 8000
