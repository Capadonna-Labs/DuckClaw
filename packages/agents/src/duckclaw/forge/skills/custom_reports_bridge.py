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
    # Vault del playground admin (mismo que el iframe); evita divergencia con vault dedicado del worker.
    from duckclaw.gateway_db import resolve_env_duckdb_path
    from duckclaw.vaults import infer_private_folder_uid_from_db_path, resolve_user_id_for_db_path

    path = (os.environ.get("DUCKCLAW_ADMIN_PLAYGROUND_VAULT") or "").strip()
    if not path:
        path = str(getattr(db, "_path", "") or "").strip()
    path = resolve_env_duckdb_path(path)
    tenant = (os.environ.get("DUCKCLAW_TENANT_ID") or "default").strip() or "default"
    user = "admin-ui"
    for candidate in (
        os.environ.get("DUCKCLAW_OWNER_ID"),
        os.environ.get("DUCKCLAW_ADMIN_TELEGRAM_USER_ID"),
        os.environ.get("DUCKCLAW_ADMIN_EMAIL"),
        os.environ.get("DUCKCLAW_OWNER_EMAIL"),
        "admin-ui",
    ):
        c = (candidate or "").strip()
        if not c:
            continue
        resolved = resolve_user_id_for_db_path(c, path, tenant_id=tenant)
        if resolved:
            user = resolved
            break
    else:
        inferred = infer_private_folder_uid_from_db_path(path)
        if inferred:
            user = inferred
    return {
        "tenant_id": tenant,
        "user_id": user,
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


def extract_report_title_from_intent(text: str) -> str | None:
    """Extrae el título entre comillas de un mensaje tipo 'cambia el título … a \"…\"'."""
    raw = str(text or "").strip()
    if not raw:
        return None
    patterns = (
        r'(?:t[ií]tulo|title)\s*(?:del\s+reporte\s+)?(?:a|como|es|to|=|:)\s*["\']([^"\']+)["\']',
        r'(?:cambia|actualiza|renombra|pon(?:er)?|establece|set)\s+.*?(?:t[ií]tulo|title).*?["\']([^"\']+)["\']',
        r'["\']([^"\']{3,200})["\']',
    )
    for pat in patterns:
        m = re.search(pat, raw, re.IGNORECASE)
        if m:
            title = str(m.group(1) or "").strip()
            if title:
                return title[:200]
    return None


def admin_reports_title_only_intent(text: str) -> bool:
    """Actualizar metadata/título sin regenerar el HTML del lienzo."""
    low = (text or "").lower()
    if not any(
        k in low
        for k in (
            "[admin_reportes]",
            "reporte",
            "reportes",
            "lienzo",
            "custom_reports",
            "custom report",
        )
    ):
        return False
    if not any(k in low for k in ("titulo", "título", "title")):
        return False
    if not any(
        k in low
        for k in (
            "actualiza",
            "update",
            "cambia",
            "cambiar",
            "renombra",
            "renombrar",
            "pon ",
            "poner ",
            "establece",
            "set ",
        )
    ):
        return False
    if any(
        k in low
        for k in (
            "regenera",
            "recrea",
            "nuevo html",
            "nuevo dashboard",
            "desde cero",
            "grafico",
            "gráfico",
            "chart",
            "tortas",
            "torta",
            "pie ",
        )
    ):
        return False
    return True


def _patch_html_document_title(html: str, title: str) -> str:
    safe = (title or "Reporte").replace("<", "").replace(">", "")
    out = str(html or "")
    if re.search(r"<title[^>]*>.*?</title>", out, re.IGNORECASE | re.DOTALL):
        out = re.sub(
            r"<title[^>]*>.*?</title>",
            f"<title>{safe}</title>",
            out,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
    if re.search(r"<h1[^>]*>.*?</h1>", out, re.IGNORECASE | re.DOTALL):
        out = re.sub(
            r"<h1[^>]*>.*?</h1>",
            f"<h1>{safe}</h1>",
            out,
            count=1,
            flags=re.IGNORECASE | re.DOTALL,
        )
    return out


def admin_reports_publish_intent(text: str) -> bool:
    low = (text or "").lower()
    if "[admin_reportes]" in low:
        return True
    if not any(
        k in low
        for k in (
            "reportes",
            "reporte",
            "lienzo",
            "dashboard",
            "custom_reports",
            "custom report",
        )
    ):
        return False
    return any(
        k in low
        for k in (
            "html",
            "grafico",
            "gráfico",
            "chart",
            "tortas",
            "torta",
            "pie",
            "iframe",
            "publica",
            "publish",
            "valida",
            "validar",
            "titulo",
            "título",
            "title",
            "actualiza",
            "update",
            "republica",
        )
    )


def _custom_report_row(db: Any, report_id: str) -> dict[str, Any] | None:
    rid = (report_id or "").strip()
    if not rid:
        return None
    try:
        rows = db.execute(
            "SELECT report_id, title, html_content, version, updated_at "
            "FROM main.custom_reports WHERE report_id = ?",
            [rid],
        )
    except Exception:
        return None
    if not rows:
        return None
    row = rows[0]
    if isinstance(row, dict):
        return row
    if isinstance(row, (list, tuple)) and len(row) >= 3:
        return {
            "report_id": row[0],
            "title": row[1],
            "html_content": row[2],
            "version": row[3] if len(row) > 3 else None,
            "updated_at": row[4] if len(row) > 4 else None,
        }
    return None


@log_tool_execution_sync(name="update_custom_report_title")
def _update_custom_report_title_impl(db: Any, *, report_id: str, title: str) -> str:
    """UPSERT del título conservando html_content (StateDelta)."""
    rid = (report_id or "").strip()
    new_title = (title or "").strip()[:200]
    if not rid or not new_title:
        return json.dumps({"status": "error", "message": "report_id y title requeridos"}, ensure_ascii=False)
    row = _custom_report_row(db, rid)
    if not row:
        return json.dumps({"status": "error", "message": f"reporte no encontrado: {rid}"}, ensure_ascii=False)
    html = str(row.get("html_content") or "").strip()
    if not html:
        return json.dumps({"status": "error", "message": "html_content vacío en DB"}, ensure_ascii=False)
    html = _patch_html_document_title(html, new_title)
    return _publish_custom_report_impl(
        db,
        report_id=rid,
        html_content=html,
        title=new_title,
        created_by=str(row.get("created_by") or ""),
    )


def extract_html_document_from_text(text: str) -> str | None:
    raw = str(text or "")
    if not raw.strip():
        return None
    fence = re.search(r"```(?:html)?\s*\n([\s\S]*?</html>[\s\S]*?)\n```", raw, re.IGNORECASE)
    if fence:
        candidate = fence.group(1).strip()
        if "</html>" in candidate.lower():
            return candidate
    low = raw.lower()
    end = low.rfind("</html>")
    if end < 0:
        return None
    start = low.find("<!doctype")
    if start < 0:
        start = low.find("<html")
    if start < 0 or end <= start:
        return None
    return raw[start : end + 7].strip()


def _messages_since_last_human(messages: list | None) -> list:
    if not messages:
        return []
    try:
        from langchain_core.messages import HumanMessage
    except ImportError:
        return list(messages)
    last_human = -1
    for i, msg in enumerate(messages):
        if isinstance(msg, HumanMessage):
            last_human = i
    return list(messages[last_human + 1 :]) if last_human >= 0 else list(messages)


def _turn_already_published_custom_report(messages: list | None) -> bool:
    if not messages:
        return False
    try:
        from langchain_core.messages import ToolMessage
    except ImportError:
        return False
    for msg in reversed(_messages_since_last_human(messages)):
        if isinstance(msg, ToolMessage) and (getattr(msg, "name", "") or "") in (
            "publish_custom_report",
            "update_custom_report_title",
        ):
            body = str(getattr(msg, "content", "") or "")
            if '"status":"success"' in body.replace(" ", "") or '"status": "success"' in body:
                return True
    return False


def _html_from_tool_payload(payload: dict) -> str | None:
    if payload.get("exit_code") not in (0, None):
        return None
    for key in ("stdout", "output"):
        raw = str(payload.get(key) or "")
        if not raw.strip():
            continue
        html = extract_html_document_from_text(raw)
        if html:
            return html
        try:
            inner = json.loads(raw)
        except json.JSONDecodeError:
            inner = None
        if isinstance(inner, dict):
            for inner_key in ("html", "html_content", "document"):
                candidate = str(inner.get(inner_key) or "")
                html = extract_html_document_from_text(candidate)
                if html:
                    return html
    return None


def _parse_portfolio_slices_from_tool_text(text: str) -> list[dict[str, float | str]]:
    raw = str(text or "")
    slices: list[dict[str, float | str]] = []
    for m in re.finditer(
        r"\|\s*([A-Z][A-Z0-9.\-]{0,12})\s*\|[^|\n]*\|\s*\$?([0-9,]+(?:\.[0-9]+)?)",
        raw,
        re.IGNORECASE,
    ):
        sym, val = m.group(1).upper(), float(m.group(2).replace(",", ""))
        if val > 0:
            slices.append({"label": sym, "value": val})
    if not slices:
        for m in re.finditer(
            r"(?:^|\n)\s*[-*]?\s*\*{0,2}([A-Z][A-Z0-9.\-]{0,12})\*{0,2}\s*[:\|]\s*\$?([0-9,]+(?:\.[0-9]+)?)",
            raw,
            re.IGNORECASE,
        ):
            sym, val = m.group(1).upper(), float(m.group(2).replace(",", ""))
            if val > 0:
                slices.append({"label": sym, "value": val})
    dedup: dict[str, float] = {}
    for s in slices:
        lab = str(s["label"])
        dedup[lab] = dedup.get(lab, 0.0) + float(s["value"])
    return [{"label": k, "value": v} for k, v in dedup.items() if v > 0]


def _build_portfolio_pie_html(slices: list[dict[str, float | str]], *, title: str) -> str:
    data = slices or [{"label": "Sin posiciones", "value": 1.0}]
    labels = json.dumps([str(d["label"]) for d in data], ensure_ascii=False)
    values = json.dumps([float(d["value"]) for d in data])
    safe_title = (title or "Portfolio").replace("<", "").replace(">", "")
    return f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{safe_title}</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
  <style>
    body {{ font-family: system-ui, sans-serif; margin: 0; padding: 1.5rem; background: #0f172a; color: #e2e8f0; }}
    h1 {{ font-size: 1.25rem; margin: 0 0 1rem; }}
    .wrap {{ max-width: 720px; margin: 0 auto; }}
    canvas {{ background: #fff; border-radius: 12px; padding: 12px; }}
  </style>
</head>
<body>
  <div class="wrap">
    <h1>{safe_title}</h1>
    <canvas id="pie" height="360"></canvas>
  </div>
  <script>
    const ctx = document.getElementById('pie');
    new Chart(ctx, {{
      type: 'pie',
      data: {{
        labels: {labels},
        datasets: [{{ data: {values}, backgroundColor: ['#3b82f6','#22c55e','#f59e0b','#ef4444','#a855f7','#06b6d4','#84cc16','#f97316'] }}]
      }},
      options: {{ plugins: {{ legend: {{ position: 'bottom' }} }} }}
    }});
  </script>
</body>
</html>"""


def _portfolio_pie_html_from_messages(messages: list | None) -> str | None:
    if not messages:
        return None
    try:
        from langchain_core.messages import ToolMessage
    except ImportError:
        return None
    for msg in reversed(messages):
        if not isinstance(msg, ToolMessage):
            continue
        tool_name = (getattr(msg, "name", "") or "").strip().lower()
        if "portfolio" not in tool_name:
            continue
        body = str(getattr(msg, "content", "") or "")
        slices = _parse_portfolio_slices_from_tool_text(body)
        return _build_portfolio_pie_html(slices, title="Portfolio — distribución")
    return None


def _html_from_sandbox_tool_messages(messages: list | None) -> str | None:
    if not messages:
        return None
    try:
        from langchain_core.messages import ToolMessage
    except ImportError:
        return None
    for msg in reversed(messages):
        if not isinstance(msg, ToolMessage):
            continue
        tool_name = (getattr(msg, "name", "") or "").strip()
        if tool_name not in ("execute_sandbox_script", "run_sandbox"):
            continue
        body = str(getattr(msg, "content", "") or "")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            payload = None
        if isinstance(payload, dict):
            html = _html_from_tool_payload(payload)
            if html:
                return html
        html = extract_html_document_from_text(body)
        if html:
            return html
    return None


def auto_publish_html_from_admin_reply(
    reply: str,
    *,
    chat_id: str,
    db: Any,
    messages: list | None = None,
    title: str = "Reporte",
    incoming: str = "",
) -> tuple[str, bool]:
    """Publica HTML incrustado en la respuesta del modelo (fallback admin Reportes)."""
    cid = (chat_id or "").strip()
    if not cid or _turn_already_published_custom_report(messages):
        return reply, False
    html = extract_html_document_from_text(reply)
    if not html:
        html = _html_from_sandbox_tool_messages(messages)
    if (
        not html
        and admin_reports_publish_intent(incoming)
        and not admin_reports_title_only_intent(incoming)
    ):
        html = _portfolio_pie_html_from_messages(messages)
    if not html:
        return reply, False
    result_raw = _publish_custom_report_impl(
        db,
        report_id=cid,
        html_content=html,
        title=title,
    )
    try:
        payload = json.loads(result_raw)
    except json.JSONDecodeError:
        return reply, False
    if payload.get("status") != "success":
        return reply, False
    summary = (
        f"Reporte publicado en el lienzo (`report_id={cid}`). "
        "El HTML ya no se muestra en el chat; recarga automática vía SSE."
    )
    return summary, True


def register_custom_reports_skill(
    tools_list: List[Any],
    db: Any,
    spec: Any,
    *,
    force_publish: bool = False,
) -> None:
    skills = getattr(spec, "skills_list", None) or []
    existing = {getattr(t, "name", "") for t in tools_list}

    if ("publish_custom_report" in skills or force_publish) and "publish_custom_report" not in existing:
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
                    "ÚNICA herramienta de escritura para main.custom_reports (UPSERT vía StateDelta). "
                    "Reemplaza INSERT/UPDATE SQL. Republica html_content completo; actualiza title. "
                    "report_id debe ser el chat_id de la sesión admin."
                ),
            )
        )

    if force_publish or "update_custom_report_title" in skills:
        if "update_custom_report_title" not in existing:
            tools_list.append(
                StructuredTool.from_function(
                    lambda report_id, title: _update_custom_report_title_impl(
                        db,
                        report_id=report_id,
                        title=title,
                    ),
                    name="update_custom_report_title",
                    description=(
                        "Actualiza solo el título de un reporte en main.custom_reports (UPSERT StateDelta). "
                        "No requiere INSERT/UPDATE SQL ni reenviar HTML; lee html_content de la DB."
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
