"""SLM evaluation utilities (MLX-Inference PM2)."""

from duckclaw.slm.client import execute_slm_http, execute_slm_http_json, validate_slm_xml_output
from duckclaw.slm.models import ExecuteSLMRequest
from duckclaw.slm.session import (
    is_slm_enabled_for_chat,
    resolve_slm_session_for_chat,
    slm_adapter_from_env,
    slm_base_url_from_env,
    slm_model_from_env,
)

__all__ = [
    "ExecuteSLMRequest",
    "execute_slm_http",
    "execute_slm_http_json",
    "is_slm_enabled_for_chat",
    "resolve_slm_session_for_chat",
    "slm_adapter_from_env",
    "slm_base_url_from_env",
    "slm_model_from_env",
    "validate_slm_xml_output",
]
