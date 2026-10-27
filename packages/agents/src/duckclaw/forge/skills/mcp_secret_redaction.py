"""Keep a connector's own credentials out of what comes back to the model and out of the audit log.

The key is resolved per call from the vault and never enters a prompt, but an upstream can echo it (an error that prints the
request URL or headers, a debug field). Whatever a tool returns or raises is scrubbed of that connector's secret values first.
"""

from __future__ import annotations

import json
import logging
from typing import Any

_log = logging.getLogger(__name__)

REDACTED = "[REDACTED]"
# Shorter values ("1", "true", "prod") would mangle ordinary text; real credentials are longer.
_MIN_SECRET_LEN = 8


def connector_secrets(db: Any, connector: dict[str, Any]) -> list[str]:
    """Secret values this connector sends upstream: bearer token, explicit launch env and the integration env the guard injects. Never raises."""
    values: list[str] = []
    try:
        if str(connector.get("auth_kind") or "").strip().lower() == "bearer":
            from duckclaw.admin_mcp_connectors import resolve_connector_bearer_token

            values.append(str(resolve_connector_bearer_token(db, connector) or ""))
        values += [str(v) for v in (connector.get("launch_env") or {}).values()]
        if str(connector.get("transport") or "").strip().lower() == "stdio" and db is not None:
            from duckclaw.forge.skills.mcp_connector_guard import apply_integration_env

            values += [str(v) for v in apply_integration_env(db, connector, {}).values()]
    except Exception:  # noqa: BLE001
        _log.debug("mcp redaction: could not resolve every secret", exc_info=True)
    return sorted({v for v in values if len(v) >= _MIN_SECRET_LEN}, key=len, reverse=True)


def redact_secrets(text: str, secrets: list[str]) -> str:
    """``text`` with every secret value (raw or JSON-escaped, as it appears inside a JSON string) replaced by [REDACTED]."""
    for secret in secrets:
        for form in {secret, json.dumps(secret)[1:-1]}:
            text = text.replace(form, REDACTED)
    return text
