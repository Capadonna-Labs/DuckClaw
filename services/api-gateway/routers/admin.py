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


def _env_file() -> Path:
    return _repo_root() / ".env"


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


class TemplateCreateBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    source_template: str = Field(default="industries/business_standard")


class EnvPatchBody(BaseModel):
    values: dict[str, str] = Field(default_factory=dict)


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
async def put_template_file(worker_id: str, file_path: str, body: FileWriteBody) -> dict[str, Any]:
    target = _safe_worker_path(worker_id, file_path)
    if not target.parent.is_dir():
        target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body.content, encoding="utf-8")
    if target.name in ("manifest.yaml", "manifest.yml"):
        from duckclaw.workers.manifest import load_manifest

        load_manifest(worker_id)
    return {"ok": True, "path": file_path}


@router.post("/templates", dependencies=[Depends(_require_admin_key)])
async def create_template(body: TemplateCreateBody) -> dict[str, Any]:
    wid = re.sub(r"[^a-zA-Z0-9_-]", "", body.id.strip())
    if not wid:
        raise _problem(400, "id inválido", body.id)
    dest = _templates_dir() / wid
    if dest.exists():
        raise _problem(409, "Plantilla ya existe", wid)
    src_rel = body.source_template.strip().strip("/")
    src = _templates_dir() / src_rel
    if not src.is_dir():
        src = _templates_dir() / "industries" / "business_standard"
    if not src.is_dir():
        raise _problem(404, "Plantilla origen no encontrada", body.source_template)
    shutil.copytree(src, dest)
    manifest = dest / "manifest.yaml"
    if manifest.is_file():
        text = manifest.read_text(encoding="utf-8")
        text = re.sub(r"^id:\s*.+$", f"id: {wid}", text, count=1, flags=re.MULTILINE)
        text = re.sub(r"^name:\s*.+$", f"name: {wid}", text, count=1, flags=re.MULTILINE)
        manifest.write_text(text, encoding="utf-8")
    return {"ok": True, "id": wid}


@router.delete("/templates/{worker_id}", dependencies=[Depends(_require_admin_key)])
async def delete_template(worker_id: str) -> dict[str, Any]:
    wid = worker_id.strip()
    if wid in _PROTECTED_TEMPLATE_IDS:
        raise _problem(403, "Plantilla protegida", wid)
    dest = _templates_dir() / wid
    if not dest.is_dir():
        raise _problem(404, "Plantilla no encontrada", wid)
    shutil.rmtree(dest)
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
async def patch_env_config(body: EnvPatchBody) -> dict[str, Any]:
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
        k = s.split("=", 1)[0].strip()
        key_to_idx[k] = i
    updated: list[str] = []
    for k, v in body.values.items():
        if not _is_env_key_allowed(k):
            raise _problem(400, "Clave no permitida", k)
        line = f"{k}={v}\n"
        if k in key_to_idx:
            lines[key_to_idx[k]] = line
        else:
            lines.append(line)
        updated.append(k)
    env_path.write_text("".join(lines), encoding="utf-8")
    return {"ok": True, "updated": updated, "backup": str(backup)}


@router.get("/telegram/routes", dependencies=[Depends(_require_admin_key)])
async def get_telegram_routes() -> dict[str, Any]:
    raw = (os.environ.get("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES") or "").strip()
    routes: list[dict[str, str]] = []
    for part in raw.split(","):
        part = part.strip()
        if not part:
            continue
        bits = part.split(":")
        if len(bits) >= 3:
            routes.append({"bot": bits[0], "path": ":".join(bits[2:])})
    return {"routes": routes, "raw_masked": _mask_secret(raw) if raw else ""}


@router.get("/runtime/vaults", dependencies=[Depends(_require_admin_key)])
async def list_vaults() -> dict[str, Any]:
    db_root = _repo_root() / "db"
    vaults: list[dict[str, str]] = []
    for sub in ("private", "shared"):
        p = db_root / sub
        if not p.is_dir():
            continue
        for f in p.rglob("*.duckdb"):
            vaults.append({"path": str(f.relative_to(_repo_root())), "scope": sub})
    return {"vaults": vaults[:100]}


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
    db = DuckClaw(abs_path, read_only=True)
    try:
        cid = (chat_id or "default").replace("'", "''")
        rows = db.query(
            f"SELECT key, value FROM agent_config WHERE chat_id = '{cid}' ORDER BY key"
        )
    except Exception as exc:
        raise _problem(400, "Error leyendo agent_config", str(exc)) from exc
    if isinstance(rows, str):
        rows = json.loads(rows) if rows.strip().startswith("[") else []
    return {"vault_path": vault_path, "chat_id": chat_id, "rows": rows}


@router.put("/runtime/config", dependencies=[Depends(_require_admin_key)])
async def put_runtime_config(body: RuntimeConfigPutBody) -> dict[str, Any]:
    import redis.asyncio as aioredis

    abs_path = body.vault_path
    if not os.path.isabs(abs_path):
        abs_path = str(_repo_root() / body.vault_path.lstrip("/"))
    key_esc = body.key.replace("'", "''")[:128]
    val_esc = body.value.replace("'", "''")[:8000]
    cid_esc = (body.chat_id or "default").replace("'", "''")
    sql = (
        f"INSERT INTO agent_config (chat_id, key, value) VALUES ('{cid_esc}', '{key_esc}', '{val_esc}') "
        f"ON CONFLICT (chat_id, key) DO UPDATE SET value = excluded.value"
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
    return {"ok": True, "queued": True}


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


@router.post("/projects", dependencies=[Depends(_require_admin_key)])
async def create_project(body: TemplateCreateBody) -> dict[str, Any]:
    return await create_template(body)
