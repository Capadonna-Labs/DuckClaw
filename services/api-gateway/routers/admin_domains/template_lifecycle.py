"""Filesystem template helpers and legacy impls delegated from templates_catalog."""

from __future__ import annotations

import re
import shutil
from pathlib import Path
from typing import Any

from fastapi import Depends, Query
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import actor_from_header, problem
from routers.admin_domains.playground.tenant_resolution import playground_telegram_user_id

_EDITABLE_SUFFIXES = frozenset({".yaml", ".yml", ".md", ".sql", ".py", ".txt", ".json"})


class FileWriteBody(BaseModel):
    content: str = ""


class VaultBindingPutBody(BaseModel):
    scope: str = Field(default="", description="private | shared; vacío = quitar binding")
    vault_id: str | None = Field(default=None, max_length=128)
    path: str | None = Field(default=None, max_length=512)


class TemplateCreateBody(BaseModel):
    id: str = Field(..., min_length=1, max_length=64)
    source_template: str = Field(default="industries/business_standard")


def templates_dir() -> Path:
    from duckclaw.forge import WORKERS_TEMPLATES_DIR

    return WORKERS_TEMPLATES_DIR


def safe_worker_path(worker_id: str, rel_path: str) -> Path:
    wid = (worker_id or "").strip()
    if not wid or ".." in wid or "/" in wid or "\\" in wid:
        raise problem(400, "worker_id inválido", wid)
    base = (templates_dir() / wid).resolve()
    if not base.is_dir():
        raise problem(404, "Plantilla no encontrada", wid)
    rel = (rel_path or "").strip().lstrip("/")
    if not rel or ".." in rel.split("/"):
        raise problem(400, "Ruta de archivo inválida", rel_path)
    target = (base / rel).resolve()
    if not str(target).startswith(str(base)):
        raise problem(400, "Ruta fuera del worker", rel_path)
    if target.suffix.lower() not in _EDITABLE_SUFFIXES and not target.is_dir():
        raise problem(400, "Extensión no editable", target.suffix)
    return target


def list_template_files(worker_dir: Path) -> list[dict[str, Any]]:
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


def template_card_description(template_dir: Path) -> tuple[str, str]:
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


def default_vault_user_id(vault_user_id: str | None = None) -> str:
    return playground_telegram_user_id(vault_user_id) or "default"


def manifest_file_for_worker(worker_id: str) -> Path:
    base = templates_dir() / worker_id.strip()
    for name in ("manifest.yaml", "manifest.yml"):
        candidate = base / name
        if candidate.is_file():
            return candidate
    return base / "manifest.yaml"


def merge_manifest_vault_binding(worker_id: str, binding: dict[str, str] | None) -> None:
    import yaml

    path = manifest_file_for_worker(worker_id)
    if not path.parent.is_dir():
        raise problem(404, "Plantilla no encontrada", worker_id)
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


def read_manifest_skills(template_dir: Path) -> list[str]:
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


def merge_skill_lists(base: list[str], extra: list[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for s in base + extra:
        key = s.strip()
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(key)
    return merged


def write_worker_prompts(dest: Path, *, system_prompt: str, soul: str) -> None:
    sp = (system_prompt or "").strip()
    if sp:
        (dest / "system_prompt.md").write_text(sp + "\n", encoding="utf-8")
    sl = (soul or "").strip()
    if sl:
        (dest / "soul.md").write_text(sl + "\n", encoding="utf-8")


def create_worker_from_source(
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
    dest = templates_dir() / wid
    if dest.exists():
        raise problem(409, "Plantilla ya existe", wid)

    base_rel = "default"
    base = templates_dir() / base_rel
    if not base.is_dir():
        base = templates_dir() / "industries" / "business_standard"
    if not base.is_dir():
        raise problem(404, "Plantilla base default no encontrada", base_rel)

    shutil.copytree(base, dest)

    from duckclaw.framework_tool_pack import ensure_baseline_skills, ensure_baseline_worker_files

    ensure_baseline_worker_files(dest)

    preset_rel = (source_template or "default").strip().strip("/")
    preset_dir = templates_dir() / preset_rel
    preset_skills: list[str] = []
    if preset_rel != "default" and preset_dir.is_dir():
        preset_skills = read_manifest_skills(preset_dir)

    base_skills = read_manifest_skills(dest)
    if skills is not None and len(skills) > 0:
        final_skills = merge_skill_lists(base_skills, list(skills))
    else:
        final_skills = merge_skill_lists(base_skills, preset_skills)

    manifest = dest / "manifest.yaml"
    if manifest.is_file():
        try:
            import yaml

            data = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            if not isinstance(data, dict):
                data = {}
            data["id"] = wid
            data["name"] = (name or wid).strip()
            data.pop("internal_scaffold", None)
            if description.strip():
                data["description"] = description.strip()
            final_skills = ensure_baseline_skills(final_skills, manifest=data)
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

    write_worker_prompts(dest, system_prompt=system_prompt, soul=soul)
    return dest


async def list_templates_impl(
    include_inactive: bool = Query(False),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import list_templates_payload, open_gateway_db

    with open_gateway_db(read_only=True) as db:
        items = list_templates_payload(db, actor_email=actor, include_inactive=include_inactive)
    return {"templates": items}


async def get_template_impl(
    worker_id: str,
    include_content: bool = True,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_identity import catalog_template_detail, open_gateway_db

    with open_gateway_db(read_only=True) as db:
        detail = catalog_template_detail(db, actor_email=actor, worker_id=worker_id)
    if detail is None:
        raise problem(404, "Plantilla no encontrada o no asignada al catálogo", worker_id)
    if not include_content:
        detail = {**detail, "contents": {}}
    return detail


async def put_template_file_impl(
    worker_id: str,
    file_path: str,
    body: FileWriteBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    raise problem(
        410,
        "Mutación legacy de template retirada",
        "Usa routers.admin_domains.templates_catalog y comandos tipados DB-first.",
    )




def _worker_known(worker_id: str) -> bool:
    wid = (worker_id or "").strip()
    if not wid:
        return False
    if (templates_dir() / wid).is_dir():
        return True
    try:
        from core.admin_identity import open_gateway_db
        from duckclaw.admin_worker_catalog import (
            catalog_worker_id_variants,
            ensure_admin_worker_catalog_schema,
            _first_row,
        )

        with open_gateway_db(read_only=True) as db:
            ensure_admin_worker_catalog_schema(db)
            for candidate in catalog_worker_id_variants(wid):
                row = _first_row(
                    db,
                    "SELECT 1 AS ok FROM main.admin_worker_catalog "
                    f"WHERE worker_id = '{candidate}' LIMIT 1",
                )
                if row:
                    return True
    except Exception:
        return False
    return False



def _catalog_manifest_dict(worker_id: str, *, actor: str | None = None) -> dict:
    """Load manifest mapping from catalog snapshot (files or manifest_snapshot)."""
    import yaml
    from core.admin_identity import effective_actor_email, open_gateway_db
    from duckclaw.admin_worker_catalog import (
        _first_row,
        catalog_worker_id_variants,
        ensure_admin_worker_catalog_schema,
        get_latest_worker_version,
        get_visible_worker_for_actor,
    )

    wid = (worker_id or "").strip()
    with open_gateway_db(read_only=True) as db:
        ensure_admin_worker_catalog_schema(db)
        worker = None
        if actor:
            worker = get_visible_worker_for_actor(
                db, actor_email=effective_actor_email(actor), worker_id=wid
            )
        if not worker:
            for candidate in catalog_worker_id_variants(wid):
                row = _first_row(
                    db,
                    "SELECT worker_uid, tenant_id, worker_id "
                    "FROM main.admin_worker_catalog "
                    f"WHERE worker_id = '{candidate}' LIMIT 1",
                )
                if row:
                    worker = {
                        "worker_uid": str(row.get("worker_uid") or ""),
                        "worker_id": str(row.get("worker_id") or candidate),
                        "tenant_id": str(row.get("tenant_id") or ""),
                    }
                    break
        if not worker:
            return {}
        latest = get_latest_worker_version(db, worker_uid=str(worker.get("worker_uid") or "")) or {}
        files = latest.get("files_snapshot") or {}
        content = files.get("manifest.yaml") or files.get("manifest.yml") or ""
        if isinstance(content, str) and content.strip():
            loaded = yaml.safe_load(content)
            return loaded if isinstance(loaded, dict) else {}
        snap = latest.get("manifest_snapshot") or {}
        return dict(snap) if isinstance(snap, dict) else {}


def _apply_vault_binding_to_manifest(raw: dict, binding: dict[str, str] | None) -> dict:
    data = dict(raw)
    fc = data.get("forge_context")
    if not isinstance(fc, dict):
        fc = {}
    else:
        fc = dict(fc)
    if binding:
        fc["vault_binding"] = dict(binding)
    else:
        fc.pop("vault_binding", None)
    if fc:
        data["forge_context"] = fc
    else:
        data.pop("forge_context", None)
    return data


async def template_vault_options_impl(
    worker_id: str,
    vault_user_id: str | None = Query(None, description="ID dueño de db/private/ (default: DUCKCLAW_OWNER_ID)"),
) -> dict[str, Any]:
    from duckclaw.vaults import list_vault_options_for_user

    wid = worker_id.strip()
    if not _worker_known(wid):
        raise problem(404, "Plantilla no encontrada", wid)
    uid = default_vault_user_id(vault_user_id)
    options = list_vault_options_for_user(uid)
    return {"vault_user_id": uid, "worker_id": wid, "options": options}


async def get_template_vault_binding_impl(
    worker_id: str,
    vault_user_id: str | None = Query(None),
) -> dict[str, Any]:
    from duckclaw.vaults import normalize_vault_binding, resolve_template_vault_path

    wid = worker_id.strip()
    uid = default_vault_user_id(vault_user_id)
    binding = None
    catalog_raw = _catalog_manifest_dict(wid)
    if catalog_raw:
        fc = catalog_raw.get("forge_context")
        if isinstance(fc, dict):
            binding = normalize_vault_binding(fc.get("vault_binding"))
    else:
        try:
            from duckclaw.workers.manifest import load_manifest

            spec = load_manifest(wid)
            binding = spec.forge_vault_binding
        except Exception as exc:
            raise problem(404, "Plantilla no encontrada o manifest inválido", str(exc)) from exc
    resolved = resolve_template_vault_path(binding, uid, require_exists=False)
    return {
        "worker_id": wid,
        "vault_user_id": uid,
        "binding": binding,
        "resolved_path": resolved,
    }


async def put_template_vault_binding_impl(
    worker_id: str,
    body: VaultBindingPutBody,
    actor: str,
) -> dict[str, Any]:
    import yaml
    from duckclaw.vaults import normalize_vault_binding, resolve_template_vault_path
    from duckclaw.write_commands import UpdateCatalogWorkerFileCommand
    from duckclaw.gateway_enqueue import enqueue_admin_command
    from core.admin_identity import effective_actor_email, open_gateway_db
    from duckclaw.admin_worker_catalog import get_visible_worker_for_actor

    wid = (worker_id or "").strip()
    if not wid:
        raise problem(400, "worker_id requerido", wid)
    actor_email = effective_actor_email(actor)
    with open_gateway_db(read_only=True) as db:
        worker = get_visible_worker_for_actor(db, actor_email=actor_email, worker_id=wid)
    if not worker:
        raise problem(404, "Worker no visible en catálogo", wid)

    scope = (body.scope or "").strip().lower()
    if not scope:
        binding = None
    elif scope == "private":
        binding = normalize_vault_binding({"scope": "private", "vault_id": body.vault_id or ""})
        if not binding:
            raise problem(400, "vault_id requerido para scope private", wid)
    elif scope == "shared":
        binding = normalize_vault_binding({"scope": "shared", "path": body.path or ""})
        if not binding:
            raise problem(400, "path requerido para scope shared", wid)
    else:
        raise problem(400, "scope inválido", scope)

    raw = _catalog_manifest_dict(wid, actor=actor_email)
    if not raw:
        raw = {"id": wid}
    updated = _apply_vault_binding_to_manifest(raw, binding)
    content = yaml.safe_dump(
        updated, allow_unicode=True, sort_keys=False, default_flow_style=False
    )
    command = UpdateCatalogWorkerFileCommand(
        actor_email=actor_email,
        worker_id=wid,
        file_path="manifest.yaml",
        content=content,
    )
    task_id = enqueue_admin_command(command)
    uid = default_vault_user_id(None)
    resolved = resolve_template_vault_path(binding, uid, require_exists=False)
    return {
        "ok": True,
        "worker_id": wid,
        "binding": binding,
        "resolved_path": resolved,
        "task_id": task_id,
        "accepted": True,
    }



async def delete_template_vault_binding_impl(
    worker_id: str,
    actor: str,
) -> dict[str, Any]:
    """Clear forge_context.vault_binding via the same catalog manifest write path as PUT."""
    body = VaultBindingPutBody(scope="", vault_id=None, path=None)
    return await put_template_vault_binding_impl(worker_id=worker_id, body=body, actor=actor)


async def create_template_impl(
    body: TemplateCreateBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    raise problem(
        410,
        "Creación filesystem de templates retirada",
        "Usa el flujo administrado de workspace o importa templates existentes al catálogo DB-first.",
    )


async def delete_template_impl(
    worker_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    raise problem(
        410,
        "Mutación legacy de template retirada",
        "Usa routers.admin_domains.templates_catalog y comandos tipados DB-first.",
    )


async def reactivate_template_impl(
    worker_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    raise problem(
        410,
        "Mutación legacy de template retirada",
        "Usa routers.admin_domains.templates_catalog y comandos tipados DB-first.",
    )


async def hard_delete_template_impl(
    worker_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    raise problem(
        410,
        "Mutación legacy de template retirada",
        "Usa routers.admin_domains.templates_catalog y comandos tipados DB-first.",
    )


async def validate_template_impl(worker_id: str) -> dict[str, Any]:
    raise problem(
        410,
        "Validación filesystem retirada",
        "La validación operativa se realiza sobre snapshots DB-first del catálogo.",
    )
