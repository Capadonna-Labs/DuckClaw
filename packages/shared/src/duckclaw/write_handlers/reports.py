"""Typed write handlers for report templates and instances."""
from __future__ import annotations

import json
import uuid
from typing import Any

from duckclaw.report_engine.preview import render_preview_html
from duckclaw.report_engine.state import init_state_from_schema, patch_section
from duckclaw.write_handlers.workspace import _require_project_access


def _json_dump(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


def _require_template(conn: Any, template_id: str, tenant_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT template_id, tenant_id, owner_email, section_schema_json, template_uri, active, visibility
        FROM main.admin_report_templates
        WHERE template_id = ? AND tenant_id = ?
        LIMIT 1
        """,
        [template_id, tenant_id],
    ).fetchone()
    if not row or not row[5]:
        raise ValueError(f"Plantilla no encontrada: {template_id}")
    return {
        "template_id": str(row[0]),
        "tenant_id": str(row[1]),
        "owner_email": str(row[2]),
        "section_schema": json.loads(str(row[3] or "[]")),
        "template_uri": str(row[4]),
        "visibility": str(row[6] or "private"),
    }


def _template_visible_to_actor(template: dict[str, Any], actor_email: str) -> bool:
    actor = (actor_email or "").strip().lower()
    owner = str(template.get("owner_email") or "").strip().lower()
    if actor and actor == owner:
        return True
    return str(template.get("visibility") or "private").strip().lower() == "tenant"


def _require_instance(conn: Any, instance_id: str, tenant_id: str) -> dict[str, Any]:
    row = conn.execute(
        """
        SELECT instance_id, template_id, tenant_id, owner_email, project_id, title, period_key,
               state_json, status, active
        FROM main.admin_report_instances
        WHERE instance_id = ? AND tenant_id = ?
        LIMIT 1
        """,
        [instance_id, tenant_id],
    ).fetchone()
    if not row or not row[9]:
        raise ValueError(f"Instancia no encontrada: {instance_id}")
    return {
        "instance_id": str(row[0]),
        "template_id": str(row[1]),
        "tenant_id": str(row[2]),
        "owner_email": str(row[3]),
        "project_id": str(row[4] or ""),
        "title": str(row[5]),
        "period_key": str(row[6] or ""),
        "state": json.loads(str(row[7] or "{}")),
        "status": str(row[8] or "draft"),
    }


def _assert_actor_on_instance(conn: Any, instance: dict[str, Any], actor_email: str) -> None:
    actor = (actor_email or "system").strip().lower()
    owner = str(instance.get("owner_email") or "").strip().lower()
    if actor == owner:
        return
    project_id = str(instance.get("project_id") or "").strip()
    if project_id:
        _require_project_access(
            conn,
            project_id=project_id,
            tenant_id=str(instance.get("tenant_id") or "default"),
            actor_email=actor_email,
        )
        return
    raise ValueError("Acceso denegado a la instancia del informe")


def _apply_upsert_report_template(conn: Any, payload: dict) -> None:
    template_id = str(payload.get("template_id") or f"rtpl_{uuid.uuid4().hex[:12]}").strip()
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    owner = str(payload.get("actor_email") or "system").strip() or "system"
    name = str(payload.get("name") or template_id).strip()
    description = str(payload.get("description") or "").strip()
    template_uri = str(payload.get("template_uri") or "").strip()
    if not template_uri:
        raise ValueError("template_uri requerido")
    section_schema = payload.get("section_schema") or []
    if not isinstance(section_schema, list):
        raise ValueError("section_schema debe ser lista")
    analyzer_mode = str(payload.get("analyzer_mode") or "jinja").strip()
    visibility = str(payload.get("visibility") or "private").strip()

    existing = conn.execute(
        """
        SELECT template_id, tenant_id, owner_email, active
        FROM main.admin_report_templates
        WHERE template_id = ?
        LIMIT 1
        """,
        [template_id],
    ).fetchone()
    schema_json = _json_dump(section_schema)
    if existing:
        existing_tenant = str(existing[1] or "")
        existing_owner = str(existing[2] or "").strip().lower()
        if existing_tenant != tenant_id:
            raise ValueError("template_id pertenece a otro tenant")
        if existing_owner and existing_owner != owner.strip().lower():
            raise ValueError(
                "No puedes sobrescribir una plantilla de otro propietario. "
                "Usa otro template_id o pide visibilidad tenant al dueño."
            )
        conn.execute(
            """
            UPDATE main.admin_report_templates
            SET name = ?, description = ?, template_uri = ?,
                section_schema_json = ?, analyzer_mode = ?, visibility = ?, active = true,
                updated_at = CURRENT_TIMESTAMP
            WHERE template_id = ? AND tenant_id = ?
            """,
            [
                name,
                description,
                template_uri,
                schema_json,
                analyzer_mode,
                visibility,
                template_id,
                tenant_id,
            ],
        )
    else:
        conn.execute(
            """
            INSERT INTO main.admin_report_templates
            (template_id, tenant_id, owner_email, name, description, template_uri,
             section_schema_json, analyzer_mode, visibility)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                template_id,
                tenant_id,
                owner,
                name,
                description,
                template_uri,
                schema_json,
                analyzer_mode,
                visibility,
            ],
        )


def _apply_create_report_instance(conn: Any, payload: dict) -> None:
    instance_id = str(payload.get("instance_id") or f"rpt_{uuid.uuid4().hex[:12]}").strip()
    template_id = str(payload.get("template_id") or "").strip()
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    owner = str(payload.get("actor_email") or "system").strip() or "system"
    title = str(payload.get("title") or "Informe").strip()
    # Legacy column retained in schema; product identity is instance_id only.
    period_key = ""
    project_id = str(payload.get("project_id") or "").strip()
    conversation_id = str(payload.get("conversation_id") or "").strip()

    if not template_id:
        raise ValueError("template_id requerido")
    template = _require_template(conn, template_id, tenant_id)
    if not _template_visible_to_actor(template, owner):
        raise ValueError(
            "Plantilla no visible para este usuario "
            "(debe ser propietaria o visibility=tenant)."
        )
    if project_id:
        _require_project_access(conn, project_id=project_id, tenant_id=tenant_id, actor_email=owner)

    state = init_state_from_schema(template["section_schema"])
    preview = render_preview_html(
        title=title,
        period_key="",
        state=state,
        section_schema=template["section_schema"],
    )

    existing = conn.execute(
        "SELECT instance_id FROM main.admin_report_instances WHERE instance_id = ?",
        [instance_id],
    ).fetchone()
    state_json = _json_dump(state)
    if existing:
        conn.execute(
            """
            UPDATE main.admin_report_instances
            SET template_id = ?, tenant_id = ?, owner_email = ?, project_id = ?, title = ?,
                period_key = ?, state_json = ?, preview_html = ?, conversation_id = ?,
                status = 'draft', active = true, updated_at = CURRENT_TIMESTAMP
            WHERE instance_id = ?
            """,
            [
                template_id,
                tenant_id,
                owner,
                project_id,
                title,
                period_key,
                state_json,
                preview,
                conversation_id,
                instance_id,
            ],
        )
    else:
        conn.execute(
            """
            INSERT INTO main.admin_report_instances
            (instance_id, template_id, tenant_id, owner_email, project_id, title, period_key,
             state_json, preview_html, conversation_id, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'draft')
            """,
            [
                instance_id,
                template_id,
                tenant_id,
                owner,
                project_id,
                title,
                period_key,
                state_json,
                preview,
                conversation_id,
            ],
        )

    # Índice Productividad (lane=report)
    try:
        prod_id = f"prep_{instance_id}"
        existing_prod = conn.execute(
            "SELECT artifact_id FROM main.admin_productivity_artifacts WHERE artifact_id = ?",
            [prod_id],
        ).fetchone()
        if existing_prod:
            conn.execute(
                """
                UPDATE main.admin_productivity_artifacts
                SET title = ?, active = true, updated_at = CURRENT_TIMESTAMP
                WHERE artifact_id = ?
                """,
                [title, prod_id],
            )
        else:
            conn.execute(
                """
                INSERT INTO main.admin_productivity_artifacts
                (artifact_id, tenant_id, owner_email, lane, title, filename, uri,
                 source_kind, source_ref, mime, byte_size, active)
                VALUES (?, ?, ?, 'report', ?, '', '', 'report_engine', ?, '', 0, true)
                """,
                [prod_id, tenant_id, owner, title, instance_id],
            )
    except Exception:
        # Tabla puede no existir aún en hubs sin migración 2
        pass


def _apply_patch_report_section(conn: Any, payload: dict) -> None:
    instance_id = str(payload.get("instance_id") or "").strip()
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    actor = str(payload.get("actor_email") or "system").strip() or "system"
    section_id = str(payload.get("section_id") or "").strip()
    content = str(payload.get("content") or "")
    mode = str(payload.get("mode") or "replace").strip().lower()
    mark_complete = bool(payload.get("mark_complete", False))

    instance = _require_instance(conn, instance_id, tenant_id)
    _assert_actor_on_instance(conn, instance, actor)
    template = _require_template(conn, str(instance["template_id"]), tenant_id)

    state = patch_section(
        instance["state"],
        section_id=section_id,
        content=content,
        mode="append" if mode == "append" else "replace",
        mark_complete=mark_complete,
    )
    preview = render_preview_html(
        title=str(instance["title"]),
        period_key=str(instance["period_key"]),
        state=state,
        section_schema=template["section_schema"],
    )
    conn.execute(
        """
        UPDATE main.admin_report_instances
        SET state_json = ?, preview_html = ?, updated_at = CURRENT_TIMESTAMP
        WHERE instance_id = ? AND tenant_id = ?
        """,
        [_json_dump(state), preview, instance_id, tenant_id],
    )


def _apply_update_report_instance_render(conn: Any, payload: dict) -> None:
    instance_id = str(payload.get("instance_id") or "").strip()
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    actor = str(payload.get("actor_email") or "system").strip() or "system"
    rendered_docx_uri = str(payload.get("rendered_docx_uri") or "").strip()
    status = str(payload.get("status") or "draft").strip()

    instance = _require_instance(conn, instance_id, tenant_id)
    _assert_actor_on_instance(conn, instance, actor)
    conn.execute(
        """
        UPDATE main.admin_report_instances
        SET rendered_docx_uri = ?, status = ?, updated_at = CURRENT_TIMESTAMP
        WHERE instance_id = ? AND tenant_id = ?
        """,
        [rendered_docx_uri, status, instance_id, tenant_id],
    )


def _apply_soft_delete_report_instance(conn: Any, payload: dict) -> None:
    instance_id = str(payload.get("instance_id") or "").strip()
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    actor = str(payload.get("actor_email") or "system").strip() or "system"
    if not instance_id:
        raise ValueError("instance_id requerido")

    instance = _require_instance(conn, instance_id, tenant_id)
    _assert_actor_on_instance(conn, instance, actor)
    conn.execute(
        """
        UPDATE main.admin_report_instances
        SET active = false, status = 'archived', updated_at = CURRENT_TIMESTAMP
        WHERE instance_id = ? AND tenant_id = ?
        """,
        [instance_id, tenant_id],
    )
    try:
        conn.execute(
            """
            UPDATE main.admin_productivity_artifacts
            SET active = false, updated_at = CURRENT_TIMESTAMP
            WHERE source_ref = ? AND lane = 'report' AND tenant_id = ?
            """,
            [instance_id, tenant_id],
        )
    except Exception:
        pass


def _apply_soft_delete_report_template(conn: Any, payload: dict) -> None:
    template_id = str(payload.get("template_id") or "").strip()
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    actor = str(payload.get("actor_email") or "system").strip().lower() or "system"
    if not template_id:
        raise ValueError("template_id requerido")

    template = _require_template(conn, template_id, tenant_id)
    owner = str(template.get("owner_email") or "").strip().lower()
    if actor != owner:
        raise ValueError("Solo el propietario puede eliminar la plantilla")

    conn.execute(
        """
        UPDATE main.admin_report_templates
        SET active = false, updated_at = CURRENT_TIMESTAMP
        WHERE template_id = ? AND tenant_id = ?
        """,
        [template_id, tenant_id],
    )
    # Archiva instancias activas de esa plantilla del mismo owner (evita huérfanos en lista).
    conn.execute(
        """
        UPDATE main.admin_report_instances
        SET active = false, status = 'archived', updated_at = CURRENT_TIMESTAMP
        WHERE template_id = ?
          AND tenant_id = ?
          AND lower(owner_email) = lower(?)
          AND active = true
        """,
        [template_id, tenant_id, actor],
    )


from duckclaw.write_handlers.registry import register_handler

register_handler("upsert_report_template", _apply_upsert_report_template)
register_handler("create_report_instance", _apply_create_report_instance)
register_handler("patch_report_section", _apply_patch_report_section)
register_handler("update_report_instance_render", _apply_update_report_instance_render)
register_handler("soft_delete_report_instance", _apply_soft_delete_report_instance)
register_handler("soft_delete_report_template", _apply_soft_delete_report_template)
