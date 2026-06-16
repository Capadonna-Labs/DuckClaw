# services/api-gateway/core/config.py
"""Re-export canonical gateway settings (owner: duckclaw.gateway.settings)."""

from duckclaw.gateway.settings import GatewaySettings, get_gateway_settings, reset_gateway_settings_cache

Settings = GatewaySettings
settings = get_gateway_settings()

__all__ = [
    "GatewaySettings",
    "Settings",
    "get_gateway_settings",
    "reset_gateway_settings_cache",
    "settings",
]
