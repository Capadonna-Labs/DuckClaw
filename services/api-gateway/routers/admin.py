from __future__ import annotations

import json
import logging
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field, field_validator

from routers.admin_domains.access_management import router as access_management_router
from routers.admin_domains.auth import router as auth_router
from routers.admin_domains.catalog_skills import router as catalog_skills_router
from routers.admin_domains.duckdb_explorer import router as duckdb_explorer_router
from routers.admin_domains.kanban import router as kanban_router
from routers.admin_domains.kanban_runtime import router as kanban_runtime_router
from routers.admin_domains.playground_chat import (
    _open_playground_vault_db,
    _pick_playground_worker,
    _playground_team_context,
    _playground_telegram_user_id,
    _playground_vault_db_path,
)
from routers.admin_domains.playground_chat import router as playground_chat_router
from routers.admin_domains.prompt_policies import router as prompt_policies_router
from routers.admin_domains.runtime_config import router as runtime_config_router
from routers.admin_domains.sandbox_sessions import router as sandbox_sessions_router
from routers.admin_domains.template_contexts import router as template_contexts_router
from routers.admin_domains.templates_catalog import router as templates_catalog_router
from routers.admin_domains.user_agents import router as user_agents_router
from routers.admin_domains.visual_assets import router as visual_assets_router
from routers.admin_domains.workspace_managed_draft import router as workspace_managed_draft_router
from routers.admin_domains.workspace_projects import router as workspace_projects_router

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
router.include_router(access_management_router)
router.include_router(auth_router)
router.include_router(catalog_skills_router)
router.include_router(duckdb_explorer_router)
router.include_router(kanban_router)
router.include_router(kanban_runtime_router)
router.include_router(playground_chat_router)
router.include_router(prompt_policies_router)
router.include_router(runtime_config_router)
router.include_router(sandbox_sessions_router)
router.include_router(template_contexts_router)
router.include_router(templates_catalog_router)
router.include_router(user_agents_router)
router.include_router(visual_assets_router)
router.include_router(workspace_managed_draft_router)
router.include_router(workspace_projects_router)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_EDITABLE_SUFFIXES = frozenset({".yaml", ".yml", ".md", ".sql", ".py", ".txt", ".json"})
_PROTECTED_TEMPLATE_IDS = frozenset({"entry_router", "manager_router"})
_CATALOG_STARTER_SKIP = frozenset({"entry_router", "manager_router", "industries"})
_ENV_ALLOW_PREFIXES = ("TELEGRAM_", "DUCKDB_", "DUCKCLAW_", "LANGCHAIN_", "OPENAI_", "GROQ_", "DEEPSEEK_")
_ENV_ALLOW_EXACT = frozenset({"LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "REDIS_URL"})
_TELEGRAM_WEBHOOK_ROUTES_ENV_KEY = "DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES"
_TELEGRAM_WEBHOOK_ROUTES_DOMAIN = "telegram"
_TELEGRAM_WEBHOOK_ROUTES_KEY = "webhook_routes"
_MCP_PORT_ENV_KEY = "DUCKCLAW_MCP_PORT"
_MCP_PORT_DOMAIN = "mcp"
_MCP_PORT_KEY = "port"


def _repo_root() -> Path:
    raw = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    return Path(raw) if raw else _REPO_ROOT


def _telegram_webhook_routes_runtime_setting() -> dict[str, Any]:
    """Rutas Telegram DB-first con fallback a `.env` bootstrap."""
    raw_env = (
        _read_env_key_unmasked(_TELEGRAM_WEBHOOK_ROUTES_ENV_KEY)
        or os.environ.get(_TELEGRAM_WEBHOOK_ROUTES_ENV_KEY)
        or ""
    ).strip()
    try:
        from core.admin_identity import open_gateway_db
        from duckclaw.admin_runtime_settings import resolve_runtime_setting

        with open_gateway_db(read_only=True) as db:
            resolved = resolve_runtime_setting(
                db,
                tenant_id="global",
                actor_email="",
                domain=_TELEGRAM_WEBHOOK_ROUTES_DOMAIN,
                key=_TELEGRAM_WEBHOOK_ROUTES_KEY,
                env_key=_TELEGRAM_WEBHOOK_ROUTES_ENV_KEY,
                default="",
            )
        return {
            "value": str(resolved.get("value") or raw_env or "").strip(),
            "source": str(resolved.get("source") or ("env" if raw_env else "default")),
        }
    except Exception:
        return {"value": raw_env, "source": "env" if raw_env else "default"}


def _upsert_telegram_webhook_routes_runtime_setting(serialized: str, *, actor: str) -> str:
    from duckclaw.db_write_queue import enqueue_typed_command
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.write_commands import UpsertRuntimeSettingCommand

    command = UpsertRuntimeSettingCommand(
        tenant_id="global",
        actor_email="",
        domain=_TELEGRAM_WEBHOOK_ROUTES_DOMAIN,
        key=_TELEGRAM_WEBHOOK_ROUTES_KEY,
        value=serialized,
        value_kind="string",
        secret=True,
        updated_by=actor,
    )
    task_id = enqueue_typed_command(command, db_path=get_gateway_db_path(), user_id="default")
    return task_id


def _mcp_port_runtime_setting() -> dict[str, str]:
    """Puerto MCP DB-first con fallback `.env` bootstrap."""
    raw_env = (os.environ.get(_MCP_PORT_ENV_KEY) or "8001").strip() or "8001"
    try:
        from core.admin_identity import open_gateway_db
        from duckclaw.admin_runtime_settings import resolve_runtime_setting

        with open_gateway_db(read_only=True) as db:
            resolved = resolve_runtime_setting(
                db,
                tenant_id="global",
                actor_email="",
                domain=_MCP_PORT_DOMAIN,
                key=_MCP_PORT_KEY,
                env_key=_MCP_PORT_ENV_KEY,
                default="8001",
            )
        raw = str(resolved.get("value") or raw_env or "8001").strip() or "8001"
        source = str(resolved.get("source") or ("env" if raw_env else "default"))
    except Exception:
        raw = raw_env
        source = "env" if os.environ.get(_MCP_PORT_ENV_KEY) is not None else "default"
    if not re.fullmatch(r"\d{2,5}", raw):
        raw = "8001"
        source = "default"
    return {"value": raw, "source": source}


def _gateway_effective_tenant_id(request_tenant: str | None) -> str:
    """Misma resolución que ``main._effective_tenant_id`` (p. ej. default → Marco si está en PM2)."""
    import main as gateway_main

    raw = (request_tenant or "").strip() or "default"
    return gateway_main._effective_tenant_id(raw)




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


def _clean_template_card_text(value: str, *, limit: int = 180) -> str:
    text = re.sub(r"```.*?```", " ", value, flags=re.DOTALL)
    text = re.sub(r"^#+\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"[*_`>|-]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _first_useful_markdown_block(path: Path) -> str:
    if not path.is_file():
        return ""
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", raw) if b.strip()]
    for block in blocks:
        if block.startswith("#"):
            continue
        cleaned = _clean_template_card_text(block)
        if len(cleaned) >= 40:
            return cleaned
    return ""


def _template_card_description(template_dir: Path) -> tuple[str, str]:
    manifest = template_dir / "manifest.yaml"
    if manifest.is_file():
        try:
            import yaml

            raw = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
        except Exception:
            raw = {}
        if isinstance(raw, dict):
            for key in ("description", "summary", "purpose", "long_description"):
                value = raw.get(key)
                if isinstance(value, str) and value.strip():
                    return _clean_template_card_text(value), f"manifest.{key}"

    for filename, source in (("soul.md", "soul.md"), ("domain_closure.md", "domain_closure.md")):
        text = _first_useful_markdown_block(template_dir / filename)
        if text:
            return text, source

    return "Sin descripción pública. Añade `description` al manifest o un resumen en `soul.md`.", "missing"


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




class EnvPatchBody(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


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


class AdminLoginBody(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def normalize_email(cls, v: str) -> str:
        return (v or "").strip().lower()

    @field_validator("password")
    @classmethod
    def password_length(cls, v: str) -> str:
        if len(v) < 8 or len(v) > 128:
            raise ValueError("invalid password length")
        return v


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
    """Actor email from header, or DUCKCLAW_ADMIN_EMAIL if header is unset."""
    raw = (x_actor or "").strip()[:128]
    if raw and raw != "admin-ui":
        return raw
    admin_email = os.environ.get("DUCKCLAW_ADMIN_EMAIL", "").strip()
    if admin_email and "@" in admin_email:
        return admin_email[:128]
    return raw or "admin-ui"




@router.get("/health", dependencies=[Depends(_require_admin_key)])
async def admin_health(request: Request) -> dict[str, Any]:
    workers: list[str] = []
    try:
        from core.admin_identity import open_gateway_db
        from duckclaw.admin_worker_catalog import list_visible_workers_for_actor
        from duckclaw.workers.factory import list_workers

        with open_gateway_db(read_only=True) as db:
            actor = (request.headers.get("x-duckclaw-actor") or "").strip().lower()
            if actor and "@" in actor:
                workers = [
                    str(item.get("id") or item.get("worker_id") or "").strip()
                    for item in list_visible_workers_for_actor(db, actor_email=actor)
                    if str(item.get("id") or item.get("worker_id") or "").strip()
                ]
            else:
                workers = list_workers(db=db)
    except Exception as exc:
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


def _overview_usage_metrics(
    db: Any,
    *,
    days: int = 7,
    group_by: str = "worker",
    worker_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Agregados de tokens/USD desde llm_usage_log (tabla opcional)."""
    days_clamped = max(1, min(int(days or 7), 90))
    group = (group_by or "worker").strip().lower()
    if group not in ("worker", "day", "session"):
        group = "worker"

    wid_filter = (worker_id or "").strip().replace("'", "''")
    sid_filter = (session_id or "").strip().replace("'", "''")
    where_parts = [f"created_at >= now() - INTERVAL '{days_clamped} days'"]
    if wid_filter:
        where_parts.append(f"worker_id = '{wid_filter}'")
    if sid_filter:
        where_parts.append(f"session_id = '{sid_filter}'")
    where_sql = " AND ".join(where_parts)

    empty: dict[str, Any] = {
        "summary": {
            "input_tokens": 0,
            "output_tokens": 0,
            "total_tokens": 0,
            "cost_usd": 0.0,
        },
        "series": [],
        "filters": {
            "days": days_clamped,
            "group_by": group,
            "worker_id": wid_filter or None,
            "session_id": sid_filter or None,
        },
        "workers": [],
        "sessions": [],
    }

    try:
        db.query("SELECT 1 FROM main.llm_usage_log LIMIT 1")
    except Exception:
        return empty

    if group == "day":
        series_sql = f"""
            SELECT strftime(created_at, '%Y-%m-%d') AS label,
                   NULL AS worker_id,
                   NULL AS session_id,
                   sum(input_tokens) AS input_tokens,
                   sum(output_tokens) AS output_tokens,
                   sum(total_tokens) AS total_tokens,
                   round(sum(cost_usd), 6) AS cost_usd
            FROM main.llm_usage_log
            WHERE {where_sql}
            GROUP BY label
            ORDER BY label
        """
    elif group == "session":
        series_sql = f"""
            SELECT coalesce(session_id, '(sin id)') AS label,
                   max(worker_id) AS worker_id,
                   session_id,
                   sum(input_tokens) AS input_tokens,
                   sum(output_tokens) AS output_tokens,
                   sum(total_tokens) AS total_tokens,
                   round(sum(cost_usd), 6) AS cost_usd
            FROM main.llm_usage_log
            WHERE {where_sql}
              AND session_id IS NOT NULL AND trim(session_id) != ''
            GROUP BY session_id
            ORDER BY total_tokens DESC
            LIMIT 40
        """
    else:
        series_sql = f"""
            SELECT worker_id AS label,
                   worker_id,
                   NULL AS session_id,
                   sum(input_tokens) AS input_tokens,
                   sum(output_tokens) AS output_tokens,
                   sum(total_tokens) AS total_tokens,
                   round(sum(cost_usd), 6) AS cost_usd
            FROM main.llm_usage_log
            WHERE {where_sql}
              AND worker_id IS NOT NULL AND trim(worker_id) != ''
            GROUP BY worker_id
            ORDER BY total_tokens DESC
        """

    summary_sql = f"""
        SELECT sum(input_tokens) AS input_tokens,
               sum(output_tokens) AS output_tokens,
               sum(total_tokens) AS total_tokens,
               round(sum(cost_usd), 6) AS cost_usd
        FROM main.llm_usage_log
        WHERE {where_sql}
    """
    workers_sql = f"""
        SELECT DISTINCT worker_id
        FROM main.llm_usage_log
        WHERE created_at >= now() - INTERVAL '{days_clamped} days'
          AND worker_id IS NOT NULL AND trim(worker_id) != ''
        ORDER BY worker_id
    """
    sessions_sql = f"""
        SELECT session_id,
               max(worker_id) AS worker_id,
               sum(total_tokens) AS total_tokens,
               round(sum(cost_usd), 6) AS cost_usd
        FROM main.llm_usage_log
        WHERE created_at >= now() - INTERVAL '{days_clamped} days'
          AND session_id IS NOT NULL AND trim(session_id) != ''
        GROUP BY session_id
        ORDER BY total_tokens DESC
        LIMIT 30
    """

    summary_rows = _gateway_db_query_rows(db, summary_sql)
    series_rows = _gateway_db_query_rows(db, series_sql)
    worker_rows = _gateway_db_query_rows(db, workers_sql)
    session_rows = _gateway_db_query_rows(db, sessions_sql)

    summary_row = summary_rows[0] if summary_rows else {}
    try:
        summary = {
            "input_tokens": int(summary_row.get("input_tokens") or 0),
            "output_tokens": int(summary_row.get("output_tokens") or 0),
            "total_tokens": int(summary_row.get("total_tokens") or 0),
            "cost_usd": float(summary_row.get("cost_usd") or 0.0),
        }
    except (TypeError, ValueError):
        summary = empty["summary"]

    series: list[dict[str, Any]] = []
    for row in series_rows:
        label = str(row.get("label") or "").strip()
        if not label:
            continue
        try:
            series.append(
                {
                    "label": label,
                    "worker_id": row.get("worker_id"),
                    "session_id": row.get("session_id"),
                    "input_tokens": int(row.get("input_tokens") or 0),
                    "output_tokens": int(row.get("output_tokens") or 0),
                    "total_tokens": int(row.get("total_tokens") or 0),
                    "cost_usd": float(row.get("cost_usd") or 0.0),
                }
            )
        except (TypeError, ValueError):
            continue

    workers = [
        str(r.get("worker_id") or "").strip()
        for r in worker_rows
        if str(r.get("worker_id") or "").strip()
    ]
    sessions: list[dict[str, Any]] = []
    for row in session_rows:
        sid = str(row.get("session_id") or "").strip()
        if not sid:
            continue
        try:
            sessions.append(
                {
                    "session_id": sid,
                    "worker_id": row.get("worker_id"),
                    "total_tokens": int(row.get("total_tokens") or 0),
                    "cost_usd": float(row.get("cost_usd") or 0.0),
                }
            )
        except (TypeError, ValueError):
            continue

    return {
        "summary": summary,
        "series": series,
        "filters": empty["filters"],
        "workers": workers,
        "sessions": sessions,
    }


@router.get("/overview/metrics", dependencies=[Depends(_require_admin_key)])
async def admin_overview_metrics(
    usage_days: int = 7,
    usage_group_by: str = "worker",
    worker_id: str | None = None,
    session_id: str | None = None,
) -> dict[str, Any]:
    """Agregados analíticos: uso LLM (tokens/USD), actividad 7d y latencia 24h."""
    from duckclaw.gateway_db import GatewayDbEphemeralReadonly, get_gateway_db_path

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(503, "Gateway DuckDB no disponible", gw or "missing")

    db = GatewayDbEphemeralReadonly(gw)
    usage = _overview_usage_metrics(
        db,
        days=usage_days,
        group_by=usage_group_by,
        worker_id=worker_id,
        session_id=session_id,
    )
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

    return {"usage": usage, "activity": activity, "latency": latency, "db_path": gw}


async def _list_templates_impl(
    include_inactive: bool = Query(False),
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import list_templates_payload, open_gateway_db

    with open_gateway_db(read_only=True) as db:
        items = list_templates_payload(db, actor_email=actor, include_inactive=include_inactive)
    return {"templates": items}


async def _get_template_impl(
    worker_id: str,
    include_content: bool = True,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import catalog_template_detail, open_gateway_db

    with open_gateway_db(read_only=True) as db:
        detail = catalog_template_detail(db, actor_email=actor, worker_id=worker_id)
    if detail is None:
        raise _problem(404, "Plantilla no encontrada o no asignada al catálogo", worker_id)
    if not include_content:
        detail = {**detail, "contents": {}}
    return detail


async def _put_template_file_impl(
    worker_id: str,
    file_path: str,
    body: FileWriteBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    raise _problem(
        410,
        "Mutación legacy de template retirada",
        "Usa routers.admin_domains.templates_catalog y comandos tipados DB-first.",
    )


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


async def _template_vault_options_impl(
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


async def _get_template_vault_binding_impl(
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


async def _put_template_vault_binding_impl(
    worker_id: str,
    body: VaultBindingPutBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    raise _problem(
        410,
        "Vault binding filesystem retirado",
        "Importa el worker al catálogo DB-first y administra contexto desde DuckDB.",
    )


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


async def _create_template_impl(
    body: TemplateCreateBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    raise _problem(
        410,
        "Creación filesystem de templates retirada",
        "Usa el flujo administrado de workspace o importa templates existentes al catálogo DB-first.",
    )


async def _delete_template_impl(
    worker_id: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    raise _problem(
        410,
        "Mutación legacy de template retirada",
        "Usa routers.admin_domains.templates_catalog y comandos tipados DB-first.",
    )


async def _reactivate_template_impl(
    worker_id: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    raise _problem(
        410,
        "Mutación legacy de template retirada",
        "Usa routers.admin_domains.templates_catalog y comandos tipados DB-first.",
    )


async def _hard_delete_template_impl(
    worker_id: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    raise _problem(
        410,
        "Mutación legacy de template retirada",
        "Usa routers.admin_domains.templates_catalog y comandos tipados DB-first.",
    )


async def _validate_template_impl(worker_id: str) -> dict[str, Any]:
    raise _problem(
        410,
        "Validación filesystem retirada",
        "La validación operativa se realiza sobre snapshots DB-first del catálogo.",
    )


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
    raise _problem(
        410,
        "Edición genérica de .env retirada",
        "Usa Runtime Settings para configuración visible y Secret Settings para API keys.",
    )


@router.get("/telegram/routes", dependencies=[Depends(_require_admin_key)])
async def get_telegram_routes() -> dict[str, Any]:
    from duckclaw.integrations.telegram.compact_webhook_routes import (
        parse_compact_telegram_webhook_routes,
    )

    resolved = _telegram_webhook_routes_runtime_setting()
    raw = str(resolved.get("value") or "").strip()
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
                    "known_bots": [],
                    "source": resolved.get("source", "default"),
                    "runtime_key": "telegram.webhook_routes",
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
        "known_bots": [str(route.get("bot") or "") for route in routes],
        "source": resolved.get("source", "default"),
        "runtime_key": "telegram.webhook_routes",
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

    current = _telegram_webhook_routes_runtime_setting()
    current_raw = str(current.get("value") or "").strip()
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

    task_id = _upsert_telegram_webhook_routes_runtime_setting(serialized, actor=actor)
    _admin_audit("telegram.routes.put", "telegram.webhook_routes", f"{len(built)} rutas", actor=actor)
    return {
        "ok": True,
        "updated": ["telegram.webhook_routes"],
        "task_id": task_id,
        "source": "db",
        "route_count": len(built),
        "restart_hint": "Reinicia DuckClaw-Gateway para registrar rutas dinámicas DB-first",
    }




async def _admin_auth_login_impl(body: Any, request: Request, response: Response) -> dict[str, Any]:
    from core.admin_auth import (
        apply_login_delay,
        check_ip_rate_limit,
        clear_email_failures,
        client_ip,
        create_session,
        record_email_failure,
        set_auth_cookies,
    )
    from duckclaw import DuckClaw
    from duckclaw import db_write_queue
    from duckclaw.admin_console_users import (
        authenticate_console_user_readonly,
        console_users_seed_required,
        default_seed_users,
    )
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.write_commands import (
        ClearAdminLoginFailuresCommand,
        RecordAdminLoginFailureCommand,
        UpdateConsoleUserPasswordHashCommand,
        UpsertConsoleUserCommand,
    )

    redis_client = getattr(request.app.state, "redis", None)
    ip = client_ip(request)
    if redis_client is not None:
        await check_ip_rate_limit(redis_client, ip)
        await apply_login_delay(redis_client, body.email)

    gw = (get_gateway_db_path() or "").strip()
    if not gw or not os.path.isfile(gw):
        raise _problem(503, "Gateway DuckDB no disponible", gw)

    from core.admin_identity import attach_profile_to_console_user, console_user_public

    def _enqueue_auth_command(command: Any) -> str:
        task_id = db_write_queue.enqueue_typed_command(command, db_path=gw, user_id="default")
        command_status = db_write_queue.poll_task_status_sync(task_id, timeout_sec=0.5, interval_sec=0.05)
        if command_status and command_status.status == "failed":
            raise RuntimeError(command_status.detail or "admin auth write failed")
        return task_id

    db = DuckClaw(gw, read_only=True, engine="python")
    should_seed = False
    try:
        should_seed = console_users_seed_required(db)
    finally:
        db.close()

    if should_seed:
        for seed_user in default_seed_users():
            _enqueue_auth_command(
                UpsertConsoleUserCommand(
                    tenant_id="default",
                    actor_email="system",
                    email=seed_user["email"],
                    nombre=seed_user.get("nombre") or seed_user["email"],
                    rol=seed_user.get("rol") or "user",
                    password=seed_user.get("password") or "",
                    initials=seed_user.get("initials") or "",
                    active=True,
                )
            )

    db = DuckClaw(gw, read_only=True, engine="python")
    user: dict[str, Any] | None = None
    password_update: dict[str, Any] | None = None
    try:
        user, password_update = authenticate_console_user_readonly(
            db, email=body.email, password=body.password
        )
        if user:
            user = attach_profile_to_console_user(db, user)
    finally:
        db.close()

    if not user:
        try:
            _enqueue_auth_command(
                RecordAdminLoginFailureCommand(
                    tenant_id="default",
                    actor_email="system",
                    email=body.email,
                )
            )
        except RuntimeError as exc:
            raise _problem(503, "DB-writer rechazó fallo de login", str(exc)) from exc
        if redis_client is not None:
            await record_email_failure(redis_client, body.email)
        raise HTTPException(status_code=401, detail="Invalid credentials")

    try:
        if password_update:
            _enqueue_auth_command(
                UpdateConsoleUserPasswordHashCommand(
                    tenant_id="default",
                    actor_email=str(user.get("email") or "system"),
                    email=str(password_update.get("email") or body.email),
                    password_hash=str(password_update.get("password_hash") or ""),
                    hash_algo=str(password_update.get("hash_algo") or "argon2id"),
                    hash_params=dict(password_update.get("hash_params") or {}),
                )
            )
        _enqueue_auth_command(
            ClearAdminLoginFailuresCommand(
                tenant_id="default",
                actor_email=str(user.get("email") or "system"),
                email=body.email,
            )
        )
    except RuntimeError as exc:
        raise _problem(503, "DB-writer rechazó estado de login", str(exc)) from exc

    if redis_client is None:
        raise _problem(503, "Redis no disponible para sesiones", "redis")
    await clear_email_failures(redis_client, body.email)
    session_id, csrf_token = await create_session(redis_client, user=user)
    set_auth_cookies(response, session_id, csrf_token, request=request)
    logging.getLogger(__name__).info("login_success email=%s ip=%s", body.email, ip)
    return {"user": console_user_public(user)}


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


@router.get("/fly-commands", dependencies=[Depends(_require_admin_key)])
async def list_fly_commands() -> dict[str, Any]:
    from duckclaw.guardrails.loader import load_guardrail, load_guardrail_pipe_table

    header = load_guardrail("fly_commands", "help_header")
    entries = [
        {"cmd": cmd, "description": desc}
        for cmd, desc in load_guardrail_pipe_table("fly_commands", "help_entries")
    ]
    return {"header": header, "commands": entries}


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
    mcp_port_setting = _mcp_port_runtime_setting()
    mcp_port = mcp_port_setting["value"]
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
            "port": mcp_port,
            "source": mcp_port_setting["source"],
            "runtime_key": "mcp.port",
            "tools": duckclaw_tools,
            "live": live,
        },
        "stdio_servers": stdio_servers,
        "official_reference": official_reference,
        "github_note": "GitHub MCP vía duckclaw.github.mcp_bridge (Docker)",
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
    raise _problem(
        410,
        "Forge Projects legacy retirado",
        "Usa /workspace/projects y el flujo administrado de workspace DB-first.",
    )


@router.get("/forge-projects/env-presets", dependencies=[Depends(_require_admin_key)])
async def forge_project_env_presets() -> dict[str, Any]:
    raise _problem(
        410,
        "Presets DUCKCLAW_TEAM_* retirados",
        "Usa proyectos DB-first y asignaciones admin_project_agents.",
    )


@router.get("/forge-projects/{slug}", dependencies=[Depends(_require_admin_key)])
async def get_forge_project(slug: str) -> dict[str, Any]:
    raise _problem(410, "Forge Projects legacy retirado", slug)


@router.post("/forge-projects", dependencies=[Depends(_require_admin_key)])
async def create_forge_project(
    body: ForgeProjectCreateBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    raise _problem(
        410,
        "Forge Projects legacy retirado",
        "Crea proyectos desde /workspace/projects o el flujo administrado de workspace.",
    )


@router.patch("/forge-projects/{slug}", dependencies=[Depends(_require_admin_key)])
async def patch_forge_project(
    slug: str,
    body: ForgeProjectPatchBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    raise _problem(410, "Forge Projects legacy retirado", slug)


@router.delete("/forge-projects/{slug}", dependencies=[Depends(_require_admin_key)])
async def delete_forge_project(
    slug: str,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    raise _problem(410, "Forge Projects legacy retirado", slug)


@router.post("/forge-projects/{slug}/apply-team", dependencies=[Depends(_require_admin_key)])
async def apply_forge_project_team(
    slug: str,
    tenant_id: str = Query("default"),
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    raise _problem(
        410,
        "Team templates legacy retirado",
        "Usa admin_project_agents en Proyectos DB-first.",
    )


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




@router.get("/meditate/status", dependencies=[Depends(_require_admin_key)])
def admin_meditate_status(
    tenant_id: str = Query("default"),
    worker_id: str = Query(""),
) -> dict[str, Any]:
    """Último run meditate, distance_vector y estado del circuit breaker."""
    from harness_core.skills.emit_correction_delta import circuit_breaker_redis_key, is_circuit_breaker_active

    tid = (tenant_id or "default").strip() or "default"
    wid = (worker_id or "").strip()
    last_run: dict[str, Any] | None = None
    try:
        from core.admin_identity import open_gateway_db

        with open_gateway_db(read_only=True) as db:
            esc = tid.replace("'", "''")
            raw = db.query(
                "SELECT run_id, distance_vector, actions_json, status, created_at "
                "FROM harness_core.meditate_runs "
                f"WHERE tenant_id = '{esc}' "
                "ORDER BY created_at DESC LIMIT 1"
            )
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
            if rows and isinstance(rows[0], dict):
                last_run = rows[0]
    except Exception as exc:
        last_run = {"error": str(exc)}

    cb_active = is_circuit_breaker_active(tid, wid) if wid else False
    return {
        "tenant_id": tid,
        "worker_id": wid or None,
        "circuit_breaker_active": cb_active,
        "circuit_breaker_key": circuit_breaker_redis_key(tid, wid) if wid else None,
        "last_run": last_run,
    }


class AdminMeditateTickBody(BaseModel):
    tenant_id: str = "default"
    worker_id: str
    vault_db_path: str = ""
    chat_id: str = "admin"
    delta_interval_seconds: int = Field(default=14400, ge=60)


@router.post("/meditate/tick", dependencies=[Depends(_require_admin_key)])
def admin_meditate_tick(body: AdminMeditateTickBody) -> dict[str, Any]:
    """Disparo manual del grafo meditate (admin)."""
    from harness_core.graphs.meditate_graph import invoke_meditate_run
    from harness_core.states.meditate_state import HomeostasisTarget
    from harness_core.targets import load_homeostasis_targets

    tid = (body.tenant_id or "default").strip() or "default"
    wid = (body.worker_id or "").strip()
    if not wid:
        raise _problem(400, "worker_id requerido", "Indica worker_id en el body.")

    vault = (body.vault_db_path or "").strip()
    if not vault:
        try:
            from duckclaw.gateway_db import get_gateway_db_path

            vault = get_gateway_db_path()
        except Exception as exc:
            raise _problem(400, "vault_db_path", str(exc)) from exc

    targets_obj = HomeostasisTarget()
    try:
        from duckclaw import DuckClaw

        with DuckClaw(vault, read_only=True) as db:
            targets_obj = load_homeostasis_targets(db, tid)
    except Exception:
        pass

    from duckclaw.graphs.on_the_fly_commands import _resolve_meditate_vault_user_id

    meditate_user_id = _resolve_meditate_vault_user_id(
        type("_VaultDb", (), {"_path": vault})(),
        chat_id=str(body.chat_id),
        tenant_id=tid,
        vault_user_id="admin",
    )
    result = invoke_meditate_run(
        {
            "tenant_id": tid,
            "worker_id": wid,
            "chat_id": str(body.chat_id),
            "admin_chat_id": str(body.chat_id),
            "vault_db_path": vault,
            "user_id": meditate_user_id,
            "delta_interval_seconds": int(body.delta_interval_seconds),
            "targets": targets_obj.model_dump(),
        },
    )
    return {"ok": True, "result": result}


class CodeDecisionApproveBody(BaseModel):
    decision_id: str = Field(..., min_length=8)
    vault_path: str = Field(..., min_length=4)
    chat_id: str = ""
    tenant_id: str = "default"
    user_id: str = ""


class CodeDecisionRejectBody(BaseModel):
    decision_id: str = Field(..., min_length=8)
    vault_path: str = Field(..., min_length=4)
    rationale: str = ""
    tenant_id: str = "default"
    user_id: str = ""


@router.post("/code/approve", dependencies=[Depends(_require_admin_key)])
def admin_code_decision_approve(
    body: CodeDecisionApproveBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    """Aprueba code_decision PENDING_HITL y crea PR en GitHub (backend soberano)."""
    try:
        con, resolved, _scope = _duckdb_readonly_session(body.vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise _problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        tid = (body.tenant_id or "default").strip() or "default"
        uid = (body.user_id or actor or tid).strip() or tid

        class _DbShim:
            _path = resolved

            def query(self, q: str, params: tuple = ()):
                return con.execute(q, params).fetchdf().to_dict(orient="records")

        from duckclaw.capadonna_plugin import approve_capadonna_code_decision, capadonna_missing_message

        result = approve_capadonna_code_decision(
            _DbShim(),
            decision_id=body.decision_id.strip(),
            tenant_id=tid,
            user_id=uid,
            chat_id=(body.chat_id or "").strip(),
        )
        if result is None:
            raise _problem(503, "Extensión no configurada", capadonna_missing_message())
        if result.get("error"):
            raise _problem(400, "Aprobación fallida", str(result["error"]))
        return result
    finally:
        con.close()


@router.post("/code/reject", dependencies=[Depends(_require_admin_key)])
def admin_code_decision_reject(
    body: CodeDecisionRejectBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    """Rechaza code_decision."""
    try:
        con, resolved, _scope = _duckdb_readonly_session(body.vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise _problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        tid = (body.tenant_id or "default").strip() or "default"
        uid = (body.user_id or actor or tid).strip() or tid

        class _DbShim:
            _path = resolved

            def query(self, q: str, params: tuple = ()):
                return con.execute(q, params).fetchdf().to_dict(orient="records")

        from duckclaw.capadonna_plugin import capadonna_missing_message, reject_capadonna_code_decision

        result = reject_capadonna_code_decision(
            _DbShim(),
            decision_id=body.decision_id.strip(),
            tenant_id=tid,
            user_id=uid,
            rationale=body.rationale,
        )
        if result is None:
            raise _problem(503, "Extensión no configurada", capadonna_missing_message())
        return result
    finally:
        con.close()


@router.get("/code/decisions", dependencies=[Depends(_require_admin_key)])
def admin_list_code_decisions(
    vault_path: str = Query(..., min_length=4),
    status: str = Query(default="PENDING_HITL"),
    limit: int = Query(default=20, ge=1, le=100),
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    """Lista decisiones de código pendientes en el vault."""
    try:
        con, resolved, _scope = _duckdb_readonly_session(vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise _problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        st = (status or "").strip() or "PENDING_HITL"
        table_exists = con.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'main' AND table_name = 'code_decisions'
            """
        ).fetchone()[0]
        if not table_exists:
            return {"vault_path": resolved, "items": [], "status_filter": st}
        rows = con.execute(
            """
            SELECT id, repo, file_path, branch_name, decision_type, title, status, created_at, pr_url
            FROM main.code_decisions
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [st, int(limit)],
        ).fetchdf()
        return {"vault_path": resolved, "items": rows.to_dict(orient="records"), "status_filter": st}
    finally:
        con.close()


@router.get("/uncertainty/events", dependencies=[Depends(_require_admin_key)])
def admin_list_uncertainty_events(
    vault_path: str = Query(..., min_length=4),
    status: str = Query(default="PENDING_HITL"),
    limit: int = Query(default=20, ge=1, le=100),
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    """Lista eventos de incertidumbre epistémica del vault."""
    try:
        con, resolved, _scope = _duckdb_readonly_session(vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise _problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        st = (status or "").strip() or "PENDING_HITL"
        table_exists = con.execute(
            """
            SELECT COUNT(*)
            FROM information_schema.tables
            WHERE table_schema = 'main' AND table_name = 'agent_uncertainty_log'
            """
        ).fetchone()[0]
        if not table_exists:
            return {"vault_path": resolved, "items": [], "status_filter": st}
        rows = con.execute(
            """
            SELECT id, session_uid, worker_id, trigger_context, confidence_score,
                   description, proposed_questions, status, created_at
            FROM main.agent_uncertainty_log
            WHERE status = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            [st, int(limit)],
        ).fetchdf()
        return {"vault_path": resolved, "items": rows.to_dict(orient="records"), "status_filter": st}
    finally:
        con.close()


class UncertaintyResolveBody(BaseModel):
    event_id: str = Field(..., min_length=8)
    vault_path: str = Field(..., min_length=4)


@router.post("/uncertainty/resolve", dependencies=[Depends(_require_admin_key)])
def admin_resolve_uncertainty_event(
    body: UncertaintyResolveBody,
    actor: str = Depends(_actor_from_header),
) -> dict[str, Any]:
    """Resuelve un evento PENDING_HITL (equivalente a /resolve_uncertainty)."""
    try:
        con, resolved, scope = _duckdb_readonly_session(body.vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise _problem(403, "Vault no autorizado", str(exc)) from exc
    finally:
        con.close()
    try:
        from duckclaw.capadonna_plugin import load_capadonna_lib

        bridge = load_capadonna_lib("epistemic_humility_bridge")
        if bridge is None:
            raise _problem(503, "Plugin epistémico no disponible", "CAPADONNA_DRILLER_ROOT")
        from duckclaw import DuckClaw

        duck = DuckClaw(resolved, read_only=True)
        try:
            result = bridge.resolve_uncertainty_event(
                duck,
                event_id=body.event_id.strip(),
                tenant_id=(scope or {}).get("tenant_id") or "default",
                user_id=actor,
            )
        finally:
            duck.close()
        if result.get("error"):
            raise _problem(400, "No se pudo resolver", str(result["error"]))
        return {"vault_path": resolved, **result}
    except HTTPException:
        raise
    except Exception as exc:
        raise _problem(500, "Error resolviendo incertidumbre", str(exc)) from exc


from routers.admin_db_first import router as _admin_db_first_router  # noqa: E402
from routers.reports import router as _admin_reports_router  # noqa: E402

router.include_router(_admin_db_first_router)
router.include_router(_admin_reports_router)
