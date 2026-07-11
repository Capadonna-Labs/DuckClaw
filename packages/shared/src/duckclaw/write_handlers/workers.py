"""Worker catalog, user-agent, template-context and capability write handlers."""
from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from duckclaw.admin_user_agents import sanitize_worker_id as sanitize_user_agent_worker_id
from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.admin_worker_catalog import (
    deactivate_visible_worker_for_actor,
    ensure_admin_worker_catalog_schema,
    get_visible_worker_for_actor,
    hard_delete_visible_worker_for_actor,
    reactivate_visible_worker_for_actor,
    sanitize_catalog_worker_id,
    update_catalog_worker_file,
)


def _resolve_worker_uid(conn: Any, worker_id: str, tenant_id: str) -> str | None:
    row = conn.execute(
        "SELECT worker_uid FROM main.admin_worker_catalog "
        "WHERE worker_id = ? AND tenant_id = ?",
        [worker_id, tenant_id],
    ).fetchone()
    return str(row[0]) if row else None


def _sync_user_agent_prompt_policy(
    conn: Any,
    *,
    worker_id: str,
    files_snapshot: dict[str, str],
    actor_email: str,
    worker_uid: str,
) -> None:
    from duckclaw.catalog_prompt_sync import sync_worker_system_prompt_policy

    if not sync_worker_system_prompt_policy(
        conn,
        worker_id=worker_id,
        files=files_snapshot,
        actor_email=actor_email,
        worker_uid=worker_uid,
        force=True,
    ):
        content = str(files_snapshot.get("system_prompt.md") or "").strip()
        if not content:
            raise RuntimeError(
                f"system_prompt vacío para {worker_id}; no se pudo materializar en prompt_policy_registry"
            )
        raise RuntimeError(f"No se pudo sincronizar system_prompt/{worker_id} en prompt_policy_registry")


def _stable_json(value: Any) -> str:
    return json.dumps(value or {}, default=str, ensure_ascii=False, sort_keys=True)


def _worker_snapshot_exists(
    conn: Any,
    *,
    worker_uid: str,
    manifest_snapshot: dict[str, Any],
    files_snapshot: dict[str, Any],
) -> bool:
    expected_manifest = _stable_json(manifest_snapshot)
    expected_files = _stable_json(files_snapshot)
    rows = conn.execute(
        "SELECT manifest_snapshot_json, files_snapshot_json "
        "FROM main.admin_worker_versions WHERE worker_uid = ?",
        [worker_uid],
    ).fetchall()
    for row in rows:
        try:
            manifest = json.loads(str(row[0] or "{}"))
            files = json.loads(str(row[1] or "{}"))
        except json.JSONDecodeError:
            continue
        if _stable_json(manifest) == expected_manifest and _stable_json(files) == expected_files:
            return True
    return False


def _apply_upsert_worker(conn: Any, payload: dict) -> None:
    worker_id = str(payload["worker_id"])
    display_name = str(payload.get("display_name", worker_id))
    tenant_id = str(payload.get("tenant_id") or "default")
    owner = str(payload.get("actor_email", "system"))
    source_kind = str(payload.get("source_kind", "runtime"))
    source_tpl = str(payload.get("source_template_id", "default"))
    visibility = str(payload.get("visibility", "private"))
    existing_uid = _resolve_worker_uid(conn, worker_id, tenant_id)

    if existing_uid:
        conn.execute(
            "UPDATE main.admin_worker_catalog "
            "SET display_name = ?, source_kind = ?, source_template_id = ?, "
            "visibility = ?, updated_at = CURRENT_TIMESTAMP "
            "WHERE worker_id = ? AND tenant_id = ?",
            [display_name, source_kind, source_tpl, visibility, worker_id, tenant_id],
        )
    else:
        wuid = str(payload.get("worker_uid", f"wrk_{uuid.uuid4().hex}"))
        conn.execute(
            "INSERT INTO main.admin_worker_catalog "
            "(worker_uid, tenant_id, owner_email, worker_id, display_name, "
            "source_kind, source_template_id, visibility, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, true)",
            [wuid, tenant_id, owner, worker_id, display_name, source_kind, source_tpl, visibility],
        )
        existing_uid = wuid

    manifest = payload.get("manifest_snapshot")
    files = payload.get("files_snapshot")
    if (manifest or files) and not _worker_snapshot_exists(
        conn,
        worker_uid=existing_uid,
        manifest_snapshot=manifest or {},
        files_snapshot=files or {},
    ):
        row = conn.execute(
            "SELECT COALESCE(MAX(version), 0) FROM main.admin_worker_versions "
            "WHERE worker_uid = ?", [existing_uid],
        ).fetchone()
        next_ver = (int(row[0]) if row[0] is not None else 0) + 1
        conn.execute(
            "INSERT INTO main.admin_worker_versions "
            "(worker_uid, version, manifest_snapshot_json, files_snapshot_json, created_by) "
            "VALUES (?, ?, ?, ?, ?)",
            [
                existing_uid, next_ver,
                _stable_json(manifest or {}),
                _stable_json(files or {}),
                owner,
            ],
        )

    manifest = payload.get("manifest_snapshot")
    if isinstance(manifest, dict) and existing_uid:
        from duckclaw.mcp_connector_defaults import (
            ensure_default_mcp_connectors,
            sync_worker_mcp_grants_from_manifest,
        )

        ensure_default_mcp_connectors(
            conn, tenant_id=tenant_id, actor_email=owner
        )
        sync_worker_mcp_grants_from_manifest(
            conn,
            worker_uid=existing_uid,
            tenant_id=tenant_id,
            manifest=manifest,
            actor_email=owner,
        )

    system_prompt = str(payload.get("system_prompt", "")).strip()
    if system_prompt:
        existing_context = conn.execute(
            "SELECT context_id FROM main.admin_worker_contexts "
            "WHERE worker_uid = ? AND title = 'system_prompt.md' AND active = true LIMIT 1",
            [existing_uid],
        ).fetchone()
        if existing_context:
            conn.execute(
                "UPDATE main.admin_worker_contexts "
                "SET content_md = ?, updated_at = CURRENT_TIMESTAMP WHERE context_id = ?",
                [system_prompt, existing_context[0]],
            )
        else:
            cid = f"ctx_{uuid.uuid4().hex[:16]}"
            conn.execute(
                "INSERT INTO main.admin_worker_contexts "
                "(context_id, worker_uid, title, content_md, sort_order) "
                "VALUES (?, ?, 'system_prompt.md', ?, 10)",
                [cid, existing_uid, system_prompt],
            )


def _apply_upsert_user_agent(conn: Any, payload: dict) -> None:
    actor = str(payload.get("actor_email") or "system").strip().lower() or "system"
    profile = ensure_profile_for_user(conn, email=actor)
    tenant_id = str(payload.get("tenant_id") or profile.get("tenant_id") or "default").strip() or "default"
    if str(profile.get("tenant_id") or tenant_id) != tenant_id:
        raise ValueError(f"Tenant mismatch for actor: {actor}")

    worker_id = sanitize_catalog_worker_id(sanitize_user_agent_worker_id(str(payload.get("worker_id") or "")))
    display_name = str(payload.get("display_name") or worker_id).strip()[:256] or worker_id
    source_template_id = str(payload.get("source_template_id") or "default").strip()[:64] or "default"
    system_prompt = str(payload.get("system_prompt") or "").strip()
    soul = str(payload.get("soul") or "").strip()
    if len(system_prompt) < 80:
        raise ValueError("system_prompt debe tener al menos 80 caracteres")
    if len(soul) < 20:
        raise ValueError("soul debe tener al menos 20 caracteres")
    tool_profile = "general"
    skills = [str(skill).strip()[:128] for skill in payload.get("skills") or [] if str(skill).strip()]
    if payload.get("web_search") and "research" not in {s.lower() for s in skills}:
        skills.append("research")
    try:
        from duckclaw.framework_tool_pack import ensure_baseline_skills

        skills = ensure_baseline_skills(skills, manifest={"tool_profile": tool_profile})
    except Exception:
        pass
    manifest = {
        "id": worker_id,
        "display_name": display_name,
        "owner_email": str(profile.get("email") or actor),
        "tenant_id": tenant_id,
        "source_template_id": source_template_id,
        "description": str(payload.get("description") or "").strip(),
        "system_prompt": system_prompt.strip(),
        "skills": skills,
        "tool_profile": tool_profile,
    }
    if payload.get("browser_sandbox"):
        manifest["browser_sandbox"] = True
    manifest_json = json.dumps(manifest, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    files_snapshot = {"manifest.json": manifest_json}
    if system_prompt.strip():
        files_snapshot["system_prompt.md"] = system_prompt.strip()
    if soul:
        files_snapshot["soul.md"] = soul

    _apply_upsert_worker(
        conn,
        {
            **payload,
            "worker_uid": str(payload.get("worker_uid") or "").strip(),
            "worker_id": worker_id,
            "display_name": display_name,
            "tenant_id": tenant_id,
            "actor_email": str(profile.get("email") or actor),
            "source_kind": "runtime",
            "source_template_id": source_template_id,
            "visibility": "private",
            "system_prompt": system_prompt,
            "manifest_snapshot": manifest,
            "files_snapshot": files_snapshot,
        },
    )
    worker_uid = _resolve_worker_uid(conn, worker_id, tenant_id)
    if not worker_uid:
        raise RuntimeError("user agent worker insert failed")
    if soul:
        existing_soul = conn.execute(
            "SELECT context_id FROM main.admin_worker_contexts "
            "WHERE worker_uid = ? AND title = 'soul.md' AND active = true LIMIT 1",
            [worker_uid],
        ).fetchone()
        if existing_soul:
            conn.execute(
                "UPDATE main.admin_worker_contexts "
                "SET content_md = ?, updated_at = CURRENT_TIMESTAMP WHERE context_id = ?",
                [soul, existing_soul[0]],
            )
        else:
            cid = f"ctx_{uuid.uuid4().hex[:16]}"
            conn.execute(
                "INSERT INTO main.admin_worker_contexts "
                "(context_id, worker_uid, title, content_md, sort_order) VALUES (?, ?, 'soul.md', ?, 20)",
                [cid, worker_uid, soul],
            )
    manifest_path = f"db://admin_worker_catalog/{worker_uid}/manifest.json"

    def _sync_mcp_grants() -> None:
        from duckclaw.mcp_connector_defaults import (
            ensure_default_mcp_connectors,
            sync_worker_mcp_grants_from_manifest,
        )

        actor_email = str(profile.get("email") or actor)
        ensure_default_mcp_connectors(conn, tenant_id=tenant_id, actor_email=actor_email)
        sync_worker_mcp_grants_from_manifest(
            conn,
            worker_uid=worker_uid,
            tenant_id=tenant_id,
            manifest=manifest,
            actor_email=actor_email,
        )

    existing_user_agent = conn.execute(
        "SELECT worker_id FROM main.admin_user_agents WHERE tenant_id = ? AND worker_id = ?",
        [tenant_id, worker_id],
    ).fetchone()
    if existing_user_agent:
        conn.execute(
            "UPDATE main.admin_user_agents "
            "SET owner_email = ?, display_name = ?, source_template_id = ?, manifest_path = ?, "
            "active = true, updated_at = CURRENT_TIMESTAMP "
            "WHERE tenant_id = ? AND worker_id = ?",
            [
                str(profile.get("email") or actor),
                display_name,
                source_template_id,
                manifest_path,
                tenant_id,
                worker_id,
            ],
        )
        _sync_user_agent_prompt_policy(
            conn,
            worker_id=worker_id,
            files_snapshot=files_snapshot,
            actor_email=str(profile.get("email") or actor),
            worker_uid=worker_uid,
        )
        _sync_mcp_grants()
        return
    conn.execute(
        "INSERT INTO main.admin_user_agents "
        "(tenant_id, owner_email, worker_id, display_name, source_template_id, manifest_path, active) "
        "VALUES (?, ?, ?, ?, ?, ?, true)",
        [
            tenant_id,
            str(profile.get("email") or actor),
            worker_id,
            display_name,
            source_template_id,
            manifest_path,
        ],
    )
    _sync_user_agent_prompt_policy(
        conn,
        worker_id=worker_id,
        files_snapshot=files_snapshot,
        actor_email=str(profile.get("email") or actor),
        worker_uid=worker_uid,
    )
    _sync_mcp_grants()


def _catalog_skill_name(raw: Any) -> str:
    name = str(raw or "").strip()
    if not name:
        raise ValueError("skill name required")
    if len(name) > 128:
        raise ValueError("skill name too long")
    return name


def _catalog_skill_visibility(raw: Any) -> str:
    visibility = str(raw or "private").strip().lower() or "private"
    if visibility not in {"private", "public"}:
        raise ValueError(f"Invalid catalog skill visibility: {visibility}")
    return visibility


def _apply_upsert_catalog_skill(conn: Any, payload: dict) -> None:
    ensure_admin_worker_catalog_schema(conn)
    actor = str(payload.get("actor_email") or "system").strip().lower() or "system"
    profile = ensure_profile_for_user(conn, email=actor)
    tenant_id = str(payload.get("tenant_id") or profile.get("tenant_id") or "default").strip() or "default"
    if str(profile.get("tenant_id") or tenant_id) != tenant_id:
        raise ValueError(f"Tenant mismatch for actor: {actor}")

    name = _catalog_skill_name(payload.get("name"))
    description = str(payload.get("description") or "").strip()[:1024]
    skill_type = str(payload.get("skill_type") or "python").strip()[:64] or "python"
    implementation_ref = str(payload.get("implementation_ref") or "").strip()[:512]
    if not implementation_ref:
        raise ValueError("implementation_ref required")
    visibility = _catalog_skill_visibility(payload.get("visibility"))
    owner = str(profile.get("email") or actor)
    existing = conn.execute(
        "SELECT skill_id, owner_email, tenant_id FROM main.admin_skills WHERE name = ? LIMIT 1",
        [name],
    ).fetchone()
    if existing:
        if str(existing[1] or "").strip().lower() != owner or str(existing[2] or "") != tenant_id:
            raise ValueError(f"Catalog skill name already exists: {name}")
        conn.execute(
            "UPDATE main.admin_skills "
            "SET description = ?, skill_type = ?, implementation_ref = ?, visibility = ?, "
            "active = true, updated_at = CURRENT_TIMESTAMP "
            "WHERE skill_id = ?",
            [description, skill_type, implementation_ref, visibility, str(existing[0])],
        )
        return

    conn.execute(
        "INSERT INTO main.admin_skills "
        "(skill_id, name, description, skill_type, implementation_ref, owner_email, tenant_id, visibility, active) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, true)",
        [f"skl_{uuid.uuid4().hex}", name, description, skill_type, implementation_ref, owner, tenant_id, visibility],
    )


def _apply_deactivate_catalog_skill(conn: Any, payload: dict) -> None:
    ensure_admin_worker_catalog_schema(conn)
    actor = str(payload.get("actor_email") or "system").strip().lower() or "system"
    profile = ensure_profile_for_user(conn, email=actor)
    tenant_id = str(payload.get("tenant_id") or profile.get("tenant_id") or "default").strip() or "default"
    if str(profile.get("tenant_id") or tenant_id) != tenant_id:
        raise ValueError(f"Tenant mismatch for actor: {actor}")

    name = _catalog_skill_name(payload.get("name"))
    conn.execute(
        "UPDATE main.admin_skills "
        "SET active = false, updated_at = CURRENT_TIMESTAMP "
        "WHERE name = ? AND owner_email = ? AND tenant_id = ?",
        [name, str(profile.get("email") or actor), tenant_id],
    )


def _apply_hard_delete_catalog_skill(conn: Any, payload: dict) -> None:
    ensure_admin_worker_catalog_schema(conn)
    actor = str(payload.get("actor_email") or "system").strip().lower() or "system"
    profile = ensure_profile_for_user(conn, email=actor)
    tenant_id = str(payload.get("tenant_id") or profile.get("tenant_id") or "default").strip() or "default"
    if str(profile.get("tenant_id") or tenant_id) != tenant_id:
        raise ValueError(f"Tenant mismatch for actor: {actor}")

    name = _catalog_skill_name(payload.get("name"))
    owner = str(profile.get("email") or actor)
    row = conn.execute(
        "SELECT skill_id, owner_email, tenant_id FROM main.admin_skills WHERE name = ? LIMIT 1",
        [name],
    ).fetchone()
    if not row:
        return
    skill_id = str(row[0])
    if str(row[1] or "").strip().lower() != owner.strip().lower() or str(row[2] or "") != tenant_id:
        raise ValueError(f"Catalog skill not owned by actor: {name}")
    conn.execute("DELETE FROM main.admin_worker_skills WHERE skill_id = ?", [skill_id])
    conn.execute("DELETE FROM main.admin_skills WHERE skill_id = ?", [skill_id])


def _apply_deactivate_worker(conn: Any, payload: dict) -> None:
    worker_id = str(payload["worker_id"])
    tenant_id = str(payload.get("tenant_id") or "default")
    conn.execute(
        "UPDATE main.admin_worker_catalog "
        "SET active = false, status = 'inactive', updated_at = CURRENT_TIMESTAMP "
        "WHERE worker_id = ? AND tenant_id = ?",
        [worker_id, tenant_id],
    )


def _catalog_worker_actor(payload: dict) -> str:
    actor = str(payload.get("actor_email") or "system").strip().lower() or "system"
    if "@" not in actor:
        raise ValueError("actor_email required for catalog worker mutation")
    return actor


def _catalog_worker_id(payload: dict) -> str:
    worker_id = str(payload.get("worker_id") or "").strip()
    if not worker_id:
        raise ValueError("worker_id required")
    return worker_id


def _apply_update_catalog_worker_file(conn: Any, payload: dict) -> None:
    actor = _catalog_worker_actor(payload)
    worker_id = _catalog_worker_id(payload)
    worker = get_visible_worker_for_actor(conn, actor_email=actor, worker_id=worker_id)
    if not worker:
        raise ValueError(f"Worker not visible in catalog: {worker_id}")
    update_catalog_worker_file(
        conn,
        worker_uid=str(worker["worker_uid"]),
        file_path=str(payload.get("file_path") or ""),
        content=str(payload.get("content") or ""),
        actor_email=actor,
    )


def _apply_deactivate_catalog_worker(conn: Any, payload: dict) -> None:
    actor = _catalog_worker_actor(payload)
    worker_id = _catalog_worker_id(payload)
    worker = deactivate_visible_worker_for_actor(conn, actor_email=actor, worker_id=worker_id)
    if not worker:
        raise ValueError(f"Worker not found in catalog: {worker_id}")


def _apply_reactivate_catalog_worker(conn: Any, payload: dict) -> None:
    actor = _catalog_worker_actor(payload)
    worker_id = _catalog_worker_id(payload)
    worker = reactivate_visible_worker_for_actor(conn, actor_email=actor, worker_id=worker_id)
    if not worker:
        raise ValueError(f"Inactive worker not found in catalog: {worker_id}")


def _apply_hard_delete_catalog_worker(conn: Any, payload: dict) -> None:
    actor = _catalog_worker_actor(payload)
    worker_id = _catalog_worker_id(payload)
    worker = hard_delete_visible_worker_for_actor(conn, actor_email=actor, worker_id=worker_id)
    if not worker:
        raise ValueError(f"Worker not found in catalog: {worker_id}")


def _require_worker_uid_for_tenant(conn: Any, worker_uid: str, tenant_id: str) -> None:
    row = conn.execute(
        "SELECT worker_uid FROM main.admin_worker_catalog "
        "WHERE worker_uid = ? AND tenant_id = ? AND active = true",
        [worker_uid, tenant_id],
    ).fetchone()
    if not row:
        raise ValueError(f"Worker not found for tenant: {worker_uid}")


def _apply_import_templates_to_catalog(conn: Any, payload: dict) -> None:
    from duckclaw.admin_template_import import import_templates_to_catalog

    import_templates_to_catalog(
        conn,
        owner_email=str(payload.get("actor_email") or "system"),
        templates_root=str(payload.get("templates_root") or ""),
        include_prefixes=list(payload.get("include_prefixes") or []),
        include_template_ids=list(payload.get("include_template_ids") or []),
    )


def _apply_upsert_worker_context(conn: Any, payload: dict) -> None:
    from duckclaw.admin_worker_catalog import add_catalog_worker_context

    worker_uid = str(payload.get("worker_uid") or "").strip()
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    _require_worker_uid_for_tenant(conn, worker_uid, tenant_id)
    add_catalog_worker_context(
        conn,
        worker_uid=worker_uid,
        title=str(payload.get("title") or ""),
        content_md=str(payload.get("content_md") or ""),
        sort_order=int(payload.get("sort_order") or 0),
        actor_email=str(payload.get("actor_email") or "system"),
    )


def _apply_reorder_worker_contexts(conn: Any, payload: dict) -> None:
    from duckclaw.admin_worker_catalog import reorder_worker_contexts

    worker_uid = str(payload.get("worker_uid") or "").strip()
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    _require_worker_uid_for_tenant(conn, worker_uid, tenant_id)
    reorder_worker_contexts(
        conn,
        worker_uid=worker_uid,
        items=list(payload.get("items") or []),
    )


def _apply_deactivate_worker_context(conn: Any, payload: dict) -> None:
    from duckclaw.admin_worker_catalog import deactivate_worker_context

    worker_uid = str(payload.get("worker_uid") or "").strip()
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    _require_worker_uid_for_tenant(conn, worker_uid, tenant_id)
    result = deactivate_worker_context(
        conn,
        worker_uid=worker_uid,
        context_id=str(payload.get("context_id") or ""),
        actor_email=str(payload.get("actor_email") or "system"),
    )
    if not result:
        raise ValueError(f"Context not found: {payload.get('context_id')}")


def _stable_capability_id(name: str) -> str:
    digest = hashlib.sha256(name.encode("utf-8")).hexdigest()
    return f"cap_{digest[:24]}"


def _normalize_capability_token(raw: Any, *, field: str, max_len: int = 128) -> str:
    value = str(raw or "").strip()
    if not value:
        raise ValueError(f"{field} required")
    if len(value) > max_len:
        raise ValueError(f"{field} too long")
    return value


def _json_payload(raw: Any, *, max_len: int = 8192) -> str:
    value = json.dumps(raw if isinstance(raw, dict) else {}, ensure_ascii=False, default=str)
    if len(value) > max_len:
        raise ValueError("JSON payload too large")
    return value


def _apply_upsert_worker_capability(conn: Any, payload: dict) -> None:
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    worker_id = _normalize_capability_token(payload.get("worker_id"), field="worker_id")
    capability_name = _normalize_capability_token(payload.get("capability_name"), field="capability_name")
    kind = _normalize_capability_token(payload.get("kind") or "runtime_policy", field="kind", max_len=64)
    provider = _normalize_capability_token(payload.get("provider") or "duckclaw", field="provider")
    permission = _normalize_capability_token(payload.get("permission") or "use", field="permission", max_len=32)
    description = str(payload.get("description") or "").strip()[:1024]
    risk_level = str(payload.get("risk_level") or "low").strip()[:32] or "low"
    requires_secret = bool(payload.get("requires_secret", False))
    requires_network = bool(payload.get("requires_network", False))
    schema_json = _json_payload(payload.get("capability_schema") or payload.get("schema"))
    config_json = _json_payload(payload.get("config"))
    policy_json = _json_payload(payload.get("policy"))

    worker_uid = _resolve_worker_uid(conn, worker_id, tenant_id)
    if not worker_uid:
        raise ValueError(f"Worker not found: {worker_id}")

    existing_capability = conn.execute(
        "SELECT capability_id FROM main.admin_capabilities WHERE name = ?",
        [capability_name],
    ).fetchone()
    capability_id = str(existing_capability[0]) if existing_capability else _stable_capability_id(capability_name)
    if existing_capability:
        conn.execute(
            "UPDATE main.admin_capabilities "
            "SET kind = ?, provider = ?, description = ?, schema_json = ?, "
            "risk_level = ?, requires_secret = ?, requires_network = ?, active = true, "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE capability_id = ?",
            [
                kind,
                provider,
                description,
                schema_json,
                risk_level,
                requires_secret,
                requires_network,
                capability_id,
            ],
        )
    else:
        conn.execute(
            "INSERT INTO main.admin_capabilities "
            "(capability_id, name, kind, provider, description, schema_json, "
            "risk_level, requires_secret, requires_network, active) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, true)",
            [
                capability_id,
                capability_name,
                kind,
                provider,
                description,
                schema_json,
                risk_level,
                requires_secret,
                requires_network,
            ],
        )

    existing_grant = conn.execute(
        "SELECT capability_id FROM main.admin_worker_capabilities "
        "WHERE worker_uid = ? AND capability_id = ?",
        [worker_uid, capability_id],
    ).fetchone()
    if existing_grant:
        conn.execute(
            "UPDATE main.admin_worker_capabilities "
            "SET permission = ?, config_json = ?, policy_json = ?, enabled = true, "
            "updated_at = CURRENT_TIMESTAMP "
            "WHERE worker_uid = ? AND capability_id = ?",
            [permission, config_json, policy_json, worker_uid, capability_id],
        )
    else:
        conn.execute(
            "INSERT INTO main.admin_worker_capabilities "
            "(worker_uid, capability_id, permission, config_json, policy_json, enabled) "
            "VALUES (?, ?, ?, ?, ?, true)",
            [worker_uid, capability_id, permission, config_json, policy_json],
        )


from duckclaw.write_handlers.registry import register_handler

register_handler("upsert_worker", _apply_upsert_worker)
register_handler("upsert_user_agent", _apply_upsert_user_agent)
register_handler("upsert_catalog_skill", _apply_upsert_catalog_skill)
register_handler("deactivate_catalog_skill", _apply_deactivate_catalog_skill)
register_handler("hard_delete_catalog_skill", _apply_hard_delete_catalog_skill)
register_handler("deactivate_worker", _apply_deactivate_worker)
register_handler("update_catalog_worker_file", _apply_update_catalog_worker_file)
register_handler("deactivate_catalog_worker", _apply_deactivate_catalog_worker)
register_handler("reactivate_catalog_worker", _apply_reactivate_catalog_worker)
register_handler("hard_delete_catalog_worker", _apply_hard_delete_catalog_worker)
register_handler("import_templates_to_catalog", _apply_import_templates_to_catalog)
register_handler("upsert_worker_context", _apply_upsert_worker_context)
register_handler("reorder_worker_contexts", _apply_reorder_worker_contexts)
register_handler("deactivate_worker_context", _apply_deactivate_worker_context)
register_handler("upsert_worker_capability", _apply_upsert_worker_capability)
