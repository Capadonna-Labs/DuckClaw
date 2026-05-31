"""Non-destructive import of filesystem worker templates into the DB catalog."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

import yaml

from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.admin_worker_catalog import (
    add_worker_context,
    add_worker_version,
    create_worker,
    get_worker_by_tenant_worker_id,
    grant_worker_capability,
    list_worker_contexts,
    register_capability,
    sanitize_catalog_worker_id,
)
from duckclaw.shared_db_grants import _query_all_dicts, _sql_lit

_IMPORT_FILE_SUFFIXES = {".yaml", ".yml", ".md", ".sql", ".txt", ".json"}
_DEFAULT_EXCLUDED_TEMPLATE_IDS = ("default",)


def _iter_template_dirs(
    templates_root: Path,
    *,
    include_prefixes: Iterable[str],
    include_template_ids: Iterable[str],
    exclude_template_ids: Iterable[str],
) -> list[Path]:
    prefixes = tuple(prefix for prefix in include_prefixes if prefix)
    explicit_ids = {item for item in include_template_ids if item}
    excluded_ids = {item for item in exclude_template_ids if item}
    if not templates_root.is_dir():
        return []

    out: list[Path] = []
    for path in sorted(templates_root.iterdir(), key=lambda p: p.name.lower()):
        if not path.is_dir():
            continue
        if path.name in excluded_ids:
            continue
        if explicit_ids and path.name not in explicit_ids:
            continue
        if prefixes and not any(path.name.startswith(prefix) for prefix in prefixes):
            continue
        if (path / "manifest.yaml").is_file() or (path / "manifest.yml").is_file():
            out.append(path)
    return out


def _load_manifest(template_dir: Path) -> dict[str, Any]:
    for name in ("manifest.yaml", "manifest.yml"):
        path = template_dir / name
        if path.is_file():
            data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            return data if isinstance(data, dict) else {}
    return {}


def _read_relevant_files(template_dir: Path) -> dict[str, str]:
    files: dict[str, str] = {}
    for path in sorted(template_dir.rglob("*"), key=lambda p: str(p.relative_to(template_dir))):
        if not path.is_file() or path.suffix.lower() not in _IMPORT_FILE_SUFFIXES:
            continue
        rel = str(path.relative_to(template_dir))
        files[rel] = path.read_text(encoding="utf-8")
    return files


def _context_files(manifest: dict[str, Any], files: dict[str, str]) -> list[tuple[str, str]]:
    candidates: set[str] = set()
    for key, value in manifest.items():
        if key.endswith("_file") and isinstance(value, str) and value.strip().endswith(".md"):
            candidates.add(value.strip().replace("./", "", 1))
    for rel in files.keys():
        if rel.endswith(".md") and rel in {
            "system_prompt.md",
            "domain_closure.md",
            "AGENT_OVERVIEW.md",
            "orchestrator_planner.md",
        }:
            candidates.add(rel)
    return [(rel, files[rel]) for rel in sorted(candidates) if rel in files]


def _capability_names(manifest: dict[str, Any]) -> list[str]:
    dependencies = manifest.get("dependencies")
    if not isinstance(dependencies, dict):
        return []
    raw = dependencies.get("capabilities_required")
    if not isinstance(raw, list):
        return []
    seen: set[str] = set()
    names: list[str] = []
    for item in raw:
        name = str(item or "").strip()
        if name and name not in seen:
            seen.add(name)
            names.append(name)
    return names


def _same_version_exists(db: Any, *, worker_uid: str, manifest: dict[str, Any], files: dict[str, str]) -> bool:
    manifest_json = json.dumps(manifest or {}, ensure_ascii=False, sort_keys=True)
    files_json = json.dumps(files or {}, ensure_ascii=False, sort_keys=True)
    rows = _query_all_dicts(
        db,
        "SELECT version FROM main.admin_worker_versions "
        f"WHERE worker_uid = '{_sql_lit(worker_uid, 64)}' "
        f"AND manifest_snapshot_json = '{_sql_lit(manifest_json, 65535)}' "
        f"AND files_snapshot_json = '{_sql_lit(files_json, 65535)}' "
        "LIMIT 1",
    )
    return bool(rows)


def import_templates_to_catalog(
    db: Any,
    *,
    owner_email: str,
    templates_root: str | Path,
    include_prefixes: Iterable[str] = (),
    include_template_ids: Iterable[str] = (),
    exclude_template_ids: Iterable[str] = _DEFAULT_EXCLUDED_TEMPLATE_IDS,
) -> dict[str, list[Any]]:
    """Import selected templates into the DB catalog without deleting folders."""
    profile = ensure_profile_for_user(db, email=owner_email)
    root = Path(templates_root)
    imported: list[dict[str, str]] = []
    skipped_existing: list[str] = []
    skipped: list[str] = []

    for template_dir in _iter_template_dirs(
        root,
        include_prefixes=include_prefixes,
        include_template_ids=include_template_ids,
        exclude_template_ids=exclude_template_ids,
    ):
        manifest = _load_manifest(template_dir)
        files = _read_relevant_files(template_dir)
        worker_id = sanitize_catalog_worker_id(template_dir.name)
        display_name = str(manifest.get("display_name") or template_dir.name).strip()
        existing = get_worker_by_tenant_worker_id(
            db,
            tenant_id=profile["tenant_id"],
            worker_id=worker_id,
        )
        if existing:
            worker = existing
            if _same_version_exists(db, worker_uid=worker["worker_uid"], manifest=manifest, files=files):
                skipped_existing.append(worker_id)
                continue
        else:
            worker = create_worker(
                db,
                owner_email=profile["email"],
                worker_id=worker_id,
                display_name=display_name,
                source_kind="template_import",
                source_template_id="default",
                visibility="private",
            )

        if not _same_version_exists(db, worker_uid=worker["worker_uid"], manifest=manifest, files=files):
            add_worker_version(
                db,
                worker_uid=worker["worker_uid"],
                created_by=profile["email"],
                manifest_snapshot=manifest,
                files_snapshot=files,
                change_note=f"Import no destructivo desde {template_dir.name}",
            )

        existing_context_titles = {ctx["title"] for ctx in list_worker_contexts(db, worker_uid=worker["worker_uid"])}
        for order, (title, content_md) in enumerate(_context_files(manifest, files), start=10):
            if title not in existing_context_titles:
                add_worker_context(
                    db,
                    worker_uid=worker["worker_uid"],
                    title=title,
                    content_md=content_md,
                    sort_order=order,
                )

        for capability_name in _capability_names(manifest):
            capability = register_capability(
                db,
                name=capability_name,
                kind="manifest_capability",
                provider="template_import",
                risk_level="medium",
            )
            grant_worker_capability(
                db,
                worker_uid=worker["worker_uid"],
                capability_id=capability["capability_id"],
                permission="use",
            )

        imported.append({"worker_id": worker_id, "worker_uid": worker["worker_uid"], "template_dir": str(template_dir)})

    return {"imported": imported, "skipped_existing": skipped_existing, "skipped": skipped}
