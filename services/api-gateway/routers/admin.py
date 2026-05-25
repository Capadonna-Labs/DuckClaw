"""
Admin API — consola DuckClaw (spec: specs/features/platform/DUCKCLAW_ADMIN_UI.md).

CRUD plantillas en disco, .env enmascarado, runtime agent_config, whitelist Telegram, historial Redis.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_EDITABLE_SUFFIXES = frozenset({".yaml", ".yml", ".md", ".sql", ".py", ".txt", ".json"})
_PROTECTED_TEMPLATE_IDS = frozenset({"entry_router", "manager_router"})
_CATALOG_STARTER_SKIP = frozenset({"entry_router", "manager_router", "industries"})
_ENV_ALLOW_PREFIXES = ("TELEGRAM_", "DUCKDB_", "DUCKCLAW_", "LANGCHAIN_", "OPENAI_", "GROQ_", "DEEPSEEK_")
_ENV_ALLOW_EXACT = frozenset({"LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "REDIS_URL"})


def _repo_root() -> Path:
    raw = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    return Path(raw) if raw else _REPO_ROOT


def _gateway_effective_tenant_id(request_tenant: str | None) -> str:
    """Misma resolución que ``main._effective_tenant_id`` (p. ej. default → Marco si está en PM2)."""
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
    from duckclaw.graphs.on_the_fly_commands import (
        _get_authorized_role,
        _is_gateway_owner_user,
        get_effective_team_templates,
        get_team_templates,
        get_tenant_team_templates,
    )

    from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

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


def _playground_workers_payload(raw_workers: list[str]) -> dict[str, Any]:
    """Normaliza equipo Playground: ids canónicos en disco + etiquetas de manifest."""
    from duckclaw.workers.manifest import load_manifest
    from duckclaw.workers.template_registry import list_template_ids, resolve_template_id

    all_ids = list_template_ids()
    source = raw_workers if raw_workers else all_ids
    seen: set[str] = set()
    workers: list[dict[str, str]] = []
    invalid: list[str] = []

    for raw in source:
        w = (raw or "").strip()
        if not w:
            continue
        canonical = resolve_template_id(all_ids, w)
        if not canonical or canonical not in all_ids:
            invalid.append(w)
            continue
        if canonical in seen:
            continue
        seen.add(canonical)
        label = canonical
        try:
            spec = load_manifest(canonical)
            label = (getattr(spec, "display_name", None) or spec.name or canonical).strip()
        except Exception:
            pass
        workers.append({"id": canonical, "label": label})

    team_hint_extra = ""
    if invalid:
        team_hint_extra = (
            f" Templates no encontrados en disco (omitidos del selector): {', '.join(invalid)}."
        )

    return {
        "workers": workers,
        "workers_invalid": invalid,
        "team_hint_extra": team_hint_extra,
    }


def _list_whitelist_users_merged(db: Any, *, tenant_id: str) -> list[dict[str, str]]:
    from duckclaw.graphs.on_the_fly_commands import (
        _dedupe_authorized_users_by_user_id,
        _list_authorized_users,
    )

    tid = (tenant_id or "default").strip() or "default"
    users = _list_authorized_users(db, tenant_id=tid)
    if tid.lower() != "default":
        legacy = _list_authorized_users(db, tenant_id="default")
        if legacy:
            users = _dedupe_authorized_users_by_user_id(users + legacy)
    return users


async def _invalidate_whitelist_cache(
    request: Request,
    *,
    tenant_id: str,
    user_id: str,
) -> None:
    from duckclaw.graphs.on_the_fly_commands import _invalidate_whitelist_redis_cache

    _invalidate_whitelist_redis_cache(tenant_id=tenant_id, user_id=user_id)
    redis_client = getattr(request.app.state, "redis", None)
    if redis_client is None:
        return
    tid = str(tenant_id or "default").strip().lower() or "default"
    uid = str(user_id or "").strip()
    if not uid:
        return
    key = f"whitelist:{tid}:{uid}"
    try:
        await redis_client.delete(key)
    except Exception:
        pass


def _env_file() -> Path:
    return _repo_root() / ".env"


def _read_env_key_unmasked(key: str) -> str:
    env_path = _env_file()
    if not env_path.is_file():
        return ""
    want = (key or "").strip()
    for line in env_path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        if k.strip() == want:
            return v.strip().strip("'\"")
    return ""


def _merge_env_lines(values: dict[str, str]) -> tuple[Path, list[str]]:
    """Actualiza .env en disco; retorna (backup_path, claves_actualizadas)."""
    env_path = _env_file()
    if not env_path.is_file():
        raise _problem(404, ".env no encontrado", str(env_path))
    backup = env_path.with_suffix(".env.bak")
    shutil.copy2(env_path, backup)
    lines = env_path.read_text(encoding="utf-8").splitlines(keepends=True)
    key_to_idx: dict[str, int] = {}
    for i, raw in enumerate(lines):
        s = raw.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        key_to_idx[s.split("=", 1)[0].strip()] = i
    updated: list[str] = []
    for k, v in values.items():
        if not _is_env_key_allowed(k):
            raise _problem(400, "Clave no permitida", k)
        line = f"{k}={v}\n"
        if k in key_to_idx:
            lines[key_to_idx[k]] = line
        else:
            lines.append(line)
        updated.append(k)
    env_path.write_text("".join(lines), encoding="utf-8")
    for k, v in values.items():
        os.environ[k] = v
    return backup, updated


def _templates_dir() -> Path:
    from duckclaw.forge import WORKERS_TEMPLATES_DIR

    return WORKERS_TEMPLATES_DIR


def _projects_dir() -> Path:
    from duckclaw.forge import PROJECTS_DIR

    PROJECTS_DIR.mkdir(parents=True, exist_ok=True)
    return PROJECTS_DIR


def _safe_project_slug(slug: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9_-]", "", (slug or "").strip())
    if not s:
        raise _problem(400, "slug inválido", slug or "")
    return s


def _read_project_yaml(path: Path) -> dict[str, Any]:
    import yaml

    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return data if isinstance(data, dict) else {}


def _write_project_yaml(path: Path, data: dict[str, Any]) -> None:
    import yaml

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
        encoding="utf-8",
    )


def _canonicalize_project_members(members: list[str]) -> list[str]:
    from duckclaw.workers.template_registry import list_template_ids, resolve_template_id

    all_ids = list_template_ids()
    out: list[str] = []
    seen: set[str] = set()
    for raw in members:
        w = str(raw or "").strip()
        if not w:
            continue
        canonical = resolve_template_id(all_ids, w) or w
        if canonical not in all_ids or canonical in seen:
            continue
        seen.add(canonical)
        out.append(canonical)
    return out


def _list_forge_projects() -> list[dict[str, Any]]:
    from duckclaw.forge.team_env import load_team_from_env

    root = _projects_dir()
    by_slug: dict[str, dict[str, Any]] = {}
    env_row = load_team_from_env()
    if env_row:
        env_row = dict(env_row)
    for env_row in [env_row] if env_row else []:
        sid = str(env_row.get("slug") or env_row.get("id") or "").strip()
        if not sid:
            continue
        members = _canonicalize_project_members(list(env_row.get("members") or []))
        if not members:
            continue
        by_slug[sid] = {
            "id": sid,
            "slug": sid,
            "display_name": str(env_row.get("display_name") or sid),
            "coordinator": env_row.get("coordinator"),
            "members": members,
            "shared_vault_id": env_row.get("shared_vault_id"),
            "source": "env",
            "path": f"forge/projects/{sid}",
        }
    if root.is_dir():
        for d in sorted(root.iterdir()):
            if not d.is_dir() or d.name.startswith((".", "_")):
                continue
            manifest = d / "project.yaml"
            if not manifest.is_file():
                continue
            data = _read_project_yaml(manifest)
            pid = str(data.get("id") or d.name).strip()
            members_raw = data.get("members")
            member_list = (
                _canonicalize_project_members(members_raw)
                if isinstance(members_raw, list)
                else []
            )
            by_slug[d.name] = {
                "id": pid,
                "slug": d.name,
                "display_name": str(data.get("display_name") or pid),
                "coordinator": data.get("coordinator"),
                "members": member_list,
                "shared_vault_id": data.get("shared_vault_id"),
                "source": "disk",
                "path": str(d.relative_to(_repo_root())),
            }
    return sorted(by_slug.values(), key=lambda x: str(x.get("slug") or ""))


def _require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    expected = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DUCKCLAW_ADMIN_API_KEY no configurada en el gateway",
        )
    if (x_admin_key or "").strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin key inválida")


def _problem(status_code: int, title: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"type": "about:blank", "title": title, "status": status_code, "detail": detail},
    )


def _mask_secret(value: str) -> str:
    v = (value or "").strip()
    if len(v) <= 4:
        return "****" if v else ""
    return f"{v[:4]}…{'*' * min(12, max(4, len(v) - 4))}"


def _is_env_key_allowed(key: str) -> bool:
    k = (key or "").strip()
    if not k or k.startswith("#"):
        return False
    if k in _ENV_ALLOW_EXACT:
        return True
    return any(k.startswith(p) for p in _ENV_ALLOW_PREFIXES)


def _safe_worker_path(worker_id: str, rel_path: str) -> Path:
    wid = (worker_id or "").strip()
    if not wid or ".." in wid or "/" in wid or "\\" in wid:
        raise _problem(400, "worker_id inválido", wid)
    base = (_templates_dir() / wid).resolve()
    if not base.is_dir():
        raise _problem(404, "Plantilla no encontrada", wid)
    rel = (rel_path or "").strip().lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise _problem(400, "Ruta de archivo inválida", rel_path)
    target = (base / rel).resolve()
    if not str(target).startswith(str(base)):
        raise _problem(400, "Ruta fuera del worker", rel_path)
    if target.suffix.lower() not in _EDITABLE_SUFFIXES and not target.is_dir():
        raise _problem(400, "Extensión no editable", target.suffix)
    return target


def _list_template_files(worker_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for p in sorted(worker_dir.rglob("*")):
        if p.is_file() and p.name.startswith("."):
            continue
        if p.is_file():
            rel = str(p.relative_to(worker_dir)).replace("\\", "/")
            out.append({"path": rel, "size": p.stat().st_size})
    return out


class FileWriteBody(BaseModel):
    content: str = ""


class VaultBindingPutBody(BaseModel):
    scope: str = Field(default="", description="private | shared; vacío = quitar binding")
    vault_id: str | None = Field(default=None, max_length=128)
    path: str | None = Field(default=None, max_length=512)


class TemplateCreateBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    source_template: str = Field(default="industries/business_standard")


class ProjectCreateBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    source_template: str = Field(
        default="default",
        description="Preset de habilidades (id de plantilla opcional). El disco siempre clona desde templates/default.",
    )
    name: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    topology: str = "general"
    system_prompt: str = ""
    soul: str = ""


class ForgeProjectCreateBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=48)
    display_name: str = Field(default="", max_length=128)
    members: list[str] = Field(default_factory=list)
    coordinator: str | None = Field(default=None, max_length=64)
    shared_vault_id: str | None = Field(default=None, max_length=64)
    shared_context: str = Field(default="", max_length=32_000)
    apply_tenant_team: bool = Field(default=False)
    tenant_id: str = Field(default="default", max_length=64)


class ForgeProjectPatchBody(BaseModel):
    display_name: str | None = Field(default=None, max_length=128)
    members: list[str] | None = None
    coordinator: str | None = Field(default=None, max_length=64)
    shared_vault_id: str | None = Field(default=None, max_length=64)
    shared_context: str | None = Field(default=None, max_length=32_000)


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


class PlaygroundChatBody(BaseModel):
    worker_id: str = Field(default="default", max_length=64)
    message: str = Field(default="", max_length=16000)
    chat_id: str = Field(default="admin-playground", max_length=128)
    tenant_id: str = Field(default="default", max_length=64)
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

    @model_validator(mode="after")
    def _message_or_images(self) -> "PlaygroundChatBody":
        if not (self.message or "").strip() and not self.images:
            raise ValueError("message o images requeridos")
        return self


class EnvPatchBody(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class NovncPrepareBody(BaseModel):
    chat_id: str | None = Field(default=None, max_length=128)
    worker_id: str | None = Field(default=None, max_length=64)
    tenant_id: str | None = Field(default=None, max_length=64)


class SandboxNetworkBody(BaseModel):
    chat_id: str = Field(..., min_length=1, max_length=128)
    enabled: bool
    worker_id: str | None = Field(default=None, max_length=64)
    tenant_id: str | None = Field(default=None, max_length=64)


class TelegramRouteInput(BaseModel):
    bot: str = Field(..., min_length=1, max_length=64)
    path: str = Field(..., min_length=8, max_length=256)
    worker_id: str = Field(..., min_length=1, max_length=64)
    tenant_id: str = Field(..., min_length=1, max_length=64)
    vault_env_var: str | None = Field(
        default=None,
        max_length=128,
        description="Nombre de variable .env con ruta DuckDB (opcional)",
    )
    token: str | None = Field(
        default=None,
        max_length=512,
        description="Vacío = conservar token actual en .env",
    )


class TelegramRoutesPutBody(BaseModel):
    routes: list[TelegramRouteInput] = Field(default_factory=list)


class RuntimeConfigPutBody(BaseModel):
    vault_path: str
    chat_id: str = "default"
    key: str
    value: str


class WhitelistBody(BaseModel):
    user_id: str
    username: str = ""
    role: str = "user"
    tenant_id: str = ""


class AdminLoginBody(BaseModel):
    email: str
    password: str


class ConsoleUserBody(BaseModel):
    email: str
    nombre: str = ""
    rol: str = "viewer"
    password: str | None = None
    initials: str = ""
    active: bool = True


class ConsoleUserPatchBody(BaseModel):
    nombre: str | None = None
    rol: str | None = None
    password: str | None = None
    initials: str | None = None
    active: bool | None = None


class SharedGrantBody(BaseModel):
    tenant_id: str = "default"
    user_id: str
    resource_key: str


_AGENT_CONFIG_DDL = """
CREATE TABLE IF NOT EXISTS agent_config (
    key VARCHAR PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _audit_log_path() -> Path:
    p = _repo_root() / ".duckclaw" / "admin-audit.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


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


def _actor_from_header(x_actor: str | None = Header(None, alias="X-Duckclaw-Actor")) -> str:
    return (x_actor or "admin-ui").strip()[:128] or "admin-ui"


def _chat_config_prefix(chat_id: str) -> str:
    cid = (chat_id or "default").strip() or "default"
    try:
        int(cid)
        return f"chat_{cid}_"
    except ValueError:
        return f"chat_{cid[:64]}_"


def _full_agent_config_key(chat_id: str, key: str) -> str:
    k = (key or "").strip()
    if k.startswith("chat_"):
        return k[:256]
    return f"{_chat_config_prefix(chat_id)}{k}"[:256]


def _parse_agent_config_rows(raw: Any, chat_id: str) -> list[dict[str, str]]:
    rows = raw
    if isinstance(raw, str):
        rows = json.loads(raw) if raw.strip().startswith("[") else []
    if not isinstance(rows, list):
        return []
    prefix = _chat_config_prefix(chat_id)
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        full = str(row.get("key") or "")
        val = str(row.get("value") or "")
        if full.startswith(prefix):
            out.append({"key": full[len(prefix) :], "full_key": full, "value": val, "scope": "chat"})
        elif not full.startswith("chat_"):
            out.append({"key": full, "full_key": full, "value": val, "scope": "global"})
    return out


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
        "model_example": "anthropic/claude-sonnet-4-5",
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


def _resolved_llm_for_chat(chat_id: str | None) -> dict[str, str]:
    """LLM efectivo: override agent_config del chat (p. ej. /model) o .env del gateway."""
    env = _resolved_llm_env()
    cid = (chat_id or "").strip()
    if not cid:
        return {**env, "scope": "env"}
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.graphs.on_the_fly_commands import _effective_llm_triplet_for_chat_ui

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        return {**env, "scope": "env"}
    try:
        db = DuckClaw(gw, read_only=True, engine="python")
    except Exception:
        return {**env, "scope": "env", "db_lock_error": True}
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
        "scope": "chat" if has_chat else "env",
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
    for k in env_keys:
        if (os.environ.get(k) or "").strip():
            return True
    return len(env_keys) == 0


@router.get("/playground/config", dependencies=[Depends(_require_admin_key)])
async def playground_config(
    request: Request,
    telegram_user_id: str | None = Query(None, description="ID Telegram (default: DUCKCLAW_OWNER_ID)"),
    tenant_id: str | None = Query(None, description="Tenant para whitelist y equipo"),
    chat_id: str | None = Query(
        None,
        description="Chat id para team_templates (default: mismo que telegram_user_id)",
    ),
) -> dict[str, Any]:
    team_ctx = _playground_team_context(
        telegram_user_id=telegram_user_id,
        tenant_id=tenant_id,
        chat_id=chat_id,
    )
    raw_workers: list[str] = team_ctx.get("workers") or []
    workers_payload = _playground_workers_payload(raw_workers)
    eff_chat = (chat_id or team_ctx.get("team_chat_id") or "admin-playground").strip()
    llm = _resolved_llm_for_chat(eff_chat)
    catalog = _playground_llm_catalog(llm.get("provider", ""))
    eff_tenant = team_ctx.get("tenant_id") or _gateway_effective_tenant_id("default")
    team_hint = (team_ctx.get("team_hint") or "") + workers_payload.get("team_hint_extra", "")
    default_wid = _pick_playground_worker(team_ctx, None)
    vault = await _resolved_vault_for_admin_chat(
        eff_chat,
        team_ctx,
        default_wid,
        request=request,
    )
    vault_options = _playground_vault_options_for_team(team_ctx)
    return {
        "llm": llm,
        "catalog": catalog,
        "config_chat_id": eff_chat,
        "workers": workers_payload["workers"],
        "workers_invalid": workers_payload["workers_invalid"],
        "env_path": str(_env_file()),
        "effective_tenant_id": eff_tenant,
        "telegram_user_id": team_ctx.get("telegram_user_id"),
        "team_chat_id": team_ctx.get("team_chat_id"),
        "authorized": team_ctx.get("authorized"),
        "whitelist_role": team_ctx.get("whitelist_role"),
        "team_source": team_ctx.get("team_source"),
        "team_hint": team_hint.strip(),
        "vault": vault,
        "vault_options": vault_options,
        "chat_endpoint": "/api/v1/admin/playground/chat",
        "chat_stream_endpoint": "/api/v1/admin/playground/chat",
        "chat_stream_hint": "POST con stream=true o Accept: text/event-stream",
        "note": (
            "Proveedor y bóveda DuckDB por conversación. "
            "Sin override de bóveda, usa vault activo del usuario o manifest del worker."
        ),
    }


@router.put("/playground/vault", dependencies=[Depends(_require_admin_key)])
async def playground_set_vault(
    body: PlaygroundVaultBody,
    request: Request,
) -> dict[str, Any]:
    """Persiste bóveda DuckDB por conversación (admin UI)."""
    from core.admin_conversations import get_conversation_meta, patch_conversation_vault, upsert_conversation_meta

    chat_id = body.chat_id.strip()
    tenant_id = _gateway_effective_tenant_id((body.tenant_id or "default").strip() or "default")
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


def _duckdb_paths_same(a: str, b: str) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return (a or "").strip() == (b or "").strip()


@router.put("/playground/model", dependencies=[Depends(_require_admin_key)])
async def playground_set_model(body: PlaygroundModelBody, request: Request) -> dict[str, Any]:
    """Equivalente a `/model provider=…` para la consola admin (persiste en agent_config del chat)."""
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path, resolve_env_duckdb_path
    from duckclaw.graphs.on_the_fly_commands import _PROVIDERS, execute_model

    prov = body.provider.strip().lower()
    if prov not in _PROVIDERS:
        raise _problem(
            400,
            "Proveedor inválido",
            f"Válidos: {', '.join(_PROVIDERS)}",
        )
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(503, "Gateway DuckDB no disponible", "Configura DUCKCLAW_FINANZ_DB_PATH")
    parts = [f"provider={prov}"]
    if body.model and body.model.strip():
        parts.append(f"model={body.model.strip()}")
    if body.base_url is not None and str(body.base_url).strip():
        parts.append(f"base_url={body.base_url.strip()}")
    args = " | ".join(parts)
    chat_id = body.chat_id.strip()
    db = DuckClaw(gw, read_only=False, engine="python")
    try:
        message = execute_model(db, chat_id, args)
    except Exception as exc:
        raise _problem(400, "No se pudo actualizar el modelo", str(exc)) from exc
    finally:
        db.close()

    # Espejo en bóveda separada (Quant-Trader, etc.) para que llm_* no quede stale en openrouter.
    hub_abs = resolve_env_duckdb_path(gw)
    team_ctx = _playground_team_context(chat_id=chat_id)
    wid = _pick_playground_worker(team_ctx, None)
    vault_info = await _resolved_vault_for_admin_chat(chat_id, team_ctx, wid, request=request)
    vault_path = resolve_env_duckdb_path(str(vault_info.get("effective_path") or "").strip())
    if (
        vault_path
        and os.path.isfile(vault_path)
        and not _duckdb_paths_same(vault_path, hub_abs)
    ):
        vault_db = DuckClaw(vault_path, read_only=False, engine="python")
        try:
            execute_model(vault_db, chat_id, args)
        except Exception as exc:
            _log = logging.getLogger(__name__)
            _log.warning(
                "playground_set_model: vault mirror failed chat_id=%s vault=%s err=%s",
                chat_id,
                vault_path[-96:] if len(vault_path) > 96 else vault_path,
                exc,
            )
        finally:
            vault_db.close()

    llm = _resolved_llm_for_chat(chat_id)
    return {
        "ok": True,
        "message": message,
        "chat_id": chat_id,
        "llm": llm,
        "catalog": _playground_llm_catalog(llm.get("provider", "")),
    }


@router.post("/playground/chat", dependencies=[Depends(_require_admin_key)])
async def playground_chat(
    body: PlaygroundChatBody,
    request: Request,
    actor: str = Depends(_actor_from_header),
):
    """Chat de prueba desde consola admin (exento Tailscale vía prefijo /admin/)."""
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", body.worker_id.strip()) or "default"
    msg = (body.message or "").strip()
    if not msg and not body.images:
        raise _problem(400, "message o images requeridos", "")
    if body.images:
        from core.vlm_ingest import enrich_message_with_admin_images

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
    tenant_id = _gateway_effective_tenant_id((body.tenant_id or "default").strip() or "default")
    team_ctx = _playground_team_context(
        telegram_user_id=body.telegram_user_id,
        tenant_id=tenant_id,
        chat_id=body.chat_id,
    )
    if not team_ctx.get("authorized"):
        raise _problem(
            403,
            "Usuario Telegram no autorizado para este tenant",
            str(team_ctx.get("team_hint") or ""),
        )
    allowed_workers: list[str] = team_ctx.get("workers") or []
    if allowed_workers and wid not in allowed_workers:
        from duckclaw.workers.template_registry import resolve_template_id

        canonical = resolve_template_id(allowed_workers, wid) or wid
        if canonical not in allowed_workers:
            raise _problem(
                403,
                "Worker fuera del equipo /workers",
                f"'{wid}' no está en el equipo efectivo: {', '.join(allowed_workers)}",
            )
        wid = canonical
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

    chat = ChatRequest(
        message=msg,
        chat_id=session_id,
        user_id=guard_user_id,
        username=actor or guard_user_id,
        chat_type="private",
        tenant_id=tenant_id,
        stream=body.stream,
        vault_db_path=vault_path or None,
    )
    redis_client = getattr(request.app.state, "redis", None)
    accept = (request.headers.get("accept") or "").lower()
    wants_stream = bool(body.stream) or "text/event-stream" in accept

    import main as gateway_main

    from duckclaw.channels import GatewayDeliveryContext

    delivery_context = GatewayDeliveryContext(channel="http")

    if wants_stream:
        from core.sse_stream import SSE_HEADERS

        return StreamingResponse(
            gateway_main._invoke_chat_sse_body(
                chat,
                wid,
                session_id,
                tenant_id,
                redis_client=redis_client,
                delivery_context=delivery_context,
            ),
            media_type="text/event-stream",
            headers=dict(SSE_HEADERS),
        )

    try:
        result = await gateway_main._invoke_chat(
            chat,
            wid,
            session_id=session_id,
            tenant_id=tenant_id,
            redis_client=redis_client,
            delivery_context=delivery_context,
        )
    except Exception as exc:
        raise _problem(500, "Error en playground chat", str(exc)) from exc

    if isinstance(result, dict):
        return {
            "ok": True,
            "worker_id": wid,
            "response": str(result.get("response") or result.get("reply") or ""),
            "assigned_worker_id": result.get("assigned_worker_id"),
            "usage_tokens": result.get("usage_tokens"),
        }
    return {"ok": True, "worker_id": wid, "response": str(result or "")}


class ComfyuiGenerateBody(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=4000)
    negative_prompt: str = Field(default="", max_length=2000)
    aspect_ratio: str = Field(default="1:1", max_length=16)
    template: str = Field(default="comfy_default", max_length=64)
    tenant_id: str | None = Field(default=None, max_length=64)


def _list_comfyui_templates() -> list[dict[str, Any]]:
    workflows_dir = (
        _repo_root()
        / "packages"
        / "agents"
        / "src"
        / "duckclaw"
        / "forge"
        / "templates"
        / "workflows"
    )
    templates: list[dict[str, Any]] = []
    if not workflows_dir.is_dir():
        return templates
    for path in sorted(workflows_dir.glob("*.json")):
        if path.name.endswith(".meta.json"):
            continue
        stem = path.stem
        meta_path = workflows_dir / f"{stem}.meta.json"
        aspect_presets: list[str] = []
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                presets = meta.get("aspect_presets") if isinstance(meta, dict) else None
                if isinstance(presets, dict):
                    aspect_presets = sorted(presets.keys())
            except (OSError, json.JSONDecodeError):
                pass
        templates.append(
            {
                "id": stem,
                "label": stem.replace("_", " ").title(),
                "aspect_ratios": aspect_presets or ["1:1", "16:9", "9:16", "4:3", "3:4"],
            }
        )
    return templates


@router.get("/comfyui/status", dependencies=[Depends(_require_admin_key)])
async def comfyui_status() -> dict[str, Any]:
    import time

    import httpx

    base = (os.environ.get("COMFYUI_API_URL") or "http://127.0.0.1:8188").strip().rstrip("/")
    if not base:
        return {"ok": False, "url": "", "error": "COMFYUI_API_URL no configurada"}
    url = f"{base}/system_stats"
    started = time.perf_counter()
    try:
        checkpoints: list[str] = []
        async with httpx.AsyncClient(timeout=8.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            try:
                oi = await client.get(f"{base}/object_info/CheckpointLoaderSimple")
                if oi.status_code == 200:
                    body = oi.json()
                    node = body.get("CheckpointLoaderSimple") if isinstance(body, dict) else {}
                    req = node.get("input", {}).get("required", {}) if isinstance(node, dict) else {}
                    ckpt_cfg = req.get("ckpt_name") if isinstance(req, dict) else None
                    if isinstance(ckpt_cfg, list) and ckpt_cfg and isinstance(ckpt_cfg[0], list):
                        checkpoints = [str(x) for x in ckpt_cfg[0] if str(x).strip()]
            except Exception:
                checkpoints = []
        latency_ms = round((time.perf_counter() - started) * 1000, 1)
        return {
            "ok": True,
            "url": base,
            "latency_ms": latency_ms,
            "system": data if isinstance(data, dict) else {},
            "checkpoints": checkpoints,
            "checkpoints_ready": len(checkpoints) > 0,
        }
    except Exception as exc:
        return {
            "ok": False,
            "url": base,
            "error": str(exc)[:500],
            "checkpoints": [],
            "checkpoints_ready": False,
        }


@router.get("/comfyui/templates", dependencies=[Depends(_require_admin_key)])
async def comfyui_templates() -> dict[str, Any]:
    items = _list_comfyui_templates()
    return {"templates": items, "default": "comfy_default"}


@router.post("/comfyui/generate", dependencies=[Depends(_require_admin_key)])
async def comfyui_generate(
    body: ComfyuiGenerateBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    import asyncio

    from duckclaw.forge.skills.comfyui_bridge import _generate_visual_asset_impl
    from duckclaw.forge.skills.quant_tool_context import (
        set_quant_tool_tenant_id,
        set_quant_tool_user_id,
    )

    tenant_id = _gateway_effective_tenant_id((body.tenant_id or "default").strip() or "default")
    set_quant_tool_tenant_id(tenant_id)
    set_quant_tool_user_id((actor or "admin-ui").strip() or "admin-ui")

    cfg = {
        "enabled": True,
        "template": (body.template or "comfy_default").strip() or "comfy_default",
    }

    def _run() -> str:
        return _generate_visual_asset_impl(
            body.prompt.strip(),
            negative_prompt=body.negative_prompt or "",
            aspect_ratio=body.aspect_ratio or "1:1",
            comfyui_config=cfg,
        )

    try:
        raw = await asyncio.to_thread(_run)
    except TimeoutError as exc:
        raise _problem(
            504,
            f"Timeout generando en ComfyUI ({exc}). Aumenta COMFYUI_TIMEOUT_SEC si usas MPS.",
            "",
        ) from exc
    except Exception as exc:
        raise _problem(
            502,
            f"Error inesperado en bridge ComfyUI: {type(exc).__name__}: {exc}",
            "",
        ) from exc
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        raise _problem(502, "Respuesta inválida del bridge ComfyUI", raw[:500]) from None
    if not isinstance(payload, dict):
        raise _problem(502, "Respuesta inválida del bridge ComfyUI", "")
    if not payload.get("ok"):
        raise _problem(400, str(payload.get("error") or "Error ComfyUI"), "")
    _admin_audit(
        "comfyui.generate",
        tenant_id,
        f"template={cfg['template']}",
        actor=actor,
    )
    return payload


@router.get("/health", dependencies=[Depends(_require_admin_key)])
async def admin_health(request: Request) -> dict[str, Any]:
    workers: list[str] = []
    try:
        from duckclaw.workers.factory import list_workers

        workers = list_workers()
    except Exception:
        workers = []
    redis_ok = False
    try:
        r = getattr(request.app.state, "redis", None)
        if r is not None:
            await r.ping()
            redis_ok = True
    except Exception:
        redis_ok = False
    return {
        "status": "ok",
        "workers_count": len(workers),
        "workers": workers[:20],
        "redis": redis_ok,
        "templates_dir": str(_templates_dir()),
        "api_revision": 2,
        "features": {
            "catalog": True,
            "ops": True,
            "projects": True,
        },
    }


def _gateway_db_query_rows(db: Any, sql: str) -> list[dict[str, Any]]:
    """Parse JSON rows from GatewayDbEphemeralReadonly.query."""
    try:
        raw = db.query(sql)
    except Exception:
        return []
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return []
    elif isinstance(raw, list):
        parsed = raw
    else:
        return []
    if not isinstance(parsed, list):
        return []
    return [r for r in parsed if isinstance(r, dict)]


@router.get("/overview/metrics", dependencies=[Depends(_require_admin_key)])
async def admin_overview_metrics() -> dict[str, Any]:
    """Agregados analíticos desde main.task_audit_log (actividad 7d, latencia 24h)."""
    from duckclaw.gateway_db import GatewayDbEphemeralReadonly, get_gateway_db_path

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(503, "Gateway DuckDB no disponible", gw or "missing")

    db = GatewayDbEphemeralReadonly(gw)
    activity_sql = """
        SELECT worker_id,
               COUNT(*) FILTER (WHERE upper(status) = 'SUCCESS') AS success_count,
               COUNT(*) FILTER (WHERE upper(status) = 'FAILED') AS failed_count
        FROM main.task_audit_log
        WHERE created_at >= now() - INTERVAL '7 days'
          AND worker_id IS NOT NULL AND trim(worker_id) != ''
        GROUP BY worker_id
        ORDER BY worker_id
    """
    latency_sql = """
        SELECT strftime(created_at, '%H:00') AS hour,
               round(avg(duration_ms)) AS avg_latency
        FROM main.task_audit_log
        WHERE created_at >= now() - INTERVAL '24 hours'
        GROUP BY hour
        ORDER BY cast(left(hour, 2) AS INTEGER)
    """
    activity_rows = _gateway_db_query_rows(db, activity_sql)
    latency_rows = _gateway_db_query_rows(db, latency_sql)

    activity: list[dict[str, Any]] = []
    for row in activity_rows:
        wid = str(row.get("worker_id") or "").strip()
        if not wid:
            continue
        try:
            success_count = int(row.get("success_count") or 0)
        except (TypeError, ValueError):
            success_count = 0
        try:
            failed_count = int(row.get("failed_count") or 0)
        except (TypeError, ValueError):
            failed_count = 0
        activity.append(
            {
                "worker_id": wid,
                "success_count": success_count,
                "failed_count": failed_count,
            }
        )

    latency: list[dict[str, Any]] = []
    for row in latency_rows:
        hour = str(row.get("hour") or "").strip()
        if not hour:
            continue
        try:
            avg_latency = int(row.get("avg_latency") or 0)
        except (TypeError, ValueError):
            avg_latency = 0
        latency.append({"hour": hour, "avg_latency": avg_latency})

    return {"activity": activity, "latency": latency, "db_path": gw}


@router.get("/templates", dependencies=[Depends(_require_admin_key)])
async def list_templates() -> dict[str, Any]:
    from duckclaw.workers.factory import list_workers
    from duckclaw.workers.manifest import load_manifest

    items: list[dict[str, Any]] = []
    for wid in list_workers():
        meta: dict[str, Any] = {"id": wid}
        try:
            spec = load_manifest(wid)
            meta.update(
                {
                    "name": spec.name,
                    "schema_name": spec.schema_name,
                    "temperature": spec.temperature,
                    "topology": spec.topology,
                }
            )
        except Exception as exc:
            meta["load_error"] = str(exc)
        items.append(meta)
    return {"templates": items}


@router.get("/templates/{worker_id}", dependencies=[Depends(_require_admin_key)])
async def get_template(worker_id: str, include_content: bool = True) -> dict[str, Any]:
    base = _templates_dir() / worker_id.strip()
    if not base.is_dir():
        raise _problem(404, "Plantilla no encontrada", worker_id)
    files = _list_template_files(base)
    contents: dict[str, str] = {}
    if include_content:
        for f in files:
            path = f["path"]
            if path.endswith((".yaml", ".yml", ".md", ".sql", ".txt", ".json")):
                try:
                    contents[path] = (base / path).read_text(encoding="utf-8")
                except Exception:
                    contents[path] = ""
    return {"id": worker_id, "files": files, "contents": contents}


@router.put("/templates/{worker_id}/files/{file_path:path}", dependencies=[Depends(_require_admin_key)])
async def put_template_file(
    worker_id: str,
    file_path: str,
    body: FileWriteBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    target = _safe_worker_path(worker_id, file_path)
    if not target.parent.is_dir():
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.content, encoding="utf-8")
    if target.name in ("manifest.yaml", "manifest.yml"):
        from duckclaw.workers.manifest import load_manifest

        load_manifest(worker_id)
    _admin_audit("template.file.put", f"templates/{worker_id}", file_path, actor=actor)
    return {"ok": True, "path": file_path}


def _default_vault_user_id(vault_user_id: str | None = None) -> str:
    return _playground_telegram_user_id(vault_user_id) or "default"


def _manifest_file_for_worker(worker_id: str) -> Path:
    base = _templates_dir() / worker_id.strip()
    for name in ("manifest.yaml", "manifest.yml"):
        candidate = base / name
        if candidate.is_file():
            return candidate
    return base / "manifest.yaml"


def _merge_manifest_vault_binding(worker_id: str, binding: dict[str, str] | None) -> None:
    import yaml

    path = _manifest_file_for_worker(worker_id)
    if not path.parent.is_dir():
        raise _problem(404, "Plantilla no encontrada", worker_id)
    raw: dict = {}
    if path.is_file():
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(loaded, dict):
            raw = loaded
    fc = raw.get("forge_context")
    if not isinstance(fc, dict):
        fc = {}
    if binding:
        fc["vault_binding"] = dict(binding)
    else:
        fc.pop("vault_binding", None)
    if fc:
        raw["forge_context"] = fc
    elif "forge_context" in raw:
        raw.pop("forge_context", None)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(raw, allow_unicode=True, sort_keys=False, default_flow_style=False),
        encoding="utf-8",
    )


@router.get("/templates/{worker_id}/vault-options", dependencies=[Depends(_require_admin_key)])
async def template_vault_options(
    worker_id: str,
    vault_user_id: str | None = Query(None, description="ID dueño de db/private/ (default: DUCKCLAW_OWNER_ID)"),
) -> dict[str, Any]:
    from duckclaw.vaults import list_vault_options_for_user

    wid = worker_id.strip()
    if not (_templates_dir() / wid).is_dir():
        raise _problem(404, "Plantilla no encontrada", wid)
    uid = _default_vault_user_id(vault_user_id)
    options = list_vault_options_for_user(uid)
    return {"vault_user_id": uid, "worker_id": wid, "options": options}


@router.get("/templates/{worker_id}/vault-binding", dependencies=[Depends(_require_admin_key)])
async def get_template_vault_binding(
    worker_id: str,
    vault_user_id: str | None = Query(None),
) -> dict[str, Any]:
    from duckclaw.vaults import resolve_template_vault_path

    wid = worker_id.strip()
    try:
        from duckclaw.workers.manifest import load_manifest

        spec = load_manifest(wid)
    except Exception as exc:
        raise _problem(404, "Plantilla no encontrada o manifest inválido", str(exc)) from exc
    uid = _default_vault_user_id(vault_user_id)
    binding = spec.forge_vault_binding
    resolved = resolve_template_vault_path(binding, uid, require_exists=False)
    return {
        "worker_id": wid,
        "vault_user_id": uid,
        "binding": binding,
        "resolved_path": resolved,
    }


@router.put("/templates/{worker_id}/vault-binding", dependencies=[Depends(_require_admin_key)])
async def put_template_vault_binding(
    worker_id: str,
    body: VaultBindingPutBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from duckclaw.vaults import normalize_vault_binding, resolve_template_vault_path

    wid = worker_id.strip()
    if not (_templates_dir() / wid).is_dir():
        raise _problem(404, "Plantilla no encontrada", wid)
    scope = (body.scope or "").strip().lower()
    binding: dict[str, str] | None
    if not scope:
        binding = None
    elif scope == "private":
        binding = normalize_vault_binding({"scope": "private", "vault_id": body.vault_id or ""})
        if not binding:
            raise _problem(400, "vault_id requerido para scope=private", body.vault_id or "")
    elif scope == "shared":
        binding = normalize_vault_binding({"scope": "shared", "path": body.path or ""})
        if not binding:
            raise _problem(400, "path requerido para scope=shared", body.path or "")
    else:
        raise _problem(400, "scope inválido", scope)
    _merge_manifest_vault_binding(wid, binding)
    from duckclaw.vaults import normalize_vault_binding

    import yaml

    manifest_path = _manifest_file_for_worker(wid)
    raw_loaded = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    fc_out = raw_loaded.get("forge_context") if isinstance(raw_loaded, dict) else {}
    binding_out = (
        normalize_vault_binding(fc_out.get("vault_binding"))
        if isinstance(fc_out, dict)
        else None
    )
    resolved = resolve_template_vault_path(binding_out, _default_vault_user_id(), require_exists=False)
    _admin_audit(
        "template.vault_binding.put",
        f"templates/{wid}",
        scope or "cleared",
        actor=actor,
        meta={"binding": binding, "resolved_path": resolved},
    )
    return {
        "ok": True,
        "worker_id": wid,
        "binding": binding_out,
        "resolved_path": resolved,
    }


def _read_manifest_skills(template_dir: Path) -> list[str]:
    manifest = template_dir / "manifest.yaml"
    if not manifest.is_file():
        return []
    try:
        import yaml

        raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        if not isinstance(raw, dict):
            return []
        sk = raw.get("skills") or []
        if not isinstance(sk, list):
            return []
        out: list[str] = []
        for item in sk:
            if isinstance(item, str) and item.strip():
                out.append(item.strip())
        return out
    except Exception:
        return []


def _merge_skill_lists(base: list[str], extra: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for s in base + extra:
        key = s.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(key)
    return merged


def _write_worker_prompts(dest: Path, *, system_prompt: str, soul: str) -> None:
    sp = (system_prompt or "").strip()
    if sp:
        (dest / "system_prompt.md").write_text(sp + "\n", encoding="utf-8")
    sl = (soul or "").strip()
    if sl:
        (dest / "soul.md").write_text(sl + "\n", encoding="utf-8")


def _create_worker_from_source(
    *,
    wid: str,
    source_template: str,
    name: str = "",
    description: str = "",
    skills: list[str] | None = None,
    topology: str = "",
    system_prompt: str = "",
    soul: str = "",
) -> Path:
    dest = _templates_dir() / wid
    if dest.exists():
        raise _problem(409, "Plantilla ya existe", wid)

    base_rel = "default"
    base = _templates_dir() / base_rel
    if not base.is_dir():
        base = _templates_dir() / "industries" / "business_standard"
    if not base.is_dir():
        raise _problem(404, "Plantilla base default no encontrada", base_rel)

    shutil.copytree(base, dest)

    preset_rel = (source_template or "default").strip().strip("/")
    preset_dir = _templates_dir() / preset_rel
    preset_skills: list[str] = []
    if preset_rel != "default" and preset_dir.is_dir():
        preset_skills = _read_manifest_skills(preset_dir)

    base_skills = _read_manifest_skills(dest)
    if skills is not None and len(skills) > 0:
        final_skills = _merge_skill_lists(base_skills, list(skills))
    else:
        final_skills = _merge_skill_lists(base_skills, preset_skills)

    manifest = dest / "manifest.yaml"
    if manifest.is_file():
        try:
            import yaml

            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                data = {}
            data["id"] = wid
            data["name"] = (name or wid).strip()
            if description.strip():
                data["description"] = description.strip()
            data["skills"] = final_skills
            if topology.strip():
                data["topology"] = topology.strip()
            manifest.write_text(
                yaml.dump(data, allow_unicode=True, default_flow_style=False, sort_keys=False),
                encoding="utf-8",
            )
        except ImportError:
            text = manifest.read_text(encoding="utf-8")
            text = re.sub(r"^id:\s*.+$", f"id: {wid}", text, count=1, flags=re.MULTILINE)
            text = re.sub(r"^name:\s*.+$", f"name: {name or wid}", text, count=1, flags=re.MULTILINE)
            manifest.write_text(text, encoding="utf-8")

    _write_worker_prompts(dest, system_prompt=system_prompt, soul=soul)
    return dest


@router.post("/templates", dependencies=[Depends(_require_admin_key)])
async def create_template(
    body: TemplateCreateBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", body.id.strip())
    if not wid:
        raise _problem(400, "id inválido", body.id)
    _create_worker_from_source(wid=wid, source_template=body.source_template)
    _admin_audit("template.create", f"templates/{wid}", body.source_template, actor=actor)
    return {"ok": True, "id": wid}


@router.delete("/templates/{worker_id}", dependencies=[Depends(_require_admin_key)])
async def delete_template(
    worker_id: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    wid = worker_id.strip()
    if wid in _PROTECTED_TEMPLATE_IDS:
        raise _problem(403, "Plantilla protegida", wid)
    dest = _templates_dir() / wid
    if not dest.is_dir():
        raise _problem(404, "Plantilla no encontrada", wid)
    shutil.rmtree(dest)
    _admin_audit("template.delete", f"templates/{wid}", "rmtree", actor=actor)
    return {"ok": True, "id": wid}


@router.post("/templates/{worker_id}/validate", dependencies=[Depends(_require_admin_key)])
async def validate_template(worker_id: str) -> dict[str, Any]:
    from duckclaw.workers.manifest import load_manifest

    errors: list[str] = []
    try:
        load_manifest(worker_id)
    except Exception as exc:
        errors.append(f"manifest: {exc}")
    if worker_id.upper().startswith("AXIS-"):
        try:
            from duckclaw.adf_validator import validate_agent

            base = _templates_dir() / worker_id
            result = validate_agent(base, canonical_agent_id=worker_id)
            if not result.valid:
                errors.extend(result.errors or [])
        except ImportError:
            pass
        except Exception as exc:
            errors.append(f"adf: {exc}")
    return {"ok": len(errors) == 0, "errors": errors}


@router.get("/env", dependencies=[Depends(_require_admin_key)])
async def get_env_config() -> dict[str, Any]:
    env_path = _env_file()
    values: dict[str, str] = {}
    if env_path.is_file():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            k = k.strip()
            if _is_env_key_allowed(k):
                values[k] = _mask_secret(v.strip().strip("'\""))
    return {"path": str(env_path), "values": values}


@router.patch("/env", dependencies=[Depends(_require_admin_key)])
async def patch_env_config(
    body: EnvPatchBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    env_path = _env_file()
    if not env_path.is_file():
        raise _problem(404, ".env no encontrado", str(env_path))
    backup, updated = _merge_env_lines(body.values)
    _admin_audit("env.patch", ".env", ",".join(updated), actor=actor)
    return {"ok": True, "updated": updated, "backup": str(backup)}


@router.get("/telegram/routes", dependencies=[Depends(_require_admin_key)])
async def get_telegram_routes() -> dict[str, Any]:
    from duckclaw.integrations.telegram.compact_webhook_routes import (
        known_compact_bot_names,
        parse_compact_telegram_webhook_routes,
    )

    key = "DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES"
    raw = (_read_env_key_unmasked(key) or os.environ.get(key) or "").strip()
    routes: list[dict[str, str]] = []
    fmt = "empty"
    if raw:
        if raw.startswith("["):
            fmt = "json"
        else:
            try:
                compact = parse_compact_telegram_webhook_routes(raw)
            except ValueError as exc:
                return {
                    "format": "invalid",
                    "routes": [],
                    "parse_error": str(exc),
                    "raw_masked": _mask_secret(raw),
                    "known_bots": list(known_compact_bot_names()),
                }
            if compact:
                fmt = "compact"
                routes = [
                    {
                        "bot": r.bot_name,
                        "path": r.webhook_path,
                        "worker_id": r.worker_id,
                        "tenant_id": r.tenant_id,
                        "vault_env_var": r.vault_env_var or "",
                        "token_masked": _mask_secret(r.bot_token),
                    }
                    for r in compact
                ]
    return {
        "format": fmt,
        "routes": routes,
        "raw_masked": _mask_secret(raw) if raw else "",
        "known_bots": list(known_compact_bot_names()),
    }


@router.put("/telegram/routes", dependencies=[Depends(_require_admin_key)])
async def put_telegram_routes(
    body: TelegramRoutesPutBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from duckclaw.integrations.telegram.compact_webhook_routes import (
        TelegramCompactWebhookRoute,
        compact_route_to_path_binding,
        parse_compact_telegram_webhook_routes,
        serialize_compact_telegram_webhook_routes,
    )

    key = "DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES"
    current_raw = (_read_env_key_unmasked(key) or os.environ.get(key) or "").strip()
    current_by_bot = {
        r.bot_name: r for r in parse_compact_telegram_webhook_routes(current_raw)
    }

    built: list[TelegramCompactWebhookRoute] = []
    for inp in body.routes:
        bot = inp.bot.strip().lower()
        path = inp.path.strip()
        if not path.startswith("/api/v1/telegram/"):
            raise _problem(
                400,
                "path inválido",
                f"Debe empezar por /api/v1/telegram/ (bot={bot})",
            )
        token_in = (inp.token or "").strip()
        if token_in:
            token = token_in
        elif bot in current_by_bot:
            token = current_by_bot[bot].bot_token
        else:
            raise _problem(400, "Token requerido", f"Ruta nueva «{bot}» sin token de bot")
        worker_id = inp.worker_id.strip()
        tenant_id = inp.tenant_id.strip()
        if not worker_id or not tenant_id:
            raise _problem(400, "worker/tenant requeridos", f"Ruta «{bot}» sin worker_id o tenant_id")
        vault_env = (inp.vault_env_var or "").strip()
        route = TelegramCompactWebhookRoute(
            bot_name=bot,
            bot_token=token,
            webhook_path=path,
            worker_id=worker_id,
            tenant_id=tenant_id,
            vault_env_var=vault_env,
        )
        try:
            compact_route_to_path_binding(route)
        except ValueError as exc:
            raise _problem(400, "Ruta inválida", str(exc)) from exc
        built.append(route)

    try:
        serialized = serialize_compact_telegram_webhook_routes(built)
        parse_compact_telegram_webhook_routes(serialized)
    except ValueError as exc:
        raise _problem(400, "Rutas inválidas", str(exc)) from exc

    backup, updated = _merge_env_lines({key: serialized})
    _admin_audit("telegram.routes.put", key, f"{len(built)} rutas", actor=actor)
    return {
        "ok": True,
        "updated": updated,
        "backup": str(backup),
        "route_count": len(built),
        "restart_hint": "pm2 restart DuckClaw-Gateway --update-env",
    }


@router.get("/runtime/vaults", dependencies=[Depends(_require_admin_key)])
async def list_vaults(
    vault_user_id: str | None = Query(None, description="Filtra private/ al usuario; shared siempre"),
) -> dict[str, Any]:
    from duckclaw.vaults import list_vault_options_for_user

    uid = _default_vault_user_id(vault_user_id)
    options = list_vault_options_for_user(uid)
    vaults = [{"path": o["path"], "scope": o["scope"], "vault_id": o.get("vault_id") or ""} for o in options]
    return {"vaults": vaults, "vault_user_id": uid}


@router.get("/runtime/config", dependencies=[Depends(_require_admin_key)])
async def get_runtime_config(
    vault_path: str = Query(...),
    chat_id: str = Query("default"),
) -> dict[str, Any]:
    from duckclaw import DuckClaw

    abs_path = vault_path
    if not os.path.isabs(abs_path):
        abs_path = str(_repo_root() / vault_path.lstrip("/"))
    if not os.path.isfile(abs_path):
        raise _problem(404, "Vault no encontrado", vault_path)
    db = DuckClaw(abs_path, read_only=True, engine="python")
    warning: str | None = None
    try:
        try:
            db.execute(_AGENT_CONFIG_DDL)
        except Exception:
            pass
        raw = db.query("SELECT key, value FROM agent_config ORDER BY key")
        rows = _parse_agent_config_rows(raw, chat_id)
    except Exception as exc:
        msg = str(exc)
        if "agent_config" in msg.lower() and "does not exist" in msg.lower():
            rows = []
            warning = (
                "La tabla agent_config no existe en esta bóveda. "
                "Ejecuta: uv run python scripts/bootstrap_dbs.py"
            )
        else:
            raise _problem(400, "Error leyendo agent_config", msg) from exc
    finally:
        db.close()
    out: dict[str, Any] = {"vault_path": vault_path, "chat_id": chat_id, "rows": rows}
    if warning:
        out["warning"] = warning
    return out


@router.put("/runtime/config", dependencies=[Depends(_require_admin_key)])
async def put_runtime_config(
    body: RuntimeConfigPutBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    import redis.asyncio as aioredis

    abs_path = body.vault_path
    if not os.path.isabs(abs_path):
        abs_path = str(_repo_root() / body.vault_path.lstrip("/"))
    full_key = _full_agent_config_key(body.chat_id, body.key)
    key_esc = full_key.replace("'", "''")
    val_esc = body.value.replace("'", "''")[:8000]
    sql = (
        f"INSERT INTO agent_config (key, value) VALUES ('{key_esc}', '{val_esc}') "
        f"ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = now()"
    )
    from duckclaw.runtime_env import resolve_redis_url

    redis_url = resolve_redis_url()
    r = aioredis.from_url(redis_url, decode_responses=True)
    try:
        payload = json.dumps(
            {
                "query": sql,
                "params": [],
                "user_id": "admin-ui",
                "db_path": abs_path,
                "tenant_id": "admin",
            }
        )
        await r.lpush("duckdb_write_queue", payload)
    finally:
        await r.aclose()
    _admin_audit(
        "runtime.config.put",
        body.vault_path,
        full_key,
        actor=actor,
        meta={"chat_id": body.chat_id},
    )
    return {"ok": True, "queued": True, "full_key": full_key}


@router.get("/chats/history", dependencies=[Depends(_require_admin_key)])
async def admin_chat_history(
    request: Request,
    tenant_id: str = Query("default"),
    session_id: str = Query(...),
) -> dict[str, Any]:
    from core.chat_history import redis_load_chat_history

    redis_client = getattr(request.app.state, "redis", None)
    items = await redis_load_chat_history(redis_client, tenant_id, session_id)
    return {"tenant_id": tenant_id, "session_id": session_id, "messages": items}


class AdminConversationCreateBody(BaseModel):
    title: str | None = None
    section: str | None = None
    worker_id: str | None = None


class AdminConversationPatchBody(BaseModel):
    title: str


@router.get("/conversations", dependencies=[Depends(_require_admin_key)])
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
    from core.admin_conversations import list_conversations

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    redis_client = getattr(request.app.state, "redis", None)
    items, total = await list_conversations(
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


@router.post("/conversations", dependencies=[Depends(_require_admin_key)])
async def admin_create_conversation(
    request: Request,
    body: AdminConversationCreateBody,
    tenant_id: str = Query("default"),
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_conversations import (
        AdminConversationMeta,
        derive_section_from_session_id,
        new_admin_conversation_session_id,
        upsert_conversation_meta,
    )

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    sid = new_admin_conversation_session_id()
    sec = (body.section or "").strip() or "other"
    redis_client = getattr(request.app.state, "redis", None)
    title = (body.title or "").strip() or f"Conversación {datetime.now(timezone.utc).strftime('%Y-%m-%d')}"
    meta = await upsert_conversation_meta(
        redis_client,
        tenant_id=tid,
        session_id=sid,
        actor=actor,
        section=sec,
        last_worker_id=(body.worker_id or "").strip(),
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
            last_worker_id=(body.worker_id or "").strip(),
            workers=[(body.worker_id or "").strip()] if (body.worker_id or "").strip() else [],
            origin="admin_ui",
        )
    return meta.model_dump()


@router.get("/conversations/{session_id}", dependencies=[Depends(_require_admin_key)])
async def admin_get_conversation(
    request: Request,
    session_id: str,
    tenant_id: str = Query("default"),
) -> dict[str, Any]:
    from core.admin_conversations import get_conversation_meta
    from core.chat_history import redis_load_chat_history

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    sid = (session_id or "").strip()
    if not sid:
        raise _problem(400, "session_id vacío", session_id)
    redis_client = getattr(request.app.state, "redis", None)
    meta = await get_conversation_meta(redis_client, tid, sid)
    messages = await redis_load_chat_history(redis_client, tid, sid)
    if meta is None and not messages:
        raise _problem(404, "Conversación no encontrada", sid)
    out: dict[str, Any] = {
        "tenant_id": tid,
        "session_id": sid,
        "messages": messages,
    }
    if meta is not None:
        out.update(meta.model_dump())
    return out


@router.patch("/conversations/{session_id}", dependencies=[Depends(_require_admin_key)])
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


@router.delete("/conversations/{session_id}", dependencies=[Depends(_require_admin_key)])
async def admin_delete_conversation(
    request: Request,
    session_id: str,
    tenant_id: str = Query("default"),
) -> dict[str, Any]:
    from core.admin_conversations import delete_conversation

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    sid = (session_id or "").strip()
    if not sid:
        raise _problem(400, "session_id vacío", session_id)
    redis_client = getattr(request.app.state, "redis", None)
    ok = await delete_conversation(redis_client, tid, sid)
    if not ok:
        raise _problem(404, "Conversación no encontrada", sid)
    return {"ok": True, "session_id": sid, "tenant_id": tid}


@router.post("/conversations/reindex", dependencies=[Depends(_require_admin_key)])
async def admin_reindex_conversations(
    request: Request,
    tenant_id: str = Query("default"),
) -> dict[str, Any]:
    from core.admin_conversations import reindex_admin_conversations

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    redis_client = getattr(request.app.state, "redis", None)
    stats = await reindex_admin_conversations(redis_client, tid)
    return {"tenant_id": tid, **stats}


@router.post("/auth/login")
async def admin_auth_login(body: AdminLoginBody) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.admin_console_users import (
        authenticate_console_user,
        seed_admin_console_users_if_empty,
    )
    from duckclaw.gateway_db import get_gateway_db_path

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(503, "Gateway DuckDB no disponible", gw)
    db = DuckClaw(gw, read_only=False, engine="python")
    try:
        seed_admin_console_users_if_empty(db)
        user = authenticate_console_user(db, email=body.email, password=body.password)
    finally:
        db.close()
    if not user:
        raise _problem(401, "Credenciales inválidas", body.email or "unknown")
    return {
        "email": user["email"],
        "nombre": user["nombre"],
        "rol": user["rol"],
        "initials": user.get("initials") or "",
        "id": user.get("id") or f"user-{user['email']}",
    }


@router.get("/access/overview", dependencies=[Depends(_require_admin_key)])
async def get_access_overview(tenant_id: str = Query("default")) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.admin_console_users import count_console_users, list_console_users
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.graphs.on_the_fly_commands import _list_authorized_users
    from duckclaw.shared_db_grants import list_shared_grants_for_tenant

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    gw = (get_gateway_db_path() or "").strip()
    console_count = 0
    telegram_count = 0
    shared_count = 0
    if gw and os.path.isfile(gw):
        db = DuckClaw(gw, read_only=True, engine="python")
        try:
            console_count = count_console_users(db)
            users = _list_authorized_users(db, tenant_id=tid)
            telegram_count = len(users)
            shared_count = len(list_shared_grants_for_tenant(db, tenant_id=tid))
        finally:
            db.close()
    return {
        "tenant_id": tid,
        "console_users": console_count,
        "telegram_users": telegram_count,
        "shared_grants": shared_count,
        "db_path": gw,
    }


@router.get("/console-users", dependencies=[Depends(_require_admin_key)])
async def list_admin_console_users() -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.admin_console_users import list_console_users
    from duckclaw.gateway_db import get_gateway_db_path

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        return {"users": [], "db_path": gw, "warning": "Gateway DuckDB no encontrada"}
    db = DuckClaw(gw, read_only=True, engine="python")
    try:
        users = list_console_users(db)
    finally:
        db.close()
    return {"users": users, "db_path": gw}


@router.post("/console-users", dependencies=[Depends(_require_admin_key)])
async def create_admin_console_user(
    body: ConsoleUserBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.admin_console_users import upsert_console_user
    from duckclaw.gateway_db import get_gateway_db_path

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(404, "Gateway DuckDB no encontrada", gw)
    if not (body.password or "").strip():
        raise _problem(400, "password requerido", body.email)
    rw = DuckClaw(gw, read_only=False, engine="python")
    try:
        user = upsert_console_user(
            rw,
            email=body.email,
            nombre=body.nombre,
            rol=body.rol,
            password=body.password,
            initials=body.initials,
            active=body.active,
        )
    except ValueError as exc:
        raise _problem(400, str(exc), body.email) from exc
    finally:
        rw.close()
    _admin_audit("console.user.upsert", body.email, body.rol, actor=actor)
    return {"ok": True, "user": user, "db_path": gw}


@router.patch("/console-users", dependencies=[Depends(_require_admin_key)])
async def patch_admin_console_user(
    email: str = Query(...),
    body: ConsoleUserPatchBody = ...,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.admin_console_users import get_by_email, upsert_console_user
    from duckclaw.gateway_db import get_gateway_db_path

    em = (email or "").strip()
    if not em:
        raise _problem(400, "email requerido", "")
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(404, "Gateway DuckDB no encontrada", gw)
    rw = DuckClaw(gw, read_only=False, engine="python")
    try:
        existing = get_by_email(rw, em)
        if not existing:
            raise _problem(404, "Usuario no encontrado", em)
        user = upsert_console_user(
            rw,
            email=em,
            nombre=body.nombre if body.nombre is not None else str(existing.get("nombre") or ""),
            rol=body.rol if body.rol is not None else str(existing.get("rol") or "viewer"),
            password=body.password,
            initials=body.initials if body.initials is not None else str(existing.get("initials") or ""),
            active=body.active if body.active is not None else bool(existing.get("active", True)),
        )
    except ValueError as exc:
        raise _problem(400, str(exc), em) from exc
    finally:
        rw.close()
    _admin_audit("console.user.patch", em, body.rol or "", actor=actor)
    return {"ok": True, "user": user, "db_path": gw}


@router.delete("/console-users", dependencies=[Depends(_require_admin_key)])
async def delete_admin_console_user(
    email: str = Query(...),
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.admin_console_users import deactivate_console_user
    from duckclaw.gateway_db import get_gateway_db_path

    em = (email or "").strip()
    if not em:
        raise _problem(400, "email requerido", "")
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(404, "Gateway DuckDB no encontrada", gw)
    rw = DuckClaw(gw, read_only=False, engine="python")
    try:
        ok = deactivate_console_user(rw, email=em)
    finally:
        rw.close()
    if not ok:
        raise _problem(404, "Usuario no encontrado", em)
    _admin_audit("console.user.deactivate", em, "", actor=actor)
    return {"ok": True, "email": em, "db_path": gw}


@router.get("/access/shared-grants", dependencies=[Depends(_require_admin_key)])
async def get_shared_grants(tenant_id: str = Query("default")) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.shared_db_grants import list_shared_grants_for_tenant

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        return {"tenant_id": tid, "grants": [], "db_path": gw, "warning": "Gateway DuckDB no encontrada"}
    db = DuckClaw(gw, read_only=True, engine="python")
    try:
        grants = list_shared_grants_for_tenant(db, tenant_id=tid)
    finally:
        db.close()
    return {"tenant_id": tid, "grants": grants, "db_path": gw}


@router.post("/access/shared-grants", dependencies=[Depends(_require_admin_key)])
async def post_shared_grant(
    body: SharedGrantBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.shared_db_grants import upsert_shared_grant, validate_resource_key

    tid = _gateway_effective_tenant_id((body.tenant_id or "default").strip() or "default")
    uid = (body.user_id or "").strip()
    rk = (body.resource_key or "").strip().lower()
    if not uid:
        raise _problem(400, "user_id requerido", "")
    if not validate_resource_key(rk):
        raise _problem(400, "resource_key inválido", rk)
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(404, "Gateway DuckDB no encontrada", gw)
    rw = DuckClaw(gw, read_only=False, engine="python")
    try:
        upsert_shared_grant(rw, tenant_id=tid, user_id=uid, resource_key=rk)
    finally:
        rw.close()
    _admin_audit("access.shared.grant", f"tenant:{tid}", f"{uid}:{rk}", actor=actor)
    return {"ok": True, "tenant_id": tid, "user_id": uid, "resource_key": rk, "db_path": gw}


@router.delete("/access/shared-grants", dependencies=[Depends(_require_admin_key)])
async def delete_shared_grant(
    tenant_id: str = Query("default"),
    user_id: str = Query(...),
    resource_key: str = Query(...),
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.shared_db_grants import delete_shared_grant

    tid = _gateway_effective_tenant_id((tenant_id or "default").strip() or "default")
    uid = (user_id or "").strip()
    rk = (resource_key or "").strip().lower()
    if not uid or not rk:
        raise _problem(400, "user_id y resource_key requeridos", "")
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(404, "Gateway DuckDB no encontrada", gw)
    rw = DuckClaw(gw, read_only=False, engine="python")
    try:
        delete_shared_grant(rw, tenant_id=tid, user_id=uid, resource_key=rk)
    finally:
        rw.close()
    _admin_audit("access.shared.revoke", f"tenant:{tid}", f"{uid}:{rk}", actor=actor)
    return {"ok": True, "tenant_id": tid, "user_id": uid, "resource_key": rk, "db_path": gw}


@router.get("/telegram/whitelist", dependencies=[Depends(_require_admin_key)])
async def get_telegram_whitelist(tenant_id: str = Query("default")) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.graphs.on_the_fly_commands import _ensure_authorized_users_table

    requested = (tenant_id or "default").strip() or "default"
    tid = _gateway_effective_tenant_id(requested)
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        return {
            "tenant_id": tid,
            "requested_tenant_id": requested,
            "effective_tenant_id": tid,
            "users": [],
            "db_path": gw,
            "warning": "Gateway DuckDB no encontrada",
        }
    db = DuckClaw(gw, read_only=True, engine="python")
    try:
        _ensure_authorized_users_table(db)
        users = _list_whitelist_users_merged(db, tenant_id=tid)
    finally:
        db.close()
    hint = None
    if requested.lower() == "default" and tid.lower() != "default":
        hint = (
            f"El gateway usa tenant «{tid}» (DUCKCLAW_GATEWAY_TENANT_ID o heurística PM2). "
            "Los usuarios deben estar en este tenant para pasar el Telegram Guard."
        )
    return {
        "tenant_id": tid,
        "requested_tenant_id": requested,
        "effective_tenant_id": tid,
        "users": users,
        "db_path": gw,
        "hint": hint,
    }


@router.get("/audit", dependencies=[Depends(_require_admin_key)])
async def get_admin_audit(limit: int = Query(100, ge=1, le=500)) -> dict[str, Any]:
    path = _audit_log_path()
    if not path.is_file():
        return {"entries": []}
    lines = path.read_text(encoding="utf-8").splitlines()
    entries: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    entries.reverse()
    return {"entries": entries}


@router.post("/telegram/whitelist", dependencies=[Depends(_require_admin_key)])
async def post_telegram_whitelist(
    body: WhitelistBody,
    request: Request,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.graphs.on_the_fly_commands import (
        _ensure_authorized_users_table,
        _upsert_authorized_user,
    )

    requested = (body.tenant_id or "default").strip() or "default"
    tid = _gateway_effective_tenant_id(requested)
    uid = (body.user_id or "").strip()
    if not uid:
        raise _problem(400, "user_id requerido", "")
    role = (body.role or "user").strip().lower()
    if role not in ("admin", "user"):
        raise _problem(400, "role inválido", role)
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(404, "Gateway DuckDB no encontrada", gw)
    rw = DuckClaw(gw, read_only=False, engine="python")
    try:
        _ensure_authorized_users_table(rw)
        _upsert_authorized_user(
            rw,
            tenant_id=tid,
            user_id=uid,
            username=(body.username or "Usuario").strip() or "Usuario",
            role=role,
        )
    finally:
        rw.close()
    await _invalidate_whitelist_cache(request, tenant_id=tid, user_id=uid)
    _admin_audit(
        "telegram.whitelist.upsert",
        f"tenant:{tid}",
        uid,
        actor=actor,
        meta={"role": role, "requested_tenant_id": requested},
    )
    return {
        "ok": True,
        "tenant_id": tid,
        "effective_tenant_id": tid,
        "requested_tenant_id": requested,
        "user_id": uid,
        "role": role,
        "db_path": gw,
    }


@router.delete("/telegram/whitelist", dependencies=[Depends(_require_admin_key)])
async def delete_telegram_whitelist(
    request: Request,
    tenant_id: str = Query("default"),
    user_id: str = Query(...),
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.graphs.on_the_fly_commands import (
        _delete_authorized_user,
        _ensure_authorized_users_table,
    )

    requested = (tenant_id or "default").strip() or "default"
    tid = _gateway_effective_tenant_id(requested)
    uid = (user_id or "").strip()
    if not uid:
        raise _problem(400, "user_id requerido", "")
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(404, "Gateway DuckDB no encontrada", gw)
    rw = DuckClaw(gw, read_only=False, engine="python")
    try:
        _ensure_authorized_users_table(rw)
        _delete_authorized_user(rw, tenant_id=tid, user_id=uid)
    finally:
        rw.close()
    await _invalidate_whitelist_cache(request, tenant_id=tid, user_id=uid)
    _admin_audit("telegram.whitelist.delete", f"tenant:{tid}", uid, actor=actor)
    return {"ok": True, "tenant_id": tid, "effective_tenant_id": tid, "user_id": uid}


@router.get("/fly-commands", dependencies=[Depends(_require_admin_key)])
async def list_fly_commands() -> dict[str, Any]:
    from duckclaw.guardrails.loader import load_guardrail, load_guardrail_pipe_table

    header = load_guardrail("fly_commands", "help_header")
    entries = [
        {"cmd": cmd, "description": desc}
        for cmd, desc in load_guardrail_pipe_table("fly_commands", "help_entries")
    ]
    return {"header": header, "commands": entries}


@router.delete("/runtime/config", dependencies=[Depends(_require_admin_key)])
async def delete_runtime_config(
    vault_path: str = Query(...),
    chat_id: str = Query("default"),
    key: str = Query(...),
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    import redis.asyncio as aioredis

    abs_path = vault_path
    if not os.path.isabs(abs_path):
        abs_path = str(_repo_root() / vault_path.lstrip("/"))
    full_key = _full_agent_config_key(chat_id, key)
    key_esc = full_key.replace("'", "''")
    sql = f"DELETE FROM agent_config WHERE key = '{key_esc}'"
    from duckclaw.runtime_env import resolve_redis_url

    redis_url = resolve_redis_url()
    r = aioredis.from_url(redis_url, decode_responses=True)
    try:
        payload = json.dumps(
            {
                "query": sql,
                "params": [],
                "user_id": "admin-ui",
                "db_path": abs_path,
                "tenant_id": "admin",
            }
        )
        await r.lpush("duckdb_write_queue", payload)
    finally:
        await r.aclose()
    _admin_audit(
        "runtime.config.delete",
        vault_path,
        full_key,
        actor=actor,
        meta={"chat_id": chat_id},
    )
    return {"ok": True, "queued": True, "full_key": full_key}


@router.get("/catalog/skills", dependencies=[Depends(_require_admin_key)])
async def catalog_skills() -> dict[str, Any]:
    forge = _repo_root() / "packages" / "agents" / "src" / "duckclaw" / "forge"
    global_skills: list[dict[str, str]] = []
    skills_dir = forge / "skills"
    if skills_dir.is_dir():
        for py in sorted(skills_dir.glob("*.py")):
            if py.name.startswith("_"):
                continue
            global_skills.append(
                {
                    "id": py.stem,
                    "path": str(py.relative_to(_repo_root())),
                    "scope": "global",
                }
            )
    template_skills: list[dict[str, str]] = []
    templates_root = _templates_dir()
    for worker_dir in sorted(templates_root.iterdir()):
        if not worker_dir.is_dir() or worker_dir.name.startswith("."):
            continue
        local = worker_dir / "skills"
        if not local.is_dir():
            continue
        for py in sorted(local.glob("*.py")):
            if py.name.startswith("_"):
                continue
            template_skills.append(
                {
                    "id": py.stem,
                    "worker_id": worker_dir.name,
                    "path": str(py.relative_to(_repo_root())),
                    "scope": "template",
                }
            )
    return {"global": global_skills, "template_local": template_skills}


@router.get("/catalog/source-preview", dependencies=[Depends(_require_admin_key)])
async def catalog_source_preview(source_template: str = Query(...)) -> dict[str, Any]:
    src_rel = source_template.strip().strip("/")
    src = _templates_dir() / src_rel
    if not src.is_dir():
        raise _problem(404, "Plantilla origen no encontrada", source_template)
    manifest = src / "manifest.yaml"
    skills: list[str] = []
    name = src_rel
    description = ""
    topology = "general"
    if manifest.is_file():
        try:
            import yaml

            raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            if isinstance(raw, dict):
                name = str(raw.get("name") or src_rel)
                description = str(raw.get("description") or "")
                topology = str(raw.get("topology") or "general")
                sk = raw.get("skills") or []
                if isinstance(sk, list):
                    skills = [str(s) for s in sk]
        except Exception:
            pass
    system_prompt = ""
    soul = ""
    sp_path = src / "system_prompt.md"
    soul_path = src / "soul.md"
    if sp_path.is_file():
        try:
            system_prompt = sp_path.read_text(encoding="utf-8")
        except Exception:
            pass
    if soul_path.is_file():
        try:
            soul = soul_path.read_text(encoding="utf-8")
        except Exception:
            pass
    return {
        "source_template": src_rel,
        "name": name,
        "description": description,
        "topology": topology,
        "skills": skills,
        "system_prompt": system_prompt,
        "soul": soul,
    }


@router.get("/catalog/industries", dependencies=[Depends(_require_admin_key)])
async def catalog_industries() -> dict[str, Any]:
    industries_dir = _templates_dir() / "industries"
    items: list[dict[str, str]] = []
    if industries_dir.is_dir():
        for d in sorted(industries_dir.iterdir()):
            if d.is_dir() and (d / "manifest.yaml").is_file():
                rel = f"industries/{d.name}"
                name = d.name
                try:
                    import yaml

                    raw = yaml.safe_load((d / "manifest.yaml").read_text(encoding="utf-8")) or {}
                    if isinstance(raw, dict):
                        name = str(raw.get("name") or d.name)
                except Exception:
                    pass
                items.append({"id": rel, "name": name, "path": rel})
    return {"industries": items, "starters": _catalog_starter_items()}


@router.get("/catalog/topologies", dependencies=[Depends(_require_admin_key)])
async def catalog_topologies() -> dict[str, Any]:
    return {
        "topologies": [
            {
                "id": "general",
                "label": "General",
                "description": "Worker autónomo estándar (un agente, un manifest).",
            },
            {
                "id": "orchestrator",
                "label": "Orquestador",
                "description": "Coordina sub-workers vía orchestrator.orchestrates en manifest.yaml.",
            },
        ]
    }


async def _probe_mcp_http(port: str) -> dict[str, Any]:
    import httpx

    base = f"http://127.0.0.1:{port}"
    out: dict[str, Any] = {"reachable": False, "url": f"{base}/mcp", "port": port}
    try:
        async with httpx.AsyncClient(timeout=2.5) as client:
            r = await client.get(f"{base}/")
            out["status_code"] = r.status_code
            out["reachable"] = r.status_code < 500
            try:
                body = r.json()
                if isinstance(body, dict):
                    out["service"] = body.get("service")
                    out["hint"] = body.get("hint")
            except Exception:
                pass
    except Exception as exc:
        out["error"] = str(exc)
    return out


@router.get("/catalog/mcp", dependencies=[Depends(_require_admin_key)])
async def catalog_mcp() -> dict[str, Any]:
    mcp_port = (os.environ.get("DUCKCLAW_MCP_PORT") or "8001").strip()
    duckclaw_tools = [
        {
            "name": "open_meteo_current_weather",
            "description": "Clima actual por ciudad (Open-Meteo)",
            "server": "duckclaw_mcp",
        },
        {
            "name": "invoke_manager_graph",
            "description": "Fly commands / y grafo Manager (Telegram, workers, team)",
            "server": "duckclaw_mcp",
        },
        {
            "name": "invoke_core_conversation_graph",
            "description": "Grafo core (/status, /balance)",
            "server": "duckclaw_mcp",
        },
        {
            "name": "list_graph_tools",
            "description": "Descubrimiento de capacidades MCP",
            "server": "duckclaw_mcp",
        },
    ]
    stdio_servers: list[dict[str, Any]] = []
    cfg_path = _repo_root() / "config" / "mcp_servers.yaml"
    if cfg_path.is_file():
        try:
            import yaml

            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
            servers = raw.get("mcp_servers") or {}
            if isinstance(servers, dict):
                for key, val in servers.items():
                    if isinstance(val, dict):
                        stdio_servers.append(
                            {
                                "id": key,
                                "enabled": bool(val.get("enabled", True)),
                                "note": "stdio vía gateway (ver config/mcp_servers.yaml)",
                            }
                        )
        except Exception:
            pass
    live = await _probe_mcp_http(mcp_port)
    from core.mcp_official_catalog import load_official_mcp_reference

    official_reference = load_official_mcp_reference(_repo_root())
    return {
        "duckclaw_mcp": {
            "command": "uv run python -m duckclaw_mcp --host 0.0.0.0 --port " + mcp_port,
            "url": f"http://127.0.0.1:{mcp_port}/mcp",
            "tools": duckclaw_tools,
            "live": live,
        },
        "stdio_servers": stdio_servers,
        "official_reference": official_reference,
        "github_note": "GitHub MCP vía forge/skills/github_bridge.py (Docker)",
    }


_OPS_ALLOWLIST: dict[str, list[str]] = {
    "pm2_list": ["pm2", "list"],
    "pm2_status": ["pm2", "status"],
    "pm2_restart_gateway": ["pm2", "restart", "DuckClaw-Gateway", "--update-env"],
    "pm2_restart_db_writer": ["pm2", "restart", "DuckClaw-DB-Writer", "--update-env"],
    "pm2_start_db_writer": ["pm2", "start", "config/ecosystem.db-writer.config.cjs", "--update-env"],
    "pm2_start_gateway": [
        "pm2",
        "start",
        "config/ecosystem.api.config.cjs",
        "--only",
        "DuckClaw-Gateway",
        "--update-env",
    ],
    "pm2_logs_gateway": ["pm2", "logs", "DuckClaw-Gateway", "--lines", "40", "--nostream"],
    "pm2_start_mcp": ["pm2", "start", "config/ecosystem.mcp.config.cjs"],
    "pm2_restart_mcp": ["pm2", "restart", "DuckClaw-MCP", "--update-env"],
    "pm2_logs_mcp": ["pm2", "logs", "DuckClaw-MCP", "--lines", "40", "--nostream"],
    "pm2_start_comfyui": ["pm2", "start", "config/ecosystem.comfyui.config.cjs", "--update-env"],
    "pm2_restart_comfyui": ["pm2", "restart", "ComfyUI", "--update-env"],
    "pm2_logs_comfyui": ["pm2", "logs", "ComfyUI", "--lines", "40", "--nostream"],
    "doctor": ["uv", "run", "python", "scripts/doctor.py"],
    "bootstrap_dbs": ["uv", "run", "python", "scripts/bootstrap_dbs.py"],
}


@router.get("/ops/commands", dependencies=[Depends(_require_admin_key)])
async def list_ops_commands() -> dict[str, Any]:
    labels = {
        "pm2_list": "PM2 — listar procesos",
        "pm2_status": "PM2 — estado",
        "pm2_restart_gateway": "Reiniciar DuckClaw-Gateway",
        "pm2_restart_db_writer": "Reiniciar DuckClaw-DB-Writer",
        "pm2_start_db_writer": "Iniciar DuckClaw-DB-Writer",
        "pm2_start_gateway": "Iniciar DuckClaw-Gateway",
        "pm2_logs_gateway": "Últimas líneas log Gateway",
        "pm2_start_mcp": "Iniciar DuckClaw-MCP (ecosystem.mcp.config.cjs)",
        "pm2_restart_mcp": "Reiniciar DuckClaw-MCP",
        "pm2_logs_mcp": "Últimas líneas log MCP",
        "pm2_start_comfyui": "Iniciar ComfyUI (ecosystem.comfyui.config.cjs)",
        "pm2_restart_comfyui": "Reiniciar ComfyUI",
        "pm2_logs_comfyui": "Últimas líneas log ComfyUI",
        "doctor": "Diagnóstico local (doctor.py)",
        "bootstrap_dbs": "Bootstrap DuckDB (tablas agent_config, etc.)",
    }
    return {
        "commands": [
            {"id": k, "label": labels.get(k, k), "argv": v}
            for k, v in _OPS_ALLOWLIST.items()
        ]
    }


class OpsRunBody(BaseModel):
    op_id: str


def _pm2_restart_interrupted(op_id: str, exit_code: int, stdout: str) -> bool:
    """PM2 reinició el gateway y mató el proceso que ejecutaba el comando (SIGINT → -2)."""
    if exit_code != -2:
        return False
    if "Applying action restartProcessId" not in stdout:
        return False
    if op_id == "pm2_restart_gateway":
        return "DuckClaw-Gateway" in stdout
    return False


def _normalize_ops_result(op_id: str, result: dict[str, Any]) -> dict[str, Any]:
    exit_code = int(result.get("exit_code") or 1)
    stdout = str(result.get("stdout") or "")
    if _pm2_restart_interrupted(op_id, exit_code, stdout):
        return {**result, "exit_code": 0}
    return result


@router.post("/ops/run", dependencies=[Depends(_require_admin_key)])
async def run_ops_command(
    body: OpsRunBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    import asyncio
    import subprocess

    op_id = (body.op_id or "").strip()
    argv = _OPS_ALLOWLIST.get(op_id)
    if not argv:
        raise _problem(400, "Comando no permitido", op_id)

    def _run() -> dict[str, Any]:
        proc = subprocess.run(
            argv,
            cwd=str(_repo_root()),
            capture_output=True,
            text=True,
            timeout=90,
        )
        return {
            "exit_code": proc.returncode,
            "stdout": (proc.stdout or "")[-12000:],
            "stderr": (proc.stderr or "")[-8000:],
        }

    try:
        result = await asyncio.to_thread(_run)
    except subprocess.TimeoutExpired:
        raise _problem(408, "Timeout ejecutando comando", op_id) from None
    except Exception as exc:
        raise _problem(500, "Error ejecutando comando", str(exc)) from exc

    result = _normalize_ops_result(op_id, result)
    if op_id in ("pm2_start_comfyui", "pm2_restart_comfyui") and result.get("exit_code") == 0:
        import asyncio
        import time

        from duckclaw.forge.skills.comfyui_bridge import clear_all_comfy_generations, reset_comfyui_runtime

        clear_all_comfy_generations()
        await asyncio.sleep(6)
        comfy_reset = await asyncio.to_thread(reset_comfyui_runtime)
        result["comfyui_reset"] = comfy_reset
    _admin_audit("ops.run", op_id, " ".join(argv), actor=actor, meta=result)
    return {"ok": result.get("exit_code") == 0, "op_id": op_id, **result}


@router.post("/projects", dependencies=[Depends(_require_admin_key)])
async def create_project(
    body: ProjectCreateBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", body.id.strip())
    if not wid:
        raise _problem(400, "id inválido", body.id)
    dest = _create_worker_from_source(
        wid=wid,
        source_template=body.source_template,
        name=body.name,
        description=body.description,
        skills=body.skills,
        topology=body.topology,
        system_prompt=body.system_prompt,
        soul=body.soul,
    )
    _admin_audit(
        "project.create",
        f"templates/{wid}",
        body.source_template,
        actor=actor,
        meta={"skills": body.skills, "path": str(dest.relative_to(_repo_root()))},
    )
    return {"ok": True, "id": wid, "path": str(dest.relative_to(_repo_root()))}


@router.get("/forge-projects", dependencies=[Depends(_require_admin_key)])
async def list_forge_projects() -> dict[str, Any]:
    return {"projects": _list_forge_projects()}


@router.get("/forge-projects/env-presets", dependencies=[Depends(_require_admin_key)])
async def forge_project_env_presets() -> dict[str, Any]:
    from duckclaw.forge.team_env import load_team_from_env

    presets: list[dict[str, Any]] = []
    env_row = load_team_from_env()
    for row in [env_row] if env_row else []:
        sid = str(row.get("slug") or row.get("id") or "").strip()
        members = _canonicalize_project_members(list(row.get("members") or []))
        if not sid or not members:
            continue
        ctx = (row.get("shared_context") or "").strip()
        ctx_file = (row.get("shared_context_file") or "").strip()
        if not ctx and ctx_file:
            p = Path(ctx_file)
            if not p.is_absolute():
                p = (_repo_root() / ctx_file).resolve()
            if p.is_file():
                ctx = p.read_text(encoding="utf-8")
        presets.append(
            {
                "id": sid,
                "display_name": str(row.get("display_name") or sid),
                "coordinator": row.get("coordinator"),
                "members": members,
                "shared_vault_id": row.get("shared_vault_id"),
                "shared_context": ctx,
                "source": "env",
            }
        )
    return {"presets": presets}


@router.get("/forge-projects/{slug}", dependencies=[Depends(_require_admin_key)])
async def get_forge_project(slug: str) -> dict[str, Any]:
    sid = _safe_project_slug(slug)
    base = _projects_dir() / sid
    manifest = base / "project.yaml"
    if not manifest.is_file():
        raise _problem(404, "Proyecto no encontrado", sid)
    data = _read_project_yaml(manifest)
    shared_path = base / "_shared" / "context.md"
    shared_context = ""
    if shared_path.is_file():
        shared_context = shared_path.read_text(encoding="utf-8")
    return {
        "id": str(data.get("id") or sid),
        "slug": sid,
        "display_name": str(data.get("display_name") or sid),
        "coordinator": data.get("coordinator"),
        "members": data.get("members") if isinstance(data.get("members"), list) else [],
        "shared_vault_id": data.get("shared_vault_id"),
        "shared_context": shared_context,
        "path": str(base.relative_to(_repo_root())),
    }


@router.post("/forge-projects", dependencies=[Depends(_require_admin_key)])
async def create_forge_project(
    body: ForgeProjectCreateBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    sid = _safe_project_slug(body.id)
    base = _projects_dir() / sid
    if (base / "project.yaml").is_file():
        raise _problem(409, "Proyecto ya existe", sid)

    members = _canonicalize_project_members(body.members)
    if not members:
        raise _problem(400, "Sin miembros válidos", "Añade templates existentes en forge/templates")

    coordinator = (body.coordinator or "").strip() or None

    data: dict[str, Any] = {
        "id": sid,
        "display_name": (body.display_name or sid).strip(),
        "coordinator": coordinator,
        "members": members,
        "shared_vault_id": (body.shared_vault_id or "").strip() or None,
        "shared_context_file": "./_shared/context.md",
    }
    _write_project_yaml(base / "project.yaml", data)
    shared = (body.shared_context or "").strip()
    if shared:
        (base / "_shared").mkdir(parents=True, exist_ok=True)
        (base / "_shared" / "context.md").write_text(shared + "\n", encoding="utf-8")

    if body.apply_tenant_team:
        from duckclaw.gateway_db import GatewayDbEphemeralReadonly, get_gateway_db_path
        from duckclaw.graphs.on_the_fly_commands import set_tenant_team_templates

        gw = (get_gateway_db_path() or "").strip()
        if gw and os.path.isfile(gw):
            db = GatewayDbEphemeralReadonly(gw)
            tid = _gateway_effective_tenant_id(body.tenant_id)
            set_tenant_team_templates(db, tid, members)

    _admin_audit("forge_project.create", f"forge/projects/{sid}", sid, actor=actor, meta={"members": members})
    return {"ok": True, "id": sid, "path": str(base.relative_to(_repo_root())), "members": members}


@router.patch("/forge-projects/{slug}", dependencies=[Depends(_require_admin_key)])
async def patch_forge_project(
    slug: str,
    body: ForgeProjectPatchBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    sid = _safe_project_slug(slug)
    base = _projects_dir() / sid
    manifest = base / "project.yaml"
    if not manifest.is_file():
        raise _problem(404, "Proyecto no encontrado", sid)
    data = _read_project_yaml(manifest)
    if body.display_name is not None:
        data["display_name"] = body.display_name.strip()
    if body.members is not None:
        data["members"] = _canonicalize_project_members(body.members)
    if body.coordinator is not None:
        data["coordinator"] = body.coordinator.strip() or None
    if body.shared_vault_id is not None:
        data["shared_vault_id"] = body.shared_vault_id.strip() or None
    _write_project_yaml(manifest, data)
    if body.shared_context is not None:
        (base / "_shared").mkdir(parents=True, exist_ok=True)
        (base / "_shared" / "context.md").write_text(
            (body.shared_context or "").strip() + "\n", encoding="utf-8"
        )
    _admin_audit("forge_project.patch", f"forge/projects/{sid}", sid, actor=actor)
    return {"ok": True, "id": sid}


@router.delete("/forge-projects/{slug}", dependencies=[Depends(_require_admin_key)])
async def delete_forge_project(
    slug: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    sid = _safe_project_slug(slug)
    base = _projects_dir() / sid
    if not base.is_dir():
        raise _problem(404, "Proyecto no encontrado", sid)
    shutil.rmtree(base)
    _admin_audit("forge_project.delete", f"forge/projects/{sid}", sid, actor=actor)
    return {"ok": True, "id": sid}


@router.post("/forge-projects/{slug}/apply-team", dependencies=[Depends(_require_admin_key)])
async def apply_forge_project_team(
    slug: str,
    tenant_id: str = Query("default"),
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    sid = _safe_project_slug(slug)
    manifest = _projects_dir() / sid / "project.yaml"
    if not manifest.is_file():
        raise _problem(404, "Proyecto no encontrado", sid)
    data = _read_project_yaml(manifest)
    members_raw = data.get("members")
    members = _canonicalize_project_members(members_raw if isinstance(members_raw, list) else [])
    if not members:
        raise _problem(400, "Proyecto sin miembros", sid)

    from duckclaw.gateway_db import GatewayDbEphemeralReadonly, get_gateway_db_path
    from duckclaw.graphs.on_the_fly_commands import set_tenant_team_templates

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(503, "Gateway DuckDB no encontrada", gw or "")
    db = GatewayDbEphemeralReadonly(gw)
    tid = _gateway_effective_tenant_id(tenant_id)
    set_tenant_team_templates(db, tid, members)
    _admin_audit(
        "forge_project.apply_team",
        f"forge/projects/{sid}",
        tid,
        actor=actor,
        meta={"members": members},
    )
    return {"ok": True, "tenant_id": tid, "members": members}


def _kanban_status_from_audit(status: str, age_seconds: float) -> str:
    """Map latest task_audit_log row to kanban column id."""
    st = (status or "").strip().upper()
    if age_seconds < 30 * 60:
        return "en_progreso"
    if st == "SUCCESS":
        return "completo"
    return "pendiente"


def _resolve_kanban_worker_ids(
    workers: str | None,
    tenant_id: str | None,
) -> list[str]:
    raw_ids = [re.sub(r"[^a-zA-Z0-9_-]", "", w.strip()) for w in (workers or "").split(",")]
    worker_ids = [w for w in raw_ids if w]
    if not worker_ids:
        team_ctx = _playground_team_context(tenant_id=tenant_id)
        worker_ids = list(team_ctx.get("workers") or [])
    return worker_ids


def _kanban_audit_states_by_worker(worker_ids: list[str]) -> dict[str, str]:
    from datetime import datetime, timezone

    from duckclaw.gateway_db import GatewayDbEphemeralReadonly, get_gateway_db_path

    states: dict[str, str] = {w: "pendiente" for w in worker_ids}
    if not worker_ids:
        return states
    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        return states
    db = GatewayDbEphemeralReadonly(gw)
    now = datetime.now(timezone.utc)
    in_list = ", ".join("'" + w.replace("'", "''") + "'" for w in worker_ids)
    try:
        rows = db.query(
            f"""
            SELECT worker_id, status, created_at
            FROM task_audit_log
            WHERE worker_id IN ({in_list})
            ORDER BY created_at DESC
            """
        )
    except Exception:
        return states
    seen: set[str] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        wid = str(row.get("worker_id") or "").strip()
        if not wid or wid in seen:
            continue
        seen.add(wid)
        created = row.get("created_at")
        age_seconds = 999999.0
        if created is not None:
            try:
                if hasattr(created, "tzinfo") and created.tzinfo is None:
                    created = created.replace(tzinfo=timezone.utc)
                age_seconds = max(0.0, (now - created).total_seconds())
            except Exception:
                age_seconds = 999999.0
        states[wid] = _kanban_status_from_audit(str(row.get("status") or ""), age_seconds)
    return states


def _kanban_instance_key(worker_id: str, slot: int) -> str:
    return f"{worker_id}:{slot}"


@router.get("/kanban/worker-states", dependencies=[Depends(_require_admin_key)])
async def kanban_worker_states(
    workers: str | None = Query(None, description="Comma-separated worker ids"),
    tenant_id: str | None = Query(None),
) -> dict[str, Any]:
    """
    Latest task_audit_log status per worker for Tablero sync (/workers team).
    Incluye claves compuestas ``{worker_id}:1`` (slot base) además de ``{worker_id}``.
    """
    worker_ids = _resolve_kanban_worker_ids(workers, tenant_id)
    if not worker_ids:
        return {"workers": [], "states": {}}
    audit = _kanban_audit_states_by_worker(worker_ids)
    states: dict[str, str] = dict(audit)
    for wid, st in audit.items():
        states[_kanban_instance_key(wid, 1)] = st
    return {"workers": worker_ids, "states": states}


@router.get("/kanban/swarm-slots", dependencies=[Depends(_require_admin_key)])
async def kanban_swarm_slots(
    workers: str | None = Query(None, description="Comma-separated worker ids"),
    tenant_id: str | None = Query(None),
) -> dict[str, Any]:
    """
    Instancias swarm activas (Redis) y estados por ``{worker_id}:{slot}`` para el Tablero.
    """
    from duckclaw.graphs.subagent_run_id import list_active_swarm_slots

    worker_ids = _resolve_kanban_worker_ids(workers, tenant_id)
    if not worker_ids:
        return {"workers": [], "instances": [], "states": {}}

    tid = _gateway_effective_tenant_id(tenant_id)
    raw_slots = list_active_swarm_slots(tid, worker_ids)
    audit = _kanban_audit_states_by_worker(worker_ids)

    active_by_worker: dict[str, set[int]] = {w: set() for w in worker_ids}
    instances: list[dict[str, Any]] = []
    for row in raw_slots:
        wid = str(row.get("worker_id") or "").strip()
        slot = int(row.get("slot") or 0)
        if not wid or slot < 1:
            continue
        active_by_worker.setdefault(wid, set()).add(slot)
        instances.append(
            {
                "worker_id": wid,
                "slot": slot,
                "chat_scope": row.get("chat_scope"),
                "started_at": row.get("started_at"),
                "active": True,
            }
        )

    states: dict[str, str] = {}
    for wid in worker_ids:
        key1 = _kanban_instance_key(wid, 1)
        if 1 in active_by_worker.get(wid, set()):
            states[key1] = "en_progreso"
        else:
            states[key1] = audit.get(wid, "pendiente")
        for slot in sorted(active_by_worker.get(wid, set())):
            if slot >= 2:
                states[_kanban_instance_key(wid, slot)] = "en_progreso"

    return {"workers": worker_ids, "instances": instances, "states": states}


def _worker_has_browser_sandbox(worker_id: str) -> bool:
    from duckclaw.workers.manifest import load_manifest

    wid = re.sub(r"[^a-zA-Z0-9_-]", "", (worker_id or "").strip())
    if not wid:
        return False
    try:
        spec = load_manifest(wid)
        return bool(getattr(spec, "browser_sandbox", False))
    except Exception:
        return False


def _iter_template_ids_for_catalog() -> list[str]:
    from duckclaw.workers.template_registry import list_template_ids

    return list_template_ids()


def _manifest_display_fields(template_id: str) -> tuple[str, str]:
    """Nombre y subtítulo desde manifest.yaml (sin listas fijas en código)."""
    import yaml

    manifest = _templates_dir() / template_id / "manifest.yaml"
    name = template_id
    subtitle = f"Plantilla forge/templates/{template_id}"
    if not manifest.is_file():
        return name, subtitle
    try:
        raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        if isinstance(raw, dict):
            name = str(raw.get("name") or raw.get("id") or template_id)
            desc = raw.get("description") or raw.get("subtitle")
            if isinstance(desc, str) and desc.strip():
                subtitle = desc.strip()
    except Exception:
        pass
    return name, subtitle


def _catalog_starter_items() -> list[dict[str, str]]:
    """Starters del wizard: solo plantillas presentes en disco."""
    starters: list[dict[str, str]] = []
    for tid in _iter_template_ids_for_catalog():
        if tid in _CATALOG_STARTER_SKIP:
            continue
        name, subtitle = _manifest_display_fields(tid)
        starters.append({"id": tid, "name": name, "path": tid, "subtitle": subtitle})
    starters.sort(key=lambda x: (x["id"] != "default", str(x.get("name") or x["id"]).lower()))
    return starters


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
) -> dict[str, Any]:
    """Bóveda efectiva: body > meta conversación > worker/activa."""
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
    ro = read_only
    if read_only and spawn_inline_writes_enabled():
        try:
            gw = resolve_env_duckdb_path(get_gateway_db_path())
            if Path(abs_path).resolve() == Path(gw).resolve():
                ro = False
        except OSError:
            pass
    return DuckClaw(abs_path, read_only=ro, engine="python")


def _sandbox_chat_policy_payload(
    *,
    chat_id: str,
    worker_id: str,
    vault_path: str,
    tenant_id: str,
) -> dict[str, Any]:
    from duckclaw.forge.schema import resolve_sandbox_network_policy
    from duckclaw.graphs.on_the_fly_commands import get_chat_state
    from duckclaw.workers.manifest import load_manifest

    db = _open_playground_vault_db(vault_path, read_only=True)
    try:
        raw_net = get_chat_state(db, chat_id, "sandbox_network_enabled")
        raw_sb = get_chat_state(db, chat_id, "sandbox_enabled")
    finally:
        db.close()

    _, meta = resolve_sandbox_network_policy(worker_id, raw_net or None)
    browser_sandbox = False
    try:
        browser_sandbox = bool(load_manifest(worker_id).browser_sandbox)
    except Exception:
        browser_sandbox = False

    return {
        "chat_id": chat_id,
        "worker_id": worker_id,
        "tenant_id": tenant_id,
        "vault_path": vault_path,
        "sandbox_enabled": (raw_sb or "").strip().lower() in ("true", "1", "on", "yes", "si", "sí"),
        "sandbox_network_enabled": (raw_net or "").strip().lower() or None,
        "yaml_network_default": meta.get("yaml_default"),
        "effective_network": meta.get("effective"),
        "network_toggle_available": bool(meta.get("toggle_available")),
        "browser_sandbox": browser_sandbox,
    }


@router.get("/sandbox/chat-policy", dependencies=[Depends(_require_admin_key)])
async def admin_sandbox_chat_policy(
    chat_id: str = Query(..., min_length=1, max_length=128),
    worker_id: str | None = Query(None, max_length=64),
    tenant_id: str | None = Query(None, max_length=64),
) -> dict[str, Any]:
    """Estado sandbox + red efectiva para un chat del admin playground."""
    team_ctx = _playground_team_context(tenant_id=tenant_id, chat_id=chat_id)
    if not team_ctx.get("authorized"):
        raise _problem(403, "No autorizado", str(team_ctx.get("team_hint") or ""))

    wid = _pick_playground_worker(team_ctx, worker_id)

    try:
        vault_path = _playground_vault_db_path(team_ctx, wid)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc

    return _sandbox_chat_policy_payload(
        chat_id=chat_id.strip(),
        worker_id=wid,
        vault_path=vault_path,
        tenant_id=str(team_ctx.get("tenant_id") or "default"),
    )


@router.post("/sandbox/network", dependencies=[Depends(_require_admin_key)])
async def admin_sandbox_network_toggle(body: SandboxNetworkBody) -> dict[str, Any]:
    """Activa/desactiva internet en sandbox para un chat (respeta security_policy.yaml)."""
    from duckclaw.forge.schema import resolve_sandbox_network_policy
    from duckclaw.graphs.on_the_fly_commands import get_chat_state, set_chat_state_via_vault
    from duckclaw.graphs.sandbox import cleanup_sandbox_session_for_chat

    team_ctx = _playground_team_context(tenant_id=body.tenant_id, chat_id=body.chat_id)
    if not team_ctx.get("authorized"):
        raise _problem(403, "No autorizado", str(team_ctx.get("team_hint") or ""))

    chat_raw = body.chat_id.strip()
    wid = _pick_playground_worker(team_ctx, body.worker_id)

    try:
        vault_path = _playground_vault_db_path(team_ctx, wid)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc

    db = _open_playground_vault_db(vault_path, read_only=True)
    try:
        raw_prev = get_chat_state(db, chat_raw, "sandbox_network_enabled")
        _, meta = resolve_sandbox_network_policy(wid, raw_prev or None)
        if not meta.get("toggle_available"):
            raise _problem(
                400,
                "Worker sin red en política",
                f"«{wid}» tiene network.default=deny en security_policy.yaml. "
                "Elige un worker con red habilitada en su política o ajusta el manifest.",
            )
        tid = str(team_ctx.get("tenant_id") or "default").strip() or "default"
        val = "true" if body.enabled else "false"
        ok, err = set_chat_state_via_vault(
            db, chat_raw, "sandbox_network_enabled", val, tenant_id=tid
        )
    finally:
        db.close()

    if not ok:
        raise _problem(500, "No se pudo persistir", err or "set_chat_state_via_vault failed")

    cleanup_sandbox_session_for_chat(chat_raw)
    policy = _sandbox_chat_policy_payload(
        chat_id=chat_raw,
        worker_id=wid,
        vault_path=vault_path,
        tenant_id=str(team_ctx.get("tenant_id") or "default"),
    )
    return {"ok": True, "recreated": True, **policy}


@router.get("/sandbox/status", dependencies=[Depends(_require_admin_key)])
async def admin_sandbox_status() -> dict[str, Any]:
    """Requisitos Docker/noVNC para la pestaña VNC del admin."""
    from duckclaw.graphs.sandbox import sandbox_runtime_status

    st = sandbox_runtime_status()
    ready = bool(st.get("docker_available")) and bool(st.get("publish_novnc"))
    hints: list[str] = []
    if not st.get("docker_available"):
        hints.append("Docker no disponible en el host del gateway.")
    if not st.get("publish_novnc"):
        hints.append("Define STRIX_BROWSER_PUBLISH_NOVNC=1 y reinicia DuckClaw-Gateway.")
    if not st.get("public_url"):
        hints.append(
            "Sin DUCKCLAW_PUBLIC_URL: el iframe usará http://127.0.0.1:<puerto> (solo mismo host)."
        )
    return {"ready": ready, "hints": hints, **st}


@router.get("/sandbox/sessions", dependencies=[Depends(_require_admin_key)])
async def admin_sandbox_sessions() -> dict[str, Any]:
    """Contenedores strix_sandbox_* y sesiones noVNC activas."""
    from duckclaw.graphs.sandbox import list_strix_sandbox_containers

    containers = list_strix_sandbox_containers()
    return {"containers": containers, "count": len(containers)}


@router.post("/sandbox/novnc/prepare", dependencies=[Depends(_require_admin_key)])
async def admin_sandbox_novnc_prepare(body: NovncPrepareBody) -> dict[str, Any]:
    """Levanta o reutiliza browser sandbox y devuelve URL noVNC para el admin."""
    from duckclaw.graphs.novnc_registry import (
        get_session_expires_at,
        sanitize_chat_to_session_id,
        touch,
    )
    from duckclaw.graphs.sandbox import ensure_browser_novnc_session, sandbox_runtime_status

    st = sandbox_runtime_status()
    if not st.get("docker_available"):
        raise _problem(503, "Docker no disponible", "El gateway no puede contactar Docker.")
    if not st.get("publish_novnc"):
        raise _problem(
            503,
            "noVNC deshabilitado",
            "STRIX_BROWSER_PUBLISH_NOVNC no está activo en el proceso del gateway.",
        )

    team_ctx = _playground_team_context(tenant_id=body.tenant_id)
    chat_raw = (body.chat_id or team_ctx.get("team_chat_id") or "admin-playground").strip()
    session_id = sanitize_chat_to_session_id(chat_raw)
    wid = _pick_playground_worker(team_ctx, body.worker_id, require_browser_sandbox=True)
    if not _worker_has_browser_sandbox(wid):
        raise _problem(
            400,
            "Worker sin browser sandbox",
            f"El worker '{wid}' no tiene browser_sandbox: true en manifest.yaml.",
        )

    policy_db = None
    try:
        vp = _playground_vault_db_path(team_ctx, wid)
        policy_db = _open_playground_vault_db(vp, read_only=True)
    except Exception:
        policy_db = None
    try:
        vnc_url = ensure_browser_novnc_session(
            wid,
            session_id,
            db=policy_db,
            chat_id=chat_raw,
        )
    finally:
        if policy_db is not None:
            try:
                policy_db.close()
            except Exception:
                pass
    if not vnc_url:
        raise _problem(
            503,
            "No se pudo preparar noVNC",
            "Revisa logs del gateway, imagen duckclaw/browser-env y política del worker.",
        )
    import time as _time

    touch(session_id)
    expires_at = get_session_expires_at(session_id)
    return {
        "session_id": session_id,
        "chat_id": chat_raw,
        "worker_id": wid,
        "vnc_url": vnc_url,
        "expires_at": expires_at,
        "seconds_remaining": max(0.0, float(expires_at or 0) - _time.time()) if expires_at else None,
    }


class DuckdbQueryBody(BaseModel):
    query: str = Field(..., min_length=1)
    vault_path: str | None = None


class DuckdbVectorSearchBody(BaseModel):
    query: str = ""
    limit: int = Field(default=10, ge=1, le=40)
    vault_path: str | None = None


def _duckdb_readonly_session(vault_path: str | None):
    from core.admin_duckdb_readonly import connect_readonly, resolve_vault_path

    path = resolve_vault_path(vault_path)
    con = connect_readonly(path)
    return con, path


@router.get("/duckdb/tables", dependencies=[Depends(_require_admin_key)])
async def duckdb_list_tables(
    vault_path: str | None = Query(None, description="Ruta .duckdb; default gateway vault"),
) -> dict[str, Any]:
    from core.admin_duckdb_readonly import fetch_table_catalog

    try:
        con, resolved = _duckdb_readonly_session(vault_path)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    try:
        catalog = fetch_table_catalog(con)
        return {"vault_path": resolved, **catalog}
    finally:
        con.close()


@router.post("/duckdb/query", dependencies=[Depends(_require_admin_key)])
async def duckdb_run_query(body: DuckdbQueryBody) -> dict[str, Any]:
    from core.admin_duckdb_readonly import execute_select

    try:
        con, resolved = _duckdb_readonly_session(body.vault_path)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    try:
        try:
            result = execute_select(con, body.query)
        except ValueError as exc:
            raise _problem(400, "Consulta no permitida", str(exc)) from exc
        except Exception as exc:
            raise _problem(400, "Error SQL", str(exc)) from exc
        return {"vault_path": resolved, **result}
    finally:
        con.close()


@router.get("/duckdb/pgq-graph", dependencies=[Depends(_require_admin_key)])
async def duckdb_pgq_graph(
    vault_path: str | None = Query(None),
) -> dict[str, Any]:
    from core.admin_duckdb_readonly import fetch_pgq_graph

    try:
        con, resolved = _duckdb_readonly_session(vault_path)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    try:
        graph = fetch_pgq_graph(con)
        return {"vault_path": resolved, **graph}
    finally:
        con.close()


@router.post("/duckdb/vector-search", dependencies=[Depends(_require_admin_key)])
async def duckdb_vector_search(body: DuckdbVectorSearchBody) -> dict[str, Any]:
    from core.admin_duckdb_readonly import (
        SemanticMemoryNotInitializedError,
        run_vector_search,
    )

    try:
        con, resolved = _duckdb_readonly_session(body.vault_path)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    try:
        try:
            payload = run_vector_search(con, body.query, body.limit)
        except SemanticMemoryNotInitializedError as exc:
            raise _problem(400, "Memoria vectorial no inicializada", str(exc)) from exc
        except Exception as exc:
            raise _problem(400, "Error en búsqueda vectorial", str(exc)) from exc
        return {"vault_path": resolved, **payload}
    finally:
        con.close()


from routers.admin_train import router as _admin_train_router  # noqa: E402

router.include_router(_admin_train_router)
