"""
Admin API — consola DuckClaw (spec: specs/features/platform/DUCKCLAW_ADMIN_UI.md).

CRUD plantillas en disco, .env enmascarado, runtime agent_config, whitelist Telegram, historial Redis.
"""
from __future__ import annotations

import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_EDITABLE_SUFFIXES = frozenset({".yaml", ".yml", ".md", ".sql", ".py", ".txt", ".json"})
_PROTECTED_TEMPLATE_IDS = frozenset({"entry_router", "manager_router"})
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
            team_hint = "Equipo de este chat (/workers en Telegram)"
        elif get_tenant_team_templates(db, tid):
            team_source = "tenant"
            team_hint = f"Equipo del tenant «{tid}»"
        elif (os.environ.get("DUCKCLAW_GATEWAY_TEAM_TEMPLATES") or "").strip():
            team_source = "env"
            team_hint = "Equipo desde DUCKCLAW_GATEWAY_TEAM_TEMPLATES"
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
        description="Preset de habilidades (support, finanz, etc.). El disco siempre clona desde templates/default.",
    )
    name: str = ""
    description: str = ""
    skills: list[str] = Field(default_factory=list)
    topology: str = "general"
    system_prompt: str = ""
    soul: str = ""


class PlaygroundChatBody(BaseModel):
    worker_id: str = Field(default="default", max_length=64)
    message: str = Field(..., min_length=1, max_length=16000)
    chat_id: str = Field(default="admin-playground", max_length=128)
    tenant_id: str = Field(default="default", max_length=64)
    telegram_user_id: str | None = Field(
        default=None,
        max_length=32,
        description="ID Telegram para whitelist y equipo /workers (default: DUCKCLAW_OWNER_ID)",
    )
    stream: bool = Field(
        default=False,
        description="Si true, respuesta text/event-stream (tokens SSE + [DONE]).",
    )


class EnvPatchBody(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


class TelegramRouteInput(BaseModel):
    bot: str = Field(..., min_length=1, max_length=64)
    path: str = Field(..., min_length=8, max_length=256)
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


def _llm_keys_configured(env_keys: list[str]) -> bool:
    for k in env_keys:
        if (os.environ.get(k) or "").strip():
            return True
    return len(env_keys) == 0


@router.get("/playground/config", dependencies=[Depends(_require_admin_key)])
async def playground_config(
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
    workers: list[str] = team_ctx.get("workers") or []
    llm = _resolved_llm_env()
    active = llm.get("provider", "")
    catalog = []
    for item in _LLM_PROVIDER_CATALOG:
        row = dict(item)
        row["active"] = row["id"] == active
        row["keys_ok"] = _llm_keys_configured(row.get("env_keys") or [])
        catalog.append(row)
    eff_tenant = team_ctx.get("tenant_id") or _gateway_effective_tenant_id("default")
    return {
        "llm": llm,
        "catalog": catalog,
        "workers": workers,
        "env_path": str(_env_file()),
        "effective_tenant_id": eff_tenant,
        "telegram_user_id": team_ctx.get("telegram_user_id"),
        "team_chat_id": team_ctx.get("team_chat_id"),
        "authorized": team_ctx.get("authorized"),
        "whitelist_role": team_ctx.get("whitelist_role"),
        "team_source": team_ctx.get("team_source"),
        "team_hint": team_ctx.get("team_hint"),
        "chat_endpoint": "/api/v1/admin/playground/chat",
        "chat_stream_endpoint": "/api/v1/admin/playground/chat",
        "chat_stream_hint": "POST con stream=true o Accept: text/event-stream",
        "note": "El LLM lo define el .env del gateway (PM2). Reinicia DuckClaw-Gateway tras cambiar proveedor.",
    }


@router.post("/playground/chat", dependencies=[Depends(_require_admin_key)])
async def playground_chat(
    body: PlaygroundChatBody,
    request: Request,
    actor: str = Depends(_actor_from_header),
):
    """Chat de prueba desde consola admin (exento Tailscale vía prefijo /admin/)."""
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", body.worker_id.strip()) or "default"
    msg = body.message.strip()
    if not msg:
        raise _problem(400, "message vacío", body.message)
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
    owner_uid = str(team_ctx.get("telegram_user_id") or "").strip()
    guard_user_id = owner_uid or (actor or "admin-ui")

    from core.models import ChatRequest

    chat = ChatRequest(
        message=msg,
        chat_id=session_id,
        user_id=guard_user_id,
        username=actor or guard_user_id,
        chat_type="private",
        tenant_id=tenant_id,
        stream=body.stream,
    )
    redis_client = getattr(request.app.state, "redis", None)
    accept = (request.headers.get("accept") or "").lower()
    wants_stream = bool(body.stream) or "text/event-stream" in accept

    import main as gateway_main

    from duckclaw.channels import GatewayDeliveryContext

    delivery_context = GatewayDeliveryContext(channel="http")

    try:
        from core.debug_session_log import agent_debug_log

        agent_debug_log(
            "C",
            "admin.py:playground_chat",
            "playground_chat_start",
            {"worker_id": wid, "tenant_id": tenant_id, "stream": wants_stream},
        )
    except Exception:
        pass

    # #region agent log
    try:
        import json as _json
        import time as _time

        with open(
            "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-fd1dbb.log",
            "a",
            encoding="utf-8",
        ) as _df:
            _df.write(
                _json.dumps(
                    {
                        "sessionId": "fd1dbb",
                        "hypothesisId": "A",
                        "location": "admin.py:playground_chat",
                        "message": "playground_invoke",
                        "data": {
                            "session_id": session_id,
                            "team_chat_id": str(team_ctx.get("team_chat_id") or ""),
                            "delivery_channel": "http",
                            "wants_stream": wants_stream,
                        },
                        "timestamp": int(_time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # #endregion

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
                        "token_masked": _mask_secret(r.bot_token),
                    }
                    for r in compact
                ]
            else:
                for part in raw.split(","):
                    part = part.strip()
                    if not part:
                        continue
                    idx = part.rfind(":/api/")
                    if idx < 0:
                        continue
                    prefix = part[:idx]
                    path = part[idx + 1 :].strip()
                    first = prefix.find(":")
                    if first <= 0:
                        continue
                    routes.append(
                        {
                            "bot": prefix[:first].strip().lower(),
                            "path": path,
                            "token_masked": _mask_secret(prefix[first + 1 :].strip()),
                        }
                    )
                fmt = "legacy" if routes else "empty"
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
        route = TelegramCompactWebhookRoute(bot_name=bot, bot_token=token, webhook_path=path)
        try:
            compact_route_to_path_binding(route)
        except ValueError as exc:
            raise _problem(400, "Perfil de bot desconocido", str(exc)) from exc
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
    redis_url = (os.environ.get("REDIS_URL") or "redis://localhost:6379/0").strip()
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
    leila = (os.environ.get("DUCKCLAW_LEILA_FLY_COMMANDS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )
    if leila:
        entries.extend(
            {"cmd": cmd, "description": desc}
            for cmd, desc in load_guardrail_pipe_table("fly_commands", "help_entries_leila")
        )
    return {"header": header, "commands": entries, "leila_enabled": leila}


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
    redis_url = (os.environ.get("REDIS_URL") or "redis://localhost:6379/0").strip()
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
    starters = [
        {
            "id": "default",
            "name": "Asistente en blanco",
            "path": "default",
            "subtitle": "Parte de la plantilla default; tú defines el comportamiento.",
        },
        {
            "id": "industries/business_standard",
            "name": "Asistente de negocio",
            "path": "industries/business_standard",
            "subtitle": "Memoria triple y habilidades enterprise.",
        },
        {
            "id": "support",
            "name": "Atención al cliente",
            "path": "support",
            "subtitle": "Responde dudas frecuentes con tono amable.",
        },
        {
            "id": "research_worker",
            "name": "Investigación y resúmenes",
            "path": "research_worker",
            "subtitle": "Busca información y entrega informes claros.",
        },
        {
            "id": "finanz",
            "name": "Finanzas personales",
            "path": "finanz",
            "subtitle": "Presupuesto y conceptos financieros básicos.",
        },
    ]
    return {"industries": items, "starters": starters}


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
                "id": "axis_orchestrator",
                "label": "AXIS orquestador",
                "description": "Coordina sub-workers vía orchestrator.orchestrates (ej. AXIS-Maestro).",
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
    return {
        "duckclaw_mcp": {
            "command": "uv run python -m duckclaw_mcp --host 0.0.0.0 --port " + mcp_port,
            "url": f"http://127.0.0.1:{mcp_port}/mcp",
            "tools": duckclaw_tools,
            "live": live,
        },
        "stdio_servers": stdio_servers,
        "github_note": "GitHub MCP vía forge/skills/github_bridge.py (Docker)",
    }


_OPS_ALLOWLIST: dict[str, list[str]] = {
    "pm2_list": ["pm2", "list"],
    "pm2_status": ["pm2", "status"],
    "pm2_restart_gateway": ["pm2", "restart", "DuckClaw-Gateway", "--update-env"],
    "pm2_restart_db_writer": ["pm2", "restart", "DuckClaw-DB-Writer", "--update-env"],
    "pm2_logs_gateway": ["pm2", "logs", "DuckClaw-Gateway", "--lines", "40", "--nostream"],
    "pm2_start_mcp": ["pm2", "start", "config/ecosystem.mcp.config.cjs"],
    "pm2_restart_mcp": ["pm2", "restart", "DuckClaw-MCP", "--update-env"],
    "pm2_logs_mcp": ["pm2", "logs", "DuckClaw-MCP", "--lines", "40", "--nostream"],
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
        "pm2_logs_gateway": "Últimas líneas log Gateway",
        "pm2_start_mcp": "Iniciar DuckClaw-MCP (ecosystem.mcp.config.cjs)",
        "pm2_restart_mcp": "Reiniciar DuckClaw-MCP",
        "pm2_logs_mcp": "Últimas líneas log MCP",
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
