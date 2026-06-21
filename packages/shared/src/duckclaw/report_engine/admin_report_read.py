"""Read-model for report templates and instances."""

from __future__ import annotations

import json
from typing import Any

from duckclaw.report_engine.state import summarize_status


def _parse_json(raw: Any, default: Any) -> Any:
    if raw is None:
        return default
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(str(raw))
    except Exception:
        return default


def list_report_templates(
    db: Any,
    *,
    tenant_id: str,
    actor_email: str,
    limit: int = 50,
) -> list[dict[str, Any]]:
    actor = (actor_email or "system").strip().lower()
    tid = (tenant_id or "default").strip() or "default"
    rows = db.execute(
        """
        SELECT template_id, tenant_id, owner_email, name, description, template_uri,
               section_schema_json, analyzer_mode, visibility, created_at, updated_at
        FROM main.admin_report_templates
        WHERE tenant_id = ?
          AND active = true
          AND (lower(owner_email) = lower(?) OR visibility = 'tenant')
        ORDER BY updated_at DESC
        LIMIT ?
        """,
        [tid, actor, max(1, min(int(limit), 200))],
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        out.append(
            {
                "template_id": str(row[0]),
                "tenant_id": str(row[1]),
                "owner_email": str(row[2]),
                "name": str(row[3]),
                "description": str(row[4] or ""),
                "template_uri": str(row[5]),
                "section_schema": _parse_json(row[6], []),
                "analyzer_mode": str(row[7] or "jinja"),
                "visibility": str(row[8] or "private"),
            }
        )
    return out


def get_report_template(db: Any, *, template_id: str, tenant_id: str) -> dict[str, Any] | None:
    row = db.execute(
        """
        SELECT template_id, tenant_id, owner_email, name, description, template_uri,
               section_schema_json, analyzer_mode, visibility, active
        FROM main.admin_report_templates
        WHERE template_id = ? AND tenant_id = ?
        LIMIT 1
        """,
        [template_id, tenant_id],
    ).fetchone()
    if not row or not row[9]:
        return None
    return {
        "template_id": str(row[0]),
        "tenant_id": str(row[1]),
        "owner_email": str(row[2]),
        "name": str(row[3]),
        "description": str(row[4] or ""),
        "template_uri": str(row[5]),
        "section_schema": _parse_json(row[6], []),
        "analyzer_mode": str(row[7] or "jinja"),
        "visibility": str(row[8] or "private"),
    }


def list_report_instances(
    db: Any,
    *,
    tenant_id: str,
    actor_email: str,
    project_id: str = "",
    limit: int = 50,
) -> list[dict[str, Any]]:
    actor = (actor_email or "system").strip().lower()
    tid = (tenant_id or "default").strip() or "default"
    pid = (project_id or "").strip()
    params: list[Any] = [tid, actor, actor, actor]
    project_clause = ""
    if pid:
        project_clause = " AND i.project_id = ?"
        params.append(pid)
    params.append(max(1, min(int(limit), 200)))
    rows = db.execute(
        f"""
        SELECT i.instance_id, i.template_id, i.title, i.period_key, i.project_id,
               i.status, i.state_json, i.preview_html, i.rendered_docx_uri,
               i.conversation_id, i.updated_at,
               t.name AS template_name, t.section_schema_json
        FROM main.admin_report_instances i
        LEFT JOIN main.admin_report_templates t
          ON t.template_id = i.template_id AND t.tenant_id = i.tenant_id
        WHERE i.tenant_id = ?
          AND i.active = true
          AND (
            lower(i.owner_email) = lower(?)
            OR (
              i.project_id != ''
              AND EXISTS (
                SELECT 1
                FROM main.admin_projects p
                LEFT JOIN main.admin_project_members m
                  ON m.project_id = p.project_id AND lower(m.email) = lower(?)
                WHERE p.project_id = i.project_id
                  AND p.active = true
                  AND (lower(p.owner_email) = lower(?) OR m.email IS NOT NULL)
              )
            )
          )
          {project_clause}
        ORDER BY i.updated_at DESC
        LIMIT ?
        """,
        params,
    ).fetchall()
    out: list[dict[str, Any]] = []
    for row in rows:
        schema = _parse_json(row[12], [])
        state = _parse_json(row[6], {"sections": {}})
        summary = summarize_status(state, schema)
        out.append(
            {
                "instance_id": str(row[0]),
                "template_id": str(row[1]),
                "title": str(row[2]),
                "period_key": str(row[3] or ""),
                "project_id": str(row[4] or ""),
                "status": str(row[5] or "draft"),
                "preview_html": str(row[7] or ""),
                "rendered_docx_uri": str(row[8] or ""),
                "conversation_id": str(row[9] or ""),
                "updated_at": str(row[10] or ""),
                "template_name": str(row[11] or ""),
                "progress": summary,
            }
        )
    return out


def get_report_instance(db: Any, *, instance_id: str, tenant_id: str) -> dict[str, Any] | None:
    row = db.execute(
        """
        SELECT instance_id, template_id, tenant_id, owner_email, project_id, title, period_key,
               state_json, status, preview_html, rendered_docx_uri, conversation_id, active
        FROM main.admin_report_instances
        WHERE instance_id = ? AND tenant_id = ?
        LIMIT 1
        """,
        [instance_id, tenant_id],
    ).fetchone()
    if not row or not row[12]:
        return None
    return {
        "instance_id": str(row[0]),
        "template_id": str(row[1]),
        "tenant_id": str(row[2]),
        "owner_email": str(row[3]),
        "project_id": str(row[4] or ""),
        "title": str(row[5]),
        "period_key": str(row[6] or ""),
        "state": _parse_json(row[7], {"sections": {}}),
        "status": str(row[8] or "draft"),
        "preview_html": str(row[9] or ""),
        "rendered_docx_uri": str(row[10] or ""),
        "conversation_id": str(row[11] or ""),
    }


def actor_can_access_instance(
    db: Any,
    *,
    instance: dict[str, Any],
    actor_email: str,
) -> bool:
    actor = (actor_email or "").strip().lower()
    if not actor:
        return False
    if str(instance.get("owner_email") or "").strip().lower() == actor:
        return True
    project_id = str(instance.get("project_id") or "").strip()
    if not project_id:
        return False
    row = db.execute(
        """
        SELECT 1
        FROM main.admin_projects p
        LEFT JOIN main.admin_project_members m
          ON m.project_id = p.project_id AND lower(m.email) = lower(?)
        WHERE p.project_id = ?
          AND p.active = true
          AND (lower(p.owner_email) = lower(?) OR m.email IS NOT NULL)
        LIMIT 1
        """,
        [actor, project_id, actor],
    ).fetchone()
    return bool(row)
