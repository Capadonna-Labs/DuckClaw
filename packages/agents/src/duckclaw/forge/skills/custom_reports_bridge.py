"""Custom reports: publish HTML al vault vía StateDelta + lectura LLM usage (gateway hub)."""

from __future__ import annotations

import json
import os
import re
from typing import Any, List

from langchain_core.tools import StructuredTool

from duckclaw.utils.logger import log_tool_execution_sync

_MAX_HTML_BYTES = 512 * 1024
_ALLOWED_SCRIPT_CDN = (
    "cdn.jsdelivr.net",
    "cdnjs.cloudflare.com",
    "unpkg.com",
    "cdn.tailwindcss.com",
)


def _validate_html_content(html: str) -> str | None:
    raw = str(html or "")
    if len(raw.encode("utf-8")) > _MAX_HTML_BYTES:
        return f"HTML excede { _MAX_HTML_BYTES // 1024 }KB"
    low = raw.lower()
    if "</html>" not in low and "<!doctype" not in low:
        return "Estructura HTML inválida: falta </html> o <!DOCTYPE>"
    for m in re.finditer(r'<script[^>]+src=["\']([^"\']+)["\']', raw, re.IGNORECASE):
        src = m.group(1).lower()
        if not any(cdn in src for cdn in _ALLOWED_SCRIPT_CDN):
            return f"script src no permitido: {m.group(1)}"
    return None


def _reports_state_delta_base(db: Any) -> dict[str, str]:
    path = str(getattr(db, "_path", "") or "").strip()
    tenant = (os.environ.get("DUCKCLAW_TENANT_ID") or "default").strip() or "default"
    user = (os.environ.get("DUCKCLAW_ADMIN_EMAIL") or os.environ.get("DUCKCLAW_OWNER_EMAIL") or "admin-ui").strip()
    return {
        "tenant_id": tenant,
        "user_id": user or "admin-ui",
        "target_db_path": path,
    }


@log_tool_execution_sync(name="publish_custom_report")
def _publish_custom_report_impl(
    db: Any,
    *,
    report_id: str,
    html_content: str,
    title: str = "Reporte",
    created_by: str = "",
) -> str:
    from duckclaw.forge.skills.reports_state_delta import push_reports_state_delta_sync

    rid = (report_id or "").strip()
    if not rid:
        return json.dumps({"status": "error", "message": "report_id requerido"}, ensure_ascii=False)

    err = _validate_html_content(html_content)
    if err:
        return json.dumps({"status": "error", "message": err}, ensure_ascii=False)

    base = _reports_state_delta_base(db)
    if not base.get("target_db_path"):
        return json.dumps({"status": "error", "message": "vault_db_path no disponible"}, ensure_ascii=False)

    payload = {
        **base,
        "delta_type": "CUSTOM_REPORT_UPSERT",
        "mutation": {
            "report_id": rid,
            "title": (title or "Reporte").strip()[:200],
            "html_content": html_content,
            "created_by": (created_by or base.get("user_id") or "").strip()[:200],
        },
    }
    ok = push_reports_state_delta_sync(payload, duckclaw_db=db)
    if not ok:
        return json.dumps(
            {"status": "error", "message": "No se pudo encolar CUSTOM_REPORT_UPSERT"},
            ensure_ascii=False,
        )
    return json.dumps(
        {"status": "success", "report_id": rid, "message": "Reporte encolado para publicación"},
        ensure_ascii=False,
    )


@log_tool_execution_sync(name="read_llm_usage_summary")
def _read_llm_usage_summary_impl(db: Any, *, days: int = 7) -> str:
    """Agregados de tokens/costo desde gateway hub main.llm_usage_log (solo lectura)."""
    del db
    try:
        from duckclaw import DuckClaw
        from duckclaw.gateway_db import get_gateway_db_path

        hub = (get_gateway_db_path() or "").strip()
        if not hub:
            return json.dumps({"error": "gateway_db_path no configurado"}, ensure_ascii=False)
        days_clamped = max(1, min(int(days or 7), 90))
        con = DuckClaw(hub, read_only=True)
        try:
            con.query("SELECT 1 FROM main.llm_usage_log LIMIT 1")
        except Exception:
            return json.dumps({"summary": {}, "series": [], "note": "llm_usage_log vacía o ausente"}, ensure_ascii=False)
        try:
            summary = con.query(
                f"""
                SELECT sum(input_tokens) AS input_tokens,
                       sum(output_tokens) AS output_tokens,
                       sum(total_tokens) AS total_tokens,
                       round(sum(cost_usd), 6) AS cost_usd
                FROM main.llm_usage_log
                WHERE created_at >= now() - INTERVAL '{days_clamped} days'
                """
            ).fetchone()
            series = con.query(
                f"""
                SELECT worker_id AS label,
                       sum(total_tokens) AS total_tokens,
                       round(sum(cost_usd), 6) AS cost_usd
                FROM main.llm_usage_log
                WHERE created_at >= now() - INTERVAL '{days_clamped} days'
                  AND worker_id IS NOT NULL AND trim(worker_id) != ''
                GROUP BY worker_id
                ORDER BY total_tokens DESC
                LIMIT 20
                """
            ).fetchall()
        finally:
            con.close()
        return json.dumps(
            {
                "days": days_clamped,
                "summary": dict(summary) if summary else {},
                "series": [dict(r) for r in (series or [])],
            },
            ensure_ascii=False,
            default=str,
        )
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def register_custom_reports_skill(tools_list: List[Any], db: Any, spec: Any) -> None:
    skills = getattr(spec, "skills_list", None) or []

    if "publish_custom_report" in skills:
        tools_list.append(
            StructuredTool.from_function(
                lambda report_id, html_content, title="Reporte", created_by="": _publish_custom_report_impl(
                    db,
                    report_id=report_id,
                    html_content=html_content,
                    title=title,
                    created_by=created_by,
                ),
                name="publish_custom_report",
                description=(
                    "Persiste un reporte HTML completo en main.custom_reports del vault activo "
                    "(StateDelta). Usar tras generar/actualizar el dashboard."
                ),
            )
        )

    if "read_llm_usage_summary" in skills:
        tools_list.append(
            StructuredTool.from_function(
                lambda days=7: _read_llm_usage_summary_impl(db, days=days),
                name="read_llm_usage_summary",
                description="Lee agregados de tokens y coste USD desde main.llm_usage_log (gateway hub).",
            )
        )
