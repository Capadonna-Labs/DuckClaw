"""
Punto único de importación para configuración DuckClaw.

- **Valores:** ``runtime_env`` + ``gateway_port`` (leen ``.env`` / propuesto / PM2 JSON).
- **Política:** ``env_secrets`` (qué no persistir en ecosystem).
- **Archivos:** ``dotenv_immutable`` (merge y bloqueo de escritura).
"""

from __future__ import annotations

from duckclaw.dotenv_immutable import (
    is_repo_dotenv_immutable,
    merge_proposed_env_file,
    merged_root_and_proposed_flat_env,
    parse_dotenv_file,
    root_dotenv_flat_env,
)
from duckclaw.env_secrets import (
    DOTENV_OWNED_ENV_KEYS,
    DOTENV_OVERRIDE_KEYS,
    SECRET_ENV_KEYS,
    apply_dotenv_overrides_to_os_environ,
    is_dotenv_owned_env_key,
    is_secret_env_key,
    strip_dotenv_owned_from_env,
    strip_secrets_from_env,
)
from duckclaw.gateway_port import (
    DEFAULT_GATEWAY_PORT,
    gateway_base_url,
    gateway_port_from_dotenv,
    gateway_port_from_pm2_json,
    parse_uvicorn_port_from_pm2_args,
    resolve_gateway_port,
)
from duckclaw.runtime_env import (
    DEFAULT_REDIS_URL,
    resolve_agent_chat_url,
    resolve_api_base_url,
    resolve_gateway_http_base,
    resolve_redis_url,
)

__all__ = [
    "DEFAULT_GATEWAY_PORT",
    "DEFAULT_REDIS_URL",
    "DOTENV_OWNED_ENV_KEYS",
    "DOTENV_OVERRIDE_KEYS",
    "SECRET_ENV_KEYS",
    "apply_dotenv_overrides_to_os_environ",
    "gateway_base_url",
    "gateway_port_from_dotenv",
    "gateway_port_from_pm2_json",
    "is_dotenv_owned_env_key",
    "is_repo_dotenv_immutable",
    "is_secret_env_key",
    "merge_proposed_env_file",
    "merged_root_and_proposed_flat_env",
    "parse_dotenv_file",
    "parse_uvicorn_port_from_pm2_args",
    "resolve_agent_chat_url",
    "resolve_api_base_url",
    "resolve_gateway_http_base",
    "resolve_gateway_port",
    "resolve_redis_url",
    "root_dotenv_flat_env",
    "strip_dotenv_owned_from_env",
    "strip_secrets_from_env",
]
