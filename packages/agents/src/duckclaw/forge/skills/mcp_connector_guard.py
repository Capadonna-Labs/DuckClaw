"""Per-tenant secrets and human confirmation for MCP connectors.

- ``metadata.integration_env`` ({ENV_VAR: integration_id}): the stdio server gets the TENANT's
  secret from Integraciones. A host value of those variables is always removed, so a user
  without keys never runs on someone else's account.
- ``metadata.integration_env_optional``: same, but the connector also works without them (e.g. a
  broker login done in the browser instead of stored credentials). When all of them are set,
  ``metadata.env_when_optional_set`` is added (e.g. switch the server to headless login).
- ``metadata.confirm_tools`` (fnmatch patterns): calling a matching tool stores the call as a
  pending action instead of running it; the human runs it with ``/approve <id>`` or drops it
  with ``/reject <id>``. DuckClaw's read_only filter only knows create_/delete_/update_ names,
  so tools such as place_*/cancel_*/close_* need this.
"""

from __future__ import annotations

import fnmatch
import json
import secrets
import time
from typing import Any

_PENDING_TTL_S = 900
_PENDING_KEY = "duckclaw:mcp_pending:{}"
_CHAT_PENDING_KEY = "duckclaw:mcp_pending_chat:{}"


def connector_metadata(connector: dict[str, Any]) -> dict[str, Any]:
    """Preset metadata overlaid by the connector row's; ``confirm_tools`` is the union of both
    so a row created before a preset update never loses a confirmation."""
    from duckclaw.mcp_connector_presets import preset_payload

    preset_id = str(connector.get("preset_id") or "").strip()
    preset_meta = dict((preset_payload(preset_id) or {}).get("metadata") or {}) if preset_id else {}
    row_meta = dict(connector.get("metadata") or {})
    merged = {**preset_meta, **row_meta}
    merged["confirm_tools"] = sorted(
        {str(p) for p in (preset_meta.get("confirm_tools") or []) + (row_meta.get("confirm_tools") or []) if str(p)}
    )
    return merged


def tenant_integration_env(
    db: Any, connector: dict[str, Any], mapping: dict[str, Any] | None = None
) -> tuple[dict[str, str], list[str]]:
    """(env vars resolved for the connector's tenant, env vars mapped but not configured)."""
    from duckclaw.integration_secrets import resolve_integration_api_key

    if mapping is None:
        mapping = connector_metadata(connector).get("integration_env") or {}
    tenant_id = str(connector.get("tenant_id") or "default")
    resolved: dict[str, str] = {}
    missing: list[str] = []
    for env_var, integration_id in mapping.items():
        value = resolve_integration_api_key(str(integration_id), db=db, tenant_id=tenant_id)
        if value:
            resolved[str(env_var)] = value
        else:
            missing.append(str(env_var))
    return resolved, missing


def apply_integration_env(db: Any, connector: dict[str, Any], env: dict[str, str]) -> dict[str, str]:
    meta = connector_metadata(connector)
    required = meta.get("integration_env") or {}
    optional = meta.get("integration_env_optional") or {}
    if not required and not optional:
        return env
    out = {k: v for k, v in env.items() if k not in required and k not in optional}  # never the host's
    resolved, missing = tenant_integration_env(db, connector, required)
    if missing:
        label = connector.get("display_name") or connector.get("connector_id")
        raise ValueError(f"{label}: faltan claves en Integraciones ({', '.join(missing)})")
    out.update(resolved)
    if optional:
        opt_resolved, opt_missing = tenant_integration_env(db, connector, optional)
        out.update(opt_resolved)
        if not opt_missing:
            out.update({str(k): str(v) for k, v in (meta.get("env_when_optional_set") or {}).items()})
    return out


def needs_confirmation(connector: dict[str, Any], tool_name: str) -> bool:
    name = str(tool_name or "").strip().lower()
    return any(fnmatch.fnmatch(name, str(p).lower()) for p in connector_metadata(connector)["confirm_tools"])


def _redis() -> Any:
    import redis

    from duckclaw.runtime_env import resolve_redis_url

    url = resolve_redis_url()
    if not url:
        raise RuntimeError("REDIS_URL no configurado: no se pueden guardar acciones pendientes")
    return redis.from_url(url, decode_responses=True)


def store_pending(connector: dict[str, Any], tool_name: str, payload: dict[str, Any], *, chat_id: str) -> str:
    """Store the call and return the message the agent relays to the user."""
    action_id = secrets.token_hex(3)
    action = {
        "id": action_id,
        "connector_id": str(connector.get("connector_id") or ""),
        "tenant_id": str(connector.get("tenant_id") or "default"),
        "chat_id": str(chat_id or ""),
        "tool": str(tool_name),
        "args": payload,
        "created_at": time.time(),
    }
    r = _redis()
    r.set(_PENDING_KEY.format(action_id), json.dumps(action, ensure_ascii=False), ex=_PENDING_TTL_S)
    if action["chat_id"]:
        r.set(_CHAT_PENDING_KEY.format(action["chat_id"]), action_id, ex=_PENDING_TTL_S)
    label = connector.get("display_name") or connector.get("connector_id")
    return (
        f"[CONFIRMACIÓN PENDIENTE #{action_id}] {label} · {tool_name} "
        f"{json.dumps(payload, ensure_ascii=False)[:400]}\n"
        f"No se ejecutó. Muéstrale al usuario estos datos y pídele que responda /approve {action_id} "
        f"para ejecutarla o /reject {action_id} para cancelarla (vence en {_PENDING_TTL_S // 60} min)."
    )


def take_pending(*, chat_id: str, tenant_id: str, action_id: str = "") -> dict[str, Any] | None:
    """Remove and return a pending action of this chat (by id, or the latest one)."""
    r = _redis()
    aid = (action_id or "").strip().lstrip("#") or (r.get(_CHAT_PENDING_KEY.format(chat_id)) or "")
    if not aid:
        return None
    raw = r.get(_PENDING_KEY.format(aid))
    if not raw:
        return None
    action = json.loads(raw)
    # The id alone is not enough: the action must belong to this chat and tenant.
    if str(action.get("chat_id") or "") not in ("", str(chat_id)) or str(action.get("tenant_id")) != str(tenant_id):
        return None
    r.delete(_PENDING_KEY.format(aid))
    if r.get(_CHAT_PENDING_KEY.format(chat_id)) == aid:
        r.delete(_CHAT_PENDING_KEY.format(chat_id))
    return action
