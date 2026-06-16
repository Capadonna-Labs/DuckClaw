from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

import duckclaw.db_write_queue as db_write_queue
from duckclaw.commands.model_setup import _DEFAULT_BASE_URL_BY_PROVIDER, _DEFAULT_MODEL_BY_PROVIDER, _PROVIDERS
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.integrations.llm_providers import mlx_openai_compatible_base_url
from duckclaw.runtime_session_settings import RUNTIME_SESSION_DOMAIN, runtime_session_actor
from duckclaw.write_commands import UpsertRuntimeSettingCommand

router = APIRouter(tags=["admin-playground-chat"])

_REPO_ROOT = Path(__file__).resolve().parents[4]


def _repo_root() -> Path:
    raw = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    return Path(raw) if raw else _REPO_ROOT


def _env_file() -> Path:
    return _repo_root() / ".env"


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    expected = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DUCKCLAW_ADMIN_API_KEY no configurada en el gateway",
        )
    if (x_admin_key or "").strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin key inválida")


def actor_from_header(x_actor: str | None = Header(None, alias="X-Duckclaw-Actor")) -> str:
    raw = (x_actor or "").strip()[:128]
    if raw and raw != "admin-ui":
        return raw
    admin_email = os.environ.get("DUCKCLAW_ADMIN_EMAIL", "").strip()
    if admin_email and "@" in admin_email:
        return admin_email[:128]
    return raw or "admin-ui"


def _problem(status_code: int, title: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"type": "about:blank", "title": title, "status": status_code, "detail": detail},
    )


def _audit_log_path() -> Path:
    path = _repo_root() / ".duckclaw" / "admin-audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _admin_audit(
    action: str,
    resource: str,
    detail: str,
    *,
    actor: str = "admin-ui",
    meta: dict[str, Any] | None = None,
) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": (actor or "admin-ui")[:128],
        "action": action[:64],
        "resource": resource[:256],
        "detail": detail[:2000],
        "meta": meta or {},
    }
    try:
        with _audit_log_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _gateway_effective_tenant_id(request_tenant: str | None) -> str:
    import main as gateway_main

    raw = (request_tenant or "").strip() or "default"
    return gateway_main._effective_tenant_id(raw)


def _playground_telegram_user_id(override: str | None = None) -> str:
    """ID Telegram del operador (mismo que Telegram Guard y /workers en DM)."""
    return (
        (override or "").strip()
        or (os.environ.get("DUCKCLAW_OWNER_ID") or os.environ.get("DUCKCLAW_ADMIN_CHAT_ID") or "")
        .strip()
    )


def _playground_team_context(
    *,
    telegram_user_id: str | None = None,
    tenant_id: str | None = None,
    chat_id: str | None = None,
) -> dict[str, Any]:
    """
    Equipo efectivo alineado con ``/workers`` (get_effective_team_templates) y whitelist Telegram.
    En Telegram DM, ``chat_id`` del equipo suele ser el ``user_id`` numérico.
    """
    from duckclaw.gateway_db import GatewayDbEphemeralReadonly, get_gateway_db_path
    from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session
    from duckclaw.graphs.on_the_fly_commands import (
        _get_authorized_role,
        _is_gateway_owner_user,
        get_effective_team_templates,
        get_team_templates,
        get_tenant_team_templates,
    )

    tid = _gateway_effective_tenant_id(tenant_id)
    tg_uid = _playground_telegram_user_id(telegram_user_id)
    raw_chat = (chat_id or "").strip()
    team_lookup_id = (
        tg_uid
        or (raw_chat if raw_chat and not is_admin_ui_chat_session(raw_chat) else "")
        or "admin-playground"
    )
    team_chat_id = (tg_uid or raw_chat or "admin-playground").strip() or "admin-playground"

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        return {
            "workers": [],
            "telegram_user_id": tg_uid,
            "team_chat_id": team_chat_id,
            "tenant_id": tid,
            "authorized": False,
            "whitelist_role": None,
            "team_source": "none",
            "team_hint": "Gateway DuckDB no encontrada",
        }

    db = GatewayDbEphemeralReadonly(gw)
    role = ""
    authorized = False
    if tg_uid:
        if _is_gateway_owner_user(tg_uid):
            authorized = True
            role = "owner"
        else:
            role = _get_authorized_role(db, tenant_id=tid, user_id=tg_uid)
            authorized = role in ("admin", "user")
    else:
        authorized = True
        role = "admin-ui"

    workers: list[str] = []
    team_source = "none"
    team_hint = ""
    if authorized:
        workers = list(get_effective_team_templates(db, team_lookup_id, tid, None))
        if get_team_templates(db, team_lookup_id):
            team_source = "chat"
            team_hint = "Equipo de este chat (/workers)"
        elif get_tenant_team_templates(db, tid):
            team_source = "tenant"
            team_hint = f"Equipo del tenant «{tid}»"
        elif (os.environ.get("DUCKCLAW_TEAM_MEMBERS") or "").strip():
            team_source = "env"
            team_hint = "Equipo desde variables de entorno (DUCKCLAW_TEAM_MEMBERS)"
        else:
            team_source = "all"
            team_hint = "Sin /workers configurado: todos los templates"

    if tg_uid and not authorized:
        team_hint = (
            f"Usuario Telegram {tg_uid} no está en la whitelist del tenant «{tid}». "
            "Añádelo en Telegram → Whitelist o usa /team en el bot."
        )

    return {
        "workers": workers,
        "telegram_user_id": tg_uid,
        "team_chat_id": team_chat_id,
        "tenant_id": tid,
        "authorized": authorized,
        "whitelist_role": role or None,
        "team_source": team_source,
        "team_hint": team_hint,
    }


def _merge_playground_catalog_and_team_workers(
    catalog_workers: list[dict[str, str]],
    team_ctx: dict[str, Any],
) -> list[dict[str, str]]:
    """Admin Playground muestra solo catálogo DB-first; team legacy queda para Telegram."""
    return list(catalog_workers)


def _playground_worker_allowed_in_team(team_ctx: dict[str, Any], worker_id: str) -> bool:
    from duckclaw.workers.identity import normalize_worker_id
    from duckclaw.workers.template_registry import resolve_template_id_global

    wid = normalize_worker_id(worker_id)
    if not wid or wid == "default":
        return True
    if (team_ctx.get("team_source") or "") == "all":
        return True
    aliases: set[str] = set()
    for raw in team_ctx.get("workers") or []:
        label = str(raw or "").strip()
        if not label:
            continue
        aliases.add(normalize_worker_id(label))
        aliases.add(normalize_worker_id(resolve_template_id_global(label) or label))
    return wid in aliases


def _playground_worker_explicitly_in_team(team_ctx: dict[str, Any], worker_id: str) -> bool:
    """Equipo explícito (sin atajo ``team_source=all``) para consola con actor real."""
    from duckclaw.workers.identity import normalize_worker_id
    from duckclaw.workers.template_registry import resolve_template_id_global

    wid = normalize_worker_id(worker_id)
    if not wid or wid == "default":
        return True
    aliases: set[str] = set()
    for raw in team_ctx.get("workers") or []:
        label = str(raw or "").strip()
        if not label:
            continue
        aliases.add(normalize_worker_id(label))
        aliases.add(normalize_worker_id(resolve_template_id_global(label) or label))
    return wid in aliases


class PlaygroundImageIn(BaseModel):
    mime_type: str = Field(..., max_length=64)
    data_base64: str = Field(..., max_length=20_000_000)


class PlaygroundModelBody(BaseModel):
    chat_id: str = Field(..., min_length=1, max_length=128)
    provider: str = Field(..., min_length=1, max_length=32)
    model: str | None = Field(default=None, max_length=256)
    base_url: str | None = Field(default=None, max_length=512)


class PlaygroundVaultBody(BaseModel):
    chat_id: str = Field(..., min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=64)
    vault_db_path: str | None = Field(
        default=None,
        max_length=512,
        description="Ruta .duckdb; vacío quita el override por conversación.",
    )


class PlaygroundWorkerBody(BaseModel):
    chat_id: str = Field(..., min_length=1, max_length=128)
    tenant_id: str | None = Field(default=None, max_length=64)
    worker_id: str = Field(..., min_length=1, max_length=64)


class PlaygroundChatBody(BaseModel):
    worker_id: str = Field(default="default", max_length=64)
    message: str = Field(default="", max_length=16000)
    chat_id: str = Field(default="admin-playground", max_length=128)
    tenant_id: str = Field(default="default", max_length=64)
    project_id: str | None = Field(default=None, max_length=64)
    telegram_user_id: str | None = Field(
        default=None,
        max_length=32,
        description="ID Telegram para whitelist y equipo /workers (default: DUCKCLAW_OWNER_ID)",
    )
    vault_db_path: str | None = Field(
        default=None,
        max_length=512,
        description="Override DuckDB por conversación (prioridad sobre manifest del worker).",
    )
    images: list[PlaygroundImageIn] = Field(default_factory=list, max_length=3)
    stream: bool = Field(
        default=False,
        description="Si true, respuesta text/event-stream (tokens SSE + [DONE]).",
    )
    voice_response: bool = Field(
        default=False,
        description="Si true (con stream), sintetiza TTS tras la respuesta y emite evento SSE audio.",
    )

    @model_validator(mode="after")
    def _message_or_images(self) -> "PlaygroundChatBody":
        if not (self.message or "").strip() and not self.images:
            raise ValueError("message o images requeridos")
        return self


class PlaygroundVoiceBody(BaseModel):
    """Nota de voz → STT → agente → TTS (sin Telegram)."""

    worker_id: str = Field(default="default", max_length=64)
    chat_id: str = Field(default="admin-playground", max_length=128)
    tenant_id: str = Field(default="default", max_length=64)
    project_id: str | None = Field(default=None, max_length=64)
    audio_base64: str = Field(..., min_length=8, description="OGG/WAV/WebM base64 desde el navegador")
    language_hint: str | None = Field(default="es", max_length=16)
    voice_response: bool = Field(
        default=True,
        description="Si true, sintetiza respuesta con TTS (Identity Lock). Si falla, solo texto.",
    )


class PlaygroundChatCancelBody(BaseModel):
    chat_id: str = Field(..., min_length=1, max_length=128)


class AdminConversationCreateBody(BaseModel):
    title: str | None = None
    section: str | None = None
    worker_id: str | None = None


class AdminConversationPatchBody(BaseModel):
    title: str


_LLM_PROVIDER_CATALOG: list[dict[str, Any]] = [
    {
        "id": "deepseek",
        "label": "DeepSeek (API en la nube)",
        "kind": "api",
        "env_keys": ["DEEPSEEK_API_KEY"],
        "base_url_example": "https://api.deepseek.com/v1",
        "model_example": "deepseek-chat",
        "hint": "Requiere cuenta DeepSeek y API key en .env",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "kind": "api",
        "env_keys": ["OPENAI_API_KEY"],
        "base_url_example": "https://api.openai.com/v1",
        "model_example": "gpt-4o-mini",
        "hint": "ChatGPT / API OpenAI oficial",
    },
    {
        "id": "groq",
        "label": "Groq (API rápida)",
        "kind": "api",
        "env_keys": ["GROQ_API_KEY"],
        "base_url_example": "https://api.groq.com/openai/v1",
        "model_example": "llama-3.3-70b-versatile",
        "hint": "Inferencia en la nube con modelos Llama",
    },
    {
        "id": "openrouter",
        "label": "OpenRouter (proxy unificado)",
        "kind": "api",
        "env_keys": ["OPENROUTER_API_KEY"],
        "base_url_example": "https://openrouter.ai/api/v1",
        "model_example": "deepseek/deepseek-v4-flash",
        "hint": "Un endpoint para muchos modelos; app attribution en rankings",
    },
    {
        "id": "gemini",
        "label": "Google Gemini",
        "kind": "api",
        "env_keys": ["GOOGLE_API_KEY", "GEMINI_API_KEY"],
        "base_url_example": "",
        "model_example": "gemini-2.0-flash",
        "hint": "GOOGLE_API_KEY o GEMINI_API_KEY",
    },
    {
        "id": "anthropic",
        "label": "Anthropic Claude",
        "kind": "api",
        "env_keys": ["ANTHROPIC_API_KEY"],
        "base_url_example": "",
        "model_example": "claude-3-5-haiku-20241022",
        "hint": "API Anthropic",
    },
    {
        "id": "ollama",
        "label": "Ollama (local)",
        "kind": "local",
        "env_keys": [],
        "base_url_example": "http://localhost:11434",
        "model_example": "llama3.2",
        "hint": "Instala Ollama y ejecuta: ollama pull llama3.2",
    },
    {
        "id": "mlx",
        "label": "MLX (Mac local)",
        "kind": "local",
        "env_keys": [],
        "base_url_example": "http://127.0.0.1:8080/v1",
        "model_example": "gemma / tu modelo MLX",
        "hint": "pm2 start config/ecosystem.mlx.config.cjs antes del gateway",
    },
    {
        "id": "huggingface",
        "label": "Hugging Face",
        "kind": "api",
        "env_keys": ["HUGGINGFACE_API_KEY", "HF_TOKEN"],
        "base_url_example": "",
        "model_example": "mistralai/Mistral-7B-Instruct-v0.3",
        "hint": "Token HF en .env",
    },
]


def _resolved_llm_env() -> dict[str, str]:
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


def _playground_runtime_defaults(tenant_id: str, actor_email: str) -> dict[str, str]:
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


def _resolved_llm_for_chat(chat_id: str | None) -> dict[str, str]:
    """LLM efectivo: override agent_config del chat (p. ej. /model) o .env del gateway."""
    env = _resolved_llm_env()
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


def _resolved_llm_for_playground(
    *,
    chat_id: str,
    tenant_id: str,
    actor_email: str,
) -> dict[str, str]:
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.runtime_session_settings import resolve_session_runtime_setting

    env = _resolved_llm_env()
    cid = (chat_id or "").strip()
    gw = (get_gateway_db_path() or "").strip()
    if not cid or not gw or not os.path.isfile(gw):
        runtime = _playground_runtime_defaults(tenant_id, actor_email)
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

    runtime = _playground_runtime_defaults(tenant_id, actor_email)
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


def _playground_llm_catalog(active_provider: str) -> list[dict[str, Any]]:
    active = (active_provider or "").strip().lower()
    catalog: list[dict[str, Any]] = []
    for item in _LLM_PROVIDER_CATALOG:
        row = dict(item)
        row["active"] = row["id"] == active
        row["keys_ok"] = _llm_keys_configured(row.get("env_keys") or [])
        catalog.append(row)
    return catalog


def _llm_keys_configured(env_keys: list[str]) -> bool:
    for key in env_keys:
        if (os.environ.get(key) or "").strip():
            return True
    return len(env_keys) == 0


async def _playground_voice_status() -> dict[str, bool]:
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


def _duckdb_paths_same(a: str, b: str) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return (a or "").strip() == (b or "").strip()


def _iter_template_ids_for_catalog() -> list[str]:
    from duckclaw.workers.template_registry import list_template_ids

    return list_template_ids()


def _pick_playground_worker(
    team_ctx: dict[str, Any],
    worker_id: str | None = None,
    *,
    require_browser_sandbox: bool = False,
) -> str:
    """Primer worker del equipo, del catálogo en disco, o ``default``."""
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", (worker_id or "").strip())
    if wid:
        return wid
    team = [w for w in (team_ctx.get("workers") or []) if isinstance(w, str) and w.strip()]
    if require_browser_sandbox:
        from routers.admin_domains.sandbox_sessions import _worker_has_browser_sandbox

        for candidate in team:
            if _worker_has_browser_sandbox(candidate):
                return candidate
        for candidate in _iter_template_ids_for_catalog():
            if _worker_has_browser_sandbox(candidate):
                return candidate
    elif team:
        return team[0].strip()
    catalog = _iter_template_ids_for_catalog()
    if "default" in catalog:
        return "default"
    return catalog[0] if catalog else "default"


def _playground_vault_options_for_team(team_ctx: dict[str, Any]) -> list[dict[str, str]]:
    from duckclaw.vaults import list_vault_options_for_user

    uid = str(team_ctx.get("telegram_user_id") or "").strip()
    if not uid:
        uid = _playground_telegram_user_id(None) or "default"
    return list_vault_options_for_user(uid)


async def _resolved_vault_for_admin_chat(
    chat_id: str,
    team_ctx: dict[str, Any],
    worker_id: str | None,
    *,
    body_override: str | None = None,
    request: Request | None = None,
    runtime_default_vault: str | None = None,
) -> dict[str, Any]:
    """Bóveda efectiva: body > meta conversación > runtime DB-first > worker/activa."""
    from duckclaw.gateway_db import resolve_env_duckdb_path

    cid = (chat_id or "").strip()
    tid = str(team_ctx.get("tenant_id") or "default").strip() or "default"
    override = (body_override or "").strip()
    scope = "default"
    if not override and request is not None:
        redis_client = getattr(request.app.state, "redis", None)
        if redis_client is not None and cid:
            from core.admin_conversations import get_conversation_meta

            meta = await get_conversation_meta(redis_client, tid, cid)
            if meta is not None and (meta.vault_db_path or "").strip():
                override = (meta.vault_db_path or "").strip()
                scope = "chat"
    elif override:
        scope = "chat"
    try:
        default_path = _playground_vault_db_path(team_ctx, worker_id)
    except Exception:
        default_path = ""
    runtime_default = (runtime_default_vault or "").strip()
    if not override and runtime_default:
        runtime_effective = resolve_env_duckdb_path(runtime_default)
        if os.path.isfile(runtime_effective):
            return {
                "effective_path": runtime_effective,
                "scope": "runtime",
                "override_path": None,
                "default_path": runtime_default,
            }
    effective = resolve_env_duckdb_path(override or default_path)
    return {
        "effective_path": effective,
        "scope": scope,
        "override_path": override or None,
        "default_path": default_path or None,
    }


def _playground_vault_db_path(
    team_ctx: dict[str, Any],
    worker_id: str | None = None,
) -> str:
    """Ruta .duckdb del vault del playground (misma lógica que invoke_chat)."""
    from duckclaw.gateway_db import resolve_env_duckdb_path
    from duckclaw.vaults import resolve_active_vault, resolve_template_vault_path, vault_scope_id_for_tenant
    from duckclaw.workers.manifest import load_manifest

    tid = str(team_ctx.get("tenant_id") or "default").strip() or "default"
    uid = str(team_ctx.get("telegram_user_id") or "").strip()
    if not uid:
        raw_chat = str(team_ctx.get("team_chat_id") or "").strip()
        from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

        if raw_chat and not is_admin_ui_chat_session(raw_chat):
            uid = raw_chat
    if not uid:
        uid = _playground_telegram_user_id(None) or "admin-playground"
    scope = vault_scope_id_for_tenant(tid)
    _, vault_path = resolve_active_vault(uid, scope)
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", (worker_id or "").strip())
    if wid:
        try:
            spec = load_manifest(wid)
            tpl = resolve_template_vault_path(spec.forge_vault_binding, uid)
            if tpl:
                vault_path = tpl
        except Exception:
            pass
    return resolve_env_duckdb_path(str(vault_path or "").strip())


def _open_playground_vault_db(vault_path: str, *, read_only: bool = True) -> Any:
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path, resolve_env_duckdb_path
    from duckclaw.spawn_profile import spawn_inline_writes_enabled

    abs_path = vault_path
    if not os.path.isabs(abs_path):
        abs_path = str(_repo_root() / vault_path.lstrip("/"))
    if not os.path.isfile(abs_path):
        raise FileNotFoundError(abs_path)
    is_read_only = read_only
    if read_only and spawn_inline_writes_enabled():
        try:
            gw = resolve_env_duckdb_path(get_gateway_db_path())
            if Path(abs_path).resolve() == Path(gw).resolve():
                is_read_only = False
        except OSError:
            pass
    return DuckClaw(abs_path, read_only=is_read_only, engine="python")


@router.get("/playground/config", dependencies=[Depends(require_admin_key)])
async def playground_config(
    request: Request,
    telegram_user_id: str | None = Query(None, description="ID Telegram (default: DUCKCLAW_OWNER_ID)"),
    tenant_id: str | None = Query(None, description="Tenant para whitelist y equipo"),
    chat_id: str | None = Query(
        None,
        description="Chat id para team_templates (default: mismo que telegram_user_id)",
    ),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import (
        list_projects_with_agents_for_actor,
        open_gateway_db,
        playground_workers_for_actor,
    )
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    profile: dict[str, Any] = {
        "email": actor,
        "tenant_id": _gateway_effective_tenant_id("default"),
        "telegram_user_id": "",
    }
    workers_list: list[dict[str, str]] = [{"id": "default", "label": "Default"}]
    projects: list[dict[str, Any]] = []
    try:
        with open_gateway_db(read_only=True) as db:
            profile = ensure_profile_for_user(db, email=actor)
            workers_list = playground_workers_for_actor(db, actor_email=actor)
            projects = list_projects_with_agents_for_actor(db, actor_email=actor)
    except FileNotFoundError:
        pass
    team_ctx = _playground_team_context(
        telegram_user_id=profile.get("telegram_user_id") or telegram_user_id,
        tenant_id=profile.get("tenant_id"),
        chat_id=chat_id,
    )
    console_actor = (request.headers.get("x-duckclaw-actor") or "").strip()
    if console_actor and console_actor.lower() not in ("admin-ui", ""):
        team_ctx["authorized"] = True
        if not team_ctx.get("whitelist_role"):
            team_ctx["whitelist_role"] = "admin-console"
    workers_list = _merge_playground_catalog_and_team_workers(workers_list, team_ctx)
    workers_payload = {"workers": workers_list, "workers_invalid": [], "team_hint_extra": ""}
    eff_chat = (chat_id or team_ctx.get("team_chat_id") or "admin-playground").strip()
    eff_tenant = str(profile.get("tenant_id") or "").strip() or _gateway_effective_tenant_id("default")
    runtime_defaults = _playground_runtime_defaults(eff_tenant, str(profile.get("email") or actor))
    llm = _resolved_llm_for_playground(
        chat_id=eff_chat,
        tenant_id=eff_tenant,
        actor_email=str(profile.get("email") or actor),
    )
    catalog = _playground_llm_catalog(llm.get("provider", ""))
    team_hint = (team_ctx.get("team_hint") or "") + workers_payload.get("team_hint_extra", "")
    selected_worker_id = ""
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is not None and eff_chat:
        from core.admin_conversations import resolve_conversation_view

        _, conv_meta, _ = await resolve_conversation_view(redis_client, eff_tenant, eff_chat)
        if conv_meta is not None:
            selected_worker_id = (
                (conv_meta.preferred_worker_id or conv_meta.last_worker_id or "").strip()
            )
    if not selected_worker_id:
        runtime_worker = re.sub(r"[^a-zA-Z0-9_-]", "", runtime_defaults.get("default_worker_id", ""))
        visible_worker_ids = {str(item.get("id") or "").strip() for item in workers_payload["workers"]}
        if runtime_worker and runtime_worker in visible_worker_ids:
            selected_worker_id = runtime_worker
    default_wid = _pick_playground_worker(team_ctx, selected_worker_id or None)
    vault = await _resolved_vault_for_admin_chat(
        eff_chat,
        team_ctx,
        default_wid,
        request=request,
        runtime_default_vault=runtime_defaults.get("default_vault_db_path"),
    )
    vault_options = _playground_vault_options_for_team(team_ctx)
    voice = await _playground_voice_status()
    return {
        "llm": llm,
        "catalog": catalog,
        "config_chat_id": eff_chat,
        "workers": workers_payload["workers"],
        "workers_invalid": workers_payload["workers_invalid"],
        "env_path": str(_env_file()),
        "effective_tenant_id": eff_tenant,
        "telegram_user_id": (profile.get("telegram_user_id") or team_ctx.get("telegram_user_id") or ""),
        "team_chat_id": team_ctx.get("team_chat_id"),
        "projects": projects,
        "authorized": team_ctx.get("authorized"),
        "whitelist_role": team_ctx.get("whitelist_role"),
        "team_source": team_ctx.get("team_source"),
        "team_hint": team_hint.strip(),
        "vault": vault,
        "vault_options": vault_options,
        "selected_worker_id": selected_worker_id or default_wid,
        "voice": voice,
        "chat_endpoint": "/api/v1/admin/playground/chat",
        "chat_stream_endpoint": "/api/v1/admin/playground/chat",
        "chat_stream_hint": "POST con stream=true o Accept: text/event-stream",
        "note": (
            "Proveedor y bóveda DuckDB por conversación. "
            "Sin override de bóveda, usa vault activo del usuario o manifest del worker."
        ),
    }


@router.put("/playground/vault", dependencies=[Depends(require_admin_key)])
async def playground_set_vault(
    body: PlaygroundVaultBody,
    request: Request,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """Persiste bóveda DuckDB por conversación (admin UI)."""
    from core.admin_conversations import get_conversation_meta, patch_conversation_vault, upsert_conversation_meta
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    chat_id = body.chat_id.strip()
    tenant_id = _gateway_effective_tenant_id((body.tenant_id or "default").strip() or "default")
    try:
        with open_gateway_db(read_only=True) as db:
            profile = ensure_profile_for_user(db, email=actor)
            tenant_id = str(profile.get("tenant_id") or "").strip() or tenant_id
    except FileNotFoundError:
        pass
    raw_path = (body.vault_db_path or "").strip()
    if raw_path:
        from duckclaw.gateway_db import resolve_env_duckdb_path

        abs_path = resolve_env_duckdb_path(raw_path)
        if not os.path.isabs(abs_path):
            abs_path = str(_repo_root() / abs_path.lstrip("/"))
        if not os.path.isfile(abs_path):
            raise _problem(404, "Vault no encontrado", raw_path)
        stored = raw_path
    else:
        stored = ""

    redis_client = getattr(request.app.state, "redis", None)
    meta = await get_conversation_meta(redis_client, tenant_id, chat_id)
    if meta is None:
        await upsert_conversation_meta(
            redis_client,
            tenant_id=tenant_id,
            session_id=chat_id,
            title="",
            message_count=0,
        )
    meta = await patch_conversation_vault(redis_client, tenant_id, chat_id, stored or None)
    team_ctx = _playground_team_context(tenant_id=tenant_id, chat_id=chat_id)
    wid = _pick_playground_worker(team_ctx, None)
    vault = await _resolved_vault_for_admin_chat(chat_id, team_ctx, wid, request=request)
    if stored and (meta is None or vault.get("scope") != "chat"):
        from duckclaw.gateway_db import resolve_env_duckdb_path

        vault = {
            "effective_path": resolve_env_duckdb_path(stored),
            "scope": "chat",
            "override_path": stored,
            "default_path": vault.get("default_path"),
        }
    return {
        "ok": True,
        "chat_id": chat_id,
        "tenant_id": tenant_id,
        "vault_db_path": stored,
        "vault": vault,
    }


@router.put("/playground/worker", dependencies=[Depends(require_admin_key)])
async def playground_set_worker(
    body: PlaygroundWorkerBody,
    request: Request,
) -> dict[str, Any]:
    """Persiste worker preferido por conversación (admin UI)."""
    from core.admin_conversations import (
        get_conversation_meta,
        patch_conversation_worker,
        upsert_conversation_meta,
    )

    chat_id = body.chat_id.strip()
    tenant_id = _gateway_effective_tenant_id((body.tenant_id or "default").strip() or "default")
    worker_id = re.sub(r"[^a-zA-Z0-9_-]", "", (body.worker_id or "").strip())
    if not worker_id:
        raise _problem(400, "worker_id inválido", body.worker_id)

    redis_client = getattr(request.app.state, "redis", None)
    meta = await get_conversation_meta(redis_client, tenant_id, chat_id)
    if meta is None:
        await upsert_conversation_meta(
            redis_client,
            tenant_id=tenant_id,
            session_id=chat_id,
            title="",
            message_count=0,
            last_worker_id=worker_id,
        )
    meta = await patch_conversation_worker(redis_client, tenant_id, chat_id, worker_id)
    team_ctx = _playground_team_context(tenant_id=tenant_id, chat_id=chat_id)
    selected = (meta.preferred_worker_id if meta else worker_id) or worker_id
    return {
        "ok": True,
        "chat_id": chat_id,
        "tenant_id": tenant_id,
        "worker_id": worker_id,
        "selected_worker_id": selected,
        "effective_worker_id": _pick_playground_worker(team_ctx, selected),
    }


@router.put("/playground/model", dependencies=[Depends(require_admin_key)])
async def playground_set_model(
    body: PlaygroundModelBody,
    request: Request,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """Equivalente a `/model provider=…` para la consola admin."""
    prov = body.provider.strip().lower()
    if prov in ("or", "router"):
        prov = "openrouter"
    if prov not in _PROVIDERS:
        raise _problem(
            400,
            "Proveedor inválido",
            f"Válidos: {', '.join(_PROVIDERS)}",
        )
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(503, "Gateway DuckDB no disponible", "Configura DUCKCLAW_GATEWAY_DB_PATH")
    chat_id = body.chat_id.strip()
    if prov == "mlx":
        default_model = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
        default_base_url = mlx_openai_compatible_base_url()
    else:
        default_model = _DEFAULT_MODEL_BY_PROVIDER.get(prov, "")
        default_base_url = _DEFAULT_BASE_URL_BY_PROVIDER.get(prov, "")
    model_value = (body.model or "").strip() if body.model is not None else default_model
    base_url_value = (body.base_url or "").strip() if body.base_url is not None else default_base_url

    task_ids: list[str] = []
    for key, value in (
        ("llm_provider", prov),
        ("llm_model", model_value),
        ("llm_base_url", base_url_value),
    ):
        command = UpsertRuntimeSettingCommand(
            tenant_id="default",
            actor_email=runtime_session_actor(chat_id),
            domain=RUNTIME_SESSION_DOMAIN,
            key=key,
            value=str(value or "")[:8192],
            value_kind="string",
            updated_by=actor,
        )
        try:
            task_id = db_write_queue.enqueue_typed_command(command, db_path=gw, user_id="default")
            command_status = db_write_queue.poll_task_status_sync(task_id, timeout_sec=0.5)
        except Exception as exc:
            raise _problem(400, "No se pudo actualizar el modelo", str(exc)) from exc
        if command_status and command_status.status == "failed":
            raise _problem(
                400,
                "No se pudo actualizar el modelo",
                command_status.detail or "runtime setting write failed",
            )
        task_ids.append(task_id)

    llm = _resolved_llm_for_chat(chat_id)
    return {
        "ok": True,
        "queued": True,
        "task_id": task_ids[0] if task_ids else "",
        "task_ids": task_ids,
        "message": "✅ Modelo actualizado. Los próximos mensajes usarán esta config.",
        "chat_id": chat_id,
        "llm": llm,
        "catalog": _playground_llm_catalog(llm.get("provider", "")),
    }


def _project_context_message(
    *,
    msg: str,
    project_context: dict[str, Any],
    worker_id: str,
    tenant_id: str,
    project_id: str,
) -> tuple[str, int]:
    from core.admin_identity import open_gateway_db

    agent_ids = [
        str(agent.get("worker_id") or "").strip()
        for agent in project_context.get("agents", [])
        if str(agent.get("worker_id") or "").strip()
    ]
    worker_uid = next(
        (
            str(agent.get("worker_uid") or "").strip()
            for agent in project_context.get("agents", [])
            if str(agent.get("worker_id") or "").strip() == worker_id
        ),
        "",
    )
    knowledge_blocks: list[str] = []
    rag_context_count = 0
    try:
        from duckclaw.forge.rag.context_provider import build_knowledge_context

        with open_gateway_db(read_only=True) as db:
            knowledge_context = build_knowledge_context(
                db,
                query=msg,
                tenant_id=tenant_id,
                project_id=project_id,
                worker_uid=worker_uid,
            )
        rag_context_count = knowledge_context.context_count
        if knowledge_context.inventory_block:
            knowledge_blocks.append(knowledge_context.inventory_block)
        if knowledge_context.rag_block:
            knowledge_blocks.append(knowledge_context.rag_block)
    except Exception:
        rag_context_count = 0
        knowledge_blocks = []
    project_block = "\n".join(
        [
            "[PROJECT_CONTEXT]",
            f"Nombre: {project_context.get('name') or ''}",
            f"Descripción: {project_context.get('description') or ''}",
            f"Agentes activos: {', '.join(agent_ids) if agent_ids else 'ninguno'}",
            "Usa el conocimiento recuperado para responder la pregunta del usuario antes de hablar de configuración interna.",
            "Usa esta descripción solo para orientar al usuario, proponer próximos pasos y pedir datos faltantes.",
            "[/PROJECT_CONTEXT]",
        ]
    )
    return "\n\n".join([project_block, *knowledge_blocks, msg]), rag_context_count


@router.post("/playground/chat", dependencies=[Depends(require_admin_key)])
async def playground_chat(
    body: PlaygroundChatBody,
    request: Request,
    actor: str = Depends(actor_from_header),
):
    """Chat de prueba desde consola admin (exento Tailscale vía prefijo /admin/)."""
    from core.admin_identity import (
        get_visible_worker_for_actor,
        open_gateway_db,
        project_context_for_actor,
        resolve_playground_worker_for_project,
    )
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    project_id = (body.project_id or "").strip()
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", body.worker_id.strip()) or "default"
    profile: dict[str, Any] = {
        "email": actor,
        "tenant_id": _gateway_effective_tenant_id("default"),
        "telegram_user_id": "",
    }
    catalog_allowed = False
    project_context: dict[str, Any] | None = None
    try:
        with open_gateway_db(read_only=True) as db:
            profile = ensure_profile_for_user(db, email=actor)
            if wid == "default" or get_visible_worker_for_actor(db, actor_email=actor, worker_id=wid):
                catalog_allowed = True
                try:
                    wid, project_id = resolve_playground_worker_for_project(
                        db,
                        actor_email=actor,
                        project_id=project_id,
                        worker_id=wid,
                    )
                    if project_id:
                        project_context = project_context_for_actor(
                            db,
                            actor_email=actor,
                            project_id=project_id,
                        )
                except PermissionError as exc:
                    raise _problem(403, str(exc), wid) from exc
    except FileNotFoundError:
        pass
    msg = (body.message or "").strip()
    original_user_message = msg
    if not msg and not body.images:
        raise _problem(400, "message o images requeridos", "")
    eff_tenant = str(profile.get("tenant_id") or "").strip() or _gateway_effective_tenant_id("default")
    if body.images:
        from core.comfyui_inbound import ingest_admin_visual_edit_inbound, should_route_comfyui_edit
        from core.vlm_ingest import decode_admin_image_b64, enrich_message_with_admin_images

        if should_route_comfyui_edit(has_visual=True, caption=msg):
            first_image = body.images[0]
            try:
                msg = ingest_admin_visual_edit_inbound(
                    image_bytes=decode_admin_image_b64(first_image.data_base64),
                    caption=msg,
                    tenant_id=eff_tenant,
                    mime_type=first_image.mime_type,
                )
            except ValueError as exc:
                raise _problem(400, str(exc), "images") from exc
            except Exception as exc:
                raise _problem(502, "Error preparando imagen para edición", str(exc)) from exc
        else:
            try:
                msg = await enrich_message_with_admin_images(
                    msg,
                    [img.model_dump() for img in body.images],
                )
            except ValueError as exc:
                raise _problem(400, str(exc), "images") from exc
            except Exception as exc:
                raise _problem(502, "Error procesando imagen (VLM)", str(exc)) from exc
    if not msg:
        raise _problem(400, "message vacío tras VLM", body.message)
    team_ctx = _playground_team_context(
        telegram_user_id=profile.get("telegram_user_id") or body.telegram_user_id,
        tenant_id=eff_tenant,
        chat_id=body.chat_id,
    )
    console_actor = (request.headers.get("x-duckclaw-actor") or "").strip()
    db_first_console = bool(
        (actor or "").strip().lower() not in ("", "admin-ui")
        or (console_actor and console_actor.lower() not in ("admin-ui", ""))
    )
    explicit_team = _playground_worker_explicitly_in_team(team_ctx, wid)
    team_allowed = _playground_worker_allowed_in_team(team_ctx, wid)
    if wid != "default" and not catalog_allowed:
        raise _problem(403, "Worker no asignado al catálogo del actor", wid)
    if not catalog_allowed:
        if db_first_console:
            if (team_ctx.get("team_source") or "") == "all":
                raise _problem(403, "Worker no asignado al catálogo del actor", wid)
            if not explicit_team:
                raise _problem(403, "Worker no asignado al catálogo del actor", wid)
        elif not team_allowed:
            raise _problem(403, "Worker no asignado al catálogo del actor", wid)
    session_id = (body.chat_id or "admin-playground").strip() or "admin-playground"
    if body.images:
        _admin_audit(
            "playground.chat.images",
            session_id,
            f"count={len(body.images)}",
            actor=actor,
        )
    owner_uid = str(team_ctx.get("telegram_user_id") or "").strip()
    guard_user_id = owner_uid or (actor or "admin-ui")

    from core.models import ChatRequest

    vault_info = await _resolved_vault_for_admin_chat(
        session_id,
        team_ctx,
        wid,
        body_override=(body.vault_db_path or "").strip() or None,
        request=request,
    )
    vault_path = vault_info.get("effective_path") or ""
    rag_context_count = 0
    if project_context:
        msg, rag_context_count = _project_context_message(
            msg=msg,
            project_context=project_context,
            worker_id=wid,
            tenant_id=eff_tenant,
            project_id=project_id,
        )

    chat = ChatRequest(
        message=msg,
        user_incoming=original_user_message or None,
        chat_id=session_id,
        user_id=guard_user_id,
        username=actor or guard_user_id,
        chat_type="private",
        tenant_id=eff_tenant,
        stream=body.stream,
        vault_db_path=vault_path or None,
    )
    redis_client = getattr(request.app.state, "redis", None)
    accept = (request.headers.get("accept") or "").lower()
    wants_stream = bool(body.stream) or "text/event-stream" in accept

    import main as gateway_main
    from duckclaw.channels import GatewayDeliveryContext

    delivery_context = GatewayDeliveryContext.trusted_admin_console()

    if wants_stream:
        from core.sse_stream import SSE_HEADERS

        return StreamingResponse(
            gateway_main._invoke_chat_sse_body(
                chat,
                wid,
                session_id,
                eff_tenant,
                redis_client=redis_client,
                delivery_context=delivery_context,
                http_request=request,
                voice_response=bool(body.voice_response),
            ),
            media_type="text/event-stream",
            headers=dict(SSE_HEADERS),
        )

    try:
        result = await gateway_main._invoke_chat(
            chat,
            wid,
            session_id=session_id,
            tenant_id=eff_tenant,
            redis_client=redis_client,
            delivery_context=delivery_context,
        )
    except Exception as exc:
        raise _problem(500, "Error en playground chat", str(exc)) from exc

    if isinstance(result, dict):
        visual = gateway_main._admin_visual_fields_from_invoke_result(
            session_id, result, eff_tenant
        )
        payload: dict[str, Any] = {
            "ok": True,
            "worker_id": wid,
            "project_id": project_id or None,
            "response": str(result.get("response") or result.get("reply") or ""),
            "assigned_worker_id": result.get("assigned_worker_id"),
            "usage_tokens": result.get("usage_tokens"),
            "rag_context_count": rag_context_count,
        }
        if visual:
            payload.update(visual)
        return payload
    return {"ok": True, "worker_id": wid, "response": str(result or "")}


@router.post("/playground/voice", dependencies=[Depends(require_admin_key)])
async def playground_voice(
    body: PlaygroundVoiceBody,
    request: Request,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    """
    Round-trip voz: transcribe en Mac mini → invoke agente → opcional TTS de vuelta.
    No usa streaming de audio (Whisper/OmniVoice son inferencia batch).
    """
    import base64

    from core.sensory_client import (
        SensoryUnavailable,
        resolve_voice_id_for_worker,
        sensory_enabled,
        synthesize_text,
    )
    from core.stt_ingest import SensoryUnavailable as SttDown, process_audio_bytes

    if not sensory_enabled():
        raise _problem(503, "DUCKCLAW_SENSORY_BASE_URL no configurado", "sensory")

    try:
        audio_bytes = base64.b64decode((body.audio_base64 or "").strip(), validate=False)
    except Exception as exc:
        raise _problem(400, "audio_base64 inválido", str(exc)) from exc
    if not audio_bytes:
        raise _problem(400, "audio vacío", "")

    t_stt = time.perf_counter()
    try:
        msg, stt_meta = await process_audio_bytes(
            audio_bytes,
            caption="",
            language_hint=body.language_hint,
        )
    except SttDown as exc:
        raise _problem(503, "STT no disponible", str(exc)) from exc
    finally:
        del audio_bytes
    stt_ms = (time.perf_counter() - t_stt) * 1000.0
    transcription = ""
    if "<audio_transcription>" in msg:
        match = re.search(r"<audio_transcription>(.*?)</audio_transcription>", msg, re.DOTALL)
        if match:
            transcription = (match.group(1) or "").strip()

    from core.admin_identity import (
        get_visible_worker_for_actor,
        open_gateway_db,
        project_context_for_actor,
        resolve_playground_worker_for_project,
    )
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    project_id = (body.project_id or "").strip()
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", body.worker_id.strip()) or "default"
    profile: dict[str, Any] = {
        "email": actor,
        "tenant_id": _gateway_effective_tenant_id("default"),
        "telegram_user_id": "",
    }
    catalog_allowed = False
    project_context: dict[str, Any] | None = None
    try:
        with open_gateway_db(read_only=True) as db:
            profile = ensure_profile_for_user(db, email=actor)
            if wid == "default" or get_visible_worker_for_actor(db, actor_email=actor, worker_id=wid):
                catalog_allowed = True
                try:
                    wid, project_id = resolve_playground_worker_for_project(
                        db,
                        actor_email=actor,
                        project_id=project_id,
                        worker_id=wid,
                    )
                    if project_id:
                        project_context = project_context_for_actor(
                            db,
                            actor_email=actor,
                            project_id=project_id,
                        )
                except PermissionError as exc:
                    raise _problem(403, str(exc), wid) from exc
    except FileNotFoundError:
        pass

    eff_tenant = str(profile.get("tenant_id") or "").strip() or _gateway_effective_tenant_id("default")
    team_ctx = _playground_team_context(tenant_id=eff_tenant, chat_id=body.chat_id)
    if wid != "default" and not catalog_allowed:
        raise _problem(403, "Worker no asignado al catálogo del actor", wid)

    session_id = (body.chat_id or "admin-playground").strip() or "admin-playground"
    owner_uid = str(team_ctx.get("telegram_user_id") or "").strip()
    guard_user_id = owner_uid or (actor or "admin-ui")

    from core.models import ChatRequest

    vault_info = await _resolved_vault_for_admin_chat(session_id, team_ctx, wid, request=request)
    vault_path = vault_info.get("effective_path") or ""
    if project_context:
        msg, _ = _project_context_message(
            msg=msg,
            project_context=project_context,
            worker_id=wid,
            tenant_id=eff_tenant,
            project_id=project_id,
        )

    chat = ChatRequest(
        message=msg,
        chat_id=session_id,
        user_id=guard_user_id,
        username=actor or guard_user_id,
        chat_type="private",
        tenant_id=eff_tenant,
        stream=False,
        vault_db_path=vault_path or None,
    )
    redis_client = getattr(request.app.state, "redis", None)
    import main as gateway_main
    from duckclaw.channels import GatewayDeliveryContext

    delivery_context = GatewayDeliveryContext.trusted_admin_console()
    try:
        result = await gateway_main._invoke_chat(
            chat,
            wid,
            session_id=session_id,
            tenant_id=eff_tenant,
            redis_client=redis_client,
            delivery_context=delivery_context,
        )
    except Exception as exc:
        raise _problem(500, "Error en playground voice (agente)", str(exc)) from exc

    if isinstance(result, dict):
        reply = str(result.get("response") or result.get("reply") or "").strip()
    else:
        reply = str(result or "").strip()

    audio_b64_out: str | None = None
    audio_format_out: str | None = None
    audio_unavailable = False
    tts_ms: float | None = None
    if body.voice_response and reply:
        t_tts = time.perf_counter()
        try:
            voice_id = resolve_voice_id_for_worker(wid)
            tts_result = await synthesize_text(reply, voice_id)
            audio_b64_out = tts_result.audio_base64
            audio_format_out = tts_result.audio_format
            tts_ms = (time.perf_counter() - t_tts) * 1000.0
            logging.getLogger("duckclaw.gateway.admin_tts").info(
                "voice_batch ok worker=%s format=%s b64_len=%s",
                wid,
                audio_format_out,
                len(audio_b64_out or ""),
            )
        except SensoryUnavailable:
            audio_unavailable = True

    payload: dict[str, Any] = {
        "ok": True,
        "worker_id": wid,
        "transcription": transcription,
        "response": reply,
        "audio_base64": audio_b64_out,
        "audio_format": audio_format_out,
        "audio_unavailable": audio_unavailable,
        "stt_processing_ms": stt_meta.get("processing_time_ms") if stt_meta else stt_ms,
        "tts_latency_ms": tts_ms,
        "streaming": {
            "audio_stt": "batch",
            "audio_tts": "batch",
            "agent_text_sse": "/api/v1/admin/playground/chat con stream=true",
        },
    }
    if isinstance(result, dict):
        visual = gateway_main._admin_visual_fields_from_invoke_result(session_id, result, eff_tenant)
        if visual:
            payload.update(visual)
    return payload


@router.post("/playground/chat/cancel", dependencies=[Depends(require_admin_key)])
async def playground_chat_cancel(body: PlaygroundChatCancelBody) -> dict[str, Any]:
    """Marca interrupción cooperativa para un chat admin en curso (Redis + grafo)."""
    session_id = (body.chat_id or "").strip()
    if not session_id:
        raise _problem(400, "chat_id vacío", body.chat_id)
    from duckclaw.graphs.chat_cancel import request_chat_cancel

    ok = request_chat_cancel(session_id)
    try:
        from duckclaw.forge.skills.comfyui_bridge import cancel_comfy_generation_for_chat

        cancel_comfy_generation_for_chat(session_id)
    except Exception:
        pass
    return {"ok": True, "chat_id": session_id, "cancelled": ok}


@router.get("/chats/history", dependencies=[Depends(require_admin_key)])
async def admin_chat_history(
    request: Request,
    tenant_id: str = Query("default"),
    session_id: str = Query(...),
) -> dict[str, Any]:
    from core.chat_history import redis_load_chat_history

    redis_client = getattr(request.app.state, "redis", None)
    items = await redis_load_chat_history(redis_client, tenant_id, session_id)
    return {"tenant_id": tenant_id, "session_id": session_id, "messages": items}


@router.get("/conversations", dependencies=[Depends(require_admin_key)])
async def admin_list_conversations(
    request: Request,
    tenant_id: str = Query("default"),
    section: str | None = Query(None),
    worker: str | None = Query(None),
    actor: str | None = Query(None),
    q: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
) -> dict[str, Any]:
    from core.admin_conversations import list_conversations_merged

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    redis_client = getattr(request.app.state, "redis", None)
    items, total = await list_conversations_merged(
        redis_client,
        tid,
        section=section,
        worker=worker,
        actor=actor,
        q=q,
        limit=limit,
        offset=offset,
    )
    return {
        "tenant_id": tid,
        "conversations": [m.model_dump() for m in items],
        "total": total,
        "limit": limit,
        "offset": offset,
    }


@router.post("/conversations", dependencies=[Depends(require_admin_key)])
async def admin_create_conversation(
    request: Request,
    body: AdminConversationCreateBody,
    tenant_id: str = Query("default"),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_conversations import (
        AdminConversationMeta,
        derive_section_from_session_id,
        new_admin_conversation_session_id,
        patch_conversation_worker,
        upsert_conversation_meta,
    )

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    sid = new_admin_conversation_session_id()
    sec = (body.section or "").strip() or "other"
    redis_client = getattr(request.app.state, "redis", None)
    title = (body.title or "").strip() or f"Conversación {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    init_worker = re.sub(r"[^a-zA-Z0-9_-]", "", (body.worker_id or "").strip())
    meta = await upsert_conversation_meta(
        redis_client,
        tenant_id=tid,
        session_id=sid,
        actor=actor,
        section=sec,
        last_worker_id=init_worker,
        title=title,
        message_count=0,
    )
    if meta is None:
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        meta = AdminConversationMeta(
            session_id=sid,
            tenant_id=tid,
            title=title,
            created_at=now,
            updated_at=now,
            actor=actor,
            section=derive_section_from_session_id(sid, origin_section=sec),
            last_worker_id=init_worker,
            preferred_worker_id=init_worker,
            workers=[init_worker] if init_worker else [],
            origin="admin_ui",
        )
    elif init_worker:
        patched = await patch_conversation_worker(redis_client, tid, sid, init_worker)
        if patched is not None:
            meta = patched
    return meta.model_dump()


@router.get("/conversations/{session_id}", dependencies=[Depends(require_admin_key)])
async def admin_get_conversation(
    request: Request,
    session_id: str,
    tenant_id: str = Query("default"),
) -> dict[str, Any]:
    from core.admin_conversations import resolve_conversation_view

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    sid = (session_id or "").strip()
    if not sid:
        raise _problem(400, "session_id vacío", session_id)
    redis_client = getattr(request.app.state, "redis", None)
    resolved_tid, meta, messages = await resolve_conversation_view(redis_client, tid, sid)
    if meta is None and not messages:
        raise _problem(404, "Conversación no encontrada", sid)
    out: dict[str, Any] = {
        "tenant_id": resolved_tid,
        "session_id": sid,
        "messages": messages,
    }
    if meta is not None:
        out.update(meta.model_dump())
    return out


@router.patch("/conversations/{session_id}", dependencies=[Depends(require_admin_key)])
async def admin_patch_conversation(
    request: Request,
    session_id: str,
    body: AdminConversationPatchBody,
    tenant_id: str = Query("default"),
) -> dict[str, Any]:
    from core.admin_conversations import patch_conversation_title

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    sid = (session_id or "").strip()
    title = (body.title or "").strip()
    if not sid or not title:
        raise _problem(400, "session_id y title requeridos", sid)
    redis_client = getattr(request.app.state, "redis", None)
    meta = await patch_conversation_title(redis_client, tid, sid, title)
    if meta is None:
        raise _problem(404, "Conversación no encontrada", sid)
    return meta.model_dump()


@router.delete("/conversations/{session_id}", dependencies=[Depends(require_admin_key)])
async def admin_delete_conversation(
    request: Request,
    session_id: str,
    tenant_id: str = Query("default"),
) -> dict[str, Any]:
    from core.admin_conversations import delete_conversation_merged

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    sid = (session_id or "").strip()
    if not sid:
        raise _problem(400, "session_id vacío", session_id)
    redis_client = getattr(request.app.state, "redis", None)
    deleted_tid = await delete_conversation_merged(redis_client, tid, sid)
    if deleted_tid is None:
        raise _problem(404, "Conversación no encontrada", sid)
    return {"ok": True, "hard_deleted": True, "session_id": sid, "tenant_id": deleted_tid}


@router.post("/conversations/reindex", dependencies=[Depends(require_admin_key)])
async def admin_reindex_conversations(
    request: Request,
    tenant_id: str = Query("default"),
) -> dict[str, Any]:
    from core.admin_conversations import reindex_admin_conversations

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    redis_client = getattr(request.app.state, "redis", None)
    stats = await reindex_admin_conversations(redis_client, tid)
    return {"tenant_id": tid, **stats}
