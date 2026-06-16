"""Gateway configuration (single owner for api-gateway settings)."""

from duckclaw.gateway.settings import GatewaySettings, get_gateway_settings, reset_gateway_settings_cache

__all__ = [
    "GatewaySettings",
    "get_gateway_settings",
    "reset_gateway_settings_cache",
]
