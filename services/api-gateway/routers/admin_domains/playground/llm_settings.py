"""Resolución LLM, defaults runtime y estado de voz para admin playground."""

from __future__ import annotations

import os
from typing import Any

from routers.admin_domains.playground.schemas import LLM_PROVIDER_CATALOG


def resolved_llm_env() -> dict[str, str]:
    prov = (os.environ.get("DUCKCLAW_LLM_PROVIDER") or os.environ.get("LLM_PROVIDER") or "").strip()
    model = (os.environ.get("DUCKCLAW_LLM_MODEL") or os.environ.get("LLM_MODEL") or "").strip()
    base = (os.environ.get("DUCKCLAW_LLM_BASE_URL") or os.environ.get("LLM_BASE_URL") or "").strip()
    return {"provider": prov, "model": model, "base_url": base}


def _runtime_setting_text(
    db: Any,
    *,
    tenant_id: str,
    actor_email: str,
    domain: str,
    key: str,
) -> dict[str, str]:
    from duckclaw.admin_runtime_settings import resolve_runtime_setting

    resolved = resolve_runtime_setting(
        db,
        tenant_id=tenant_id,
        actor_email=actor_email,
        domain=domain,
        key=key,
        default="",
    )
    return {
        "value": str(resolved.get("value") or "").strip(),
        "source": str(resolved.get("source") or "").strip(),
    }


def playground_runtime_defaults(tenant_id: str, actor_email: str) -> dict[str, str]:
    try:
        from core.admin_identity import open_gateway_db

        with open_gateway_db(read_only=True) as db:
            pairs = {
                "llm_provider": ("llm", "provider"),
                "llm_model": ("llm", "model"),
                "llm_base_url": ("llm", "base_url"),
                "default_worker_id": ("playground", "default_worker_id"),
                "default_vault_db_path": ("playground", "default_vault_db_path"),
            }
            out: dict[str, str] = {}
            for out_key, (domain, key) in pairs.items():
                item = _runtime_setting_text(
                    db,
                    tenant_id=tenant_id,
                    actor_email=actor_email,
                    domain=domain,
                    key=key,
                )
                if item["source"] == "db" and item["value"]:
                    out[out_key] = item["value"]
            return out
    except Exception:
        return {}


def resolved_llm_for_chat(chat_id: str | None) -> dict[str, str]:
    """LLM efectivo: override agent_config del chat (p. ej. /model) o .env del gateway."""
    env = resolved_llm_env()
    cid = (chat_id or "").strip()
    if not cid:
        return {**env, "scope": "env_bootstrap"}
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.graphs.on_the_fly_commands import _effective_llm_triplet_for_chat_ui

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        return {**env, "scope": "env_bootstrap"}
    try:
        db = DuckClaw(gw, read_only=True, engine="python")
    except Exception:
        return {**env, "scope": "env_bootstrap", "db_lock_error": True}
    try:
        provider, model, base_url = _effective_llm_triplet_for_chat_ui(db, cid)
    except Exception:
        provider, model, base_url = "", "", ""
    finally:
        db.close()
    has_chat = bool((provider or "").strip())
    return {
        "provider": (provider or env["provider"] or "").strip(),
        "model": (model or env["model"] or "").strip(),
        "base_url": (base_url or env["base_url"] or "").strip(),
        "scope": "chat" if has_chat else "env_bootstrap",
    }


def resolved_llm_for_playground(
    *,
    chat_id: str,
    tenant_id: str,
    actor_email: str,
) -> dict[str, str]:
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.runtime_session_settings import resolve_session_runtime_setting

    env = resolved_llm_env()
    cid = (chat_id or "").strip()
    gw = (get_gateway_db_path() or "").strip()
    if not cid or not gw or not os.path.isfile(gw):
        runtime = playground_runtime_defaults(tenant_id, actor_email)
        if any(runtime.get(k) for k in ("llm_provider", "llm_model", "llm_base_url")):
            return {
                "provider": runtime.get("llm_provider", env["provider"]).strip(),
                "model": runtime.get("llm_model", env["model"]).strip(),
                "base_url": runtime.get("llm_base_url", env["base_url"]).strip(),
                "scope": "runtime",
            }
        return {**env, "scope": "env_bootstrap"}

    try:
        db = DuckClaw(gw, read_only=True, engine="python")
    except Exception:
        return {**env, "scope": "env_bootstrap", "db_lock_error": True}
    try:
        tenant_candidates = [str(tenant_id or "default").strip() or "default"]
        if "default" not in tenant_candidates:
            tenant_candidates.append("default")

        def _chat_setting(key: str) -> str:
            for candidate in tenant_candidates:
                value = (
                    resolve_session_runtime_setting(
                        db,
                        cid,
                        key,
                        tenant_id=candidate,
                    )
                    or ""
                ).strip()
                if value:
                    return value
            return ""

        chat_provider = _chat_setting("llm_provider")
        chat_model = _chat_setting("llm_model")
        chat_base_url = _chat_setting("llm_base_url")
    except Exception:
        chat_provider = chat_model = chat_base_url = ""
    finally:
        db.close()

    if chat_provider or chat_model or chat_base_url:
        return {
            "provider": (chat_provider or env["provider"]).strip(),
            "model": (chat_model or env["model"]).strip(),
            "base_url": (chat_base_url or env["base_url"]).strip(),
            "scope": "chat",
        }

    runtime = playground_runtime_defaults(tenant_id, actor_email)
    if any(runtime.get(k) for k in ("llm_provider", "llm_model", "llm_base_url")):
        return {
            "provider": (runtime.get("llm_provider") or env["provider"]).strip(),
            "model": (runtime.get("llm_model") or env["model"]).strip(),
            "base_url": (runtime.get("llm_base_url") or env["base_url"]).strip(),
            "scope": "runtime",
        }

    return {
        "provider": env["provider"].strip(),
        "model": env["model"].strip(),
        "base_url": env["base_url"].strip(),
        "scope": "env_bootstrap",
    }


def playground_llm_catalog(active_provider: str) -> list[dict[str, Any]]:
    active = (active_provider or "").strip().lower()
    catalog: list[dict[str, Any]] = []
    for item in LLM_PROVIDER_CATALOG:
        row = dict(item)
        row["active"] = row["id"] == active
        row["keys_ok"] = llm_keys_configured(row.get("env_keys") or [])
        catalog.append(row)
    return catalog


def llm_keys_configured(env_keys: list[str]) -> bool:
    for key in env_keys:
        if (os.environ.get(key) or "").strip():
            return True
    return len(env_keys) == 0


async def playground_voice_status() -> dict[str, bool]:
    from core import sensory_client

    configured = sensory_client.sensory_enabled()
    tts_loaded = False
    if configured:
        health = await sensory_client.sensory_health()
        tts_loaded = bool((health or {}).get("tts_loaded"))
    return {
        "configured": configured,
        "available": configured and tts_loaded,
        "tts_loaded": tts_loaded,
    }


async def playground_realtime_voice_status() -> dict[str, bool | str]:
    """Pipecat SmallWebRTC availability for admin live voice (distinct from Sensory batch)."""
    import httpx

    enabled = (os.environ.get("DUCKCLAW_VOICE_ENABLED") or "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    transport = (os.environ.get("DUCKCLAW_VOICE_TRANSPORT") or "small_webrtc").strip()
    base = (os.environ.get("DUCKCLAW_VOICE_INTERNAL_URL") or "").strip().rstrip("/")
    available = False
    if enabled and base:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"{base}/health")
                if response.status_code == 200:
                    payload = response.json()
                    available = bool((payload or {}).get("ok"))
        except Exception:
            available = False
    return {
        "configured": enabled and bool(base),
        "available": available,
        "transport": transport,
    }
