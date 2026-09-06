"""Admin custom reports: servir HTML del vault + SSE reload + LLM usage summary."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from core.report_updates import iter_report_reload_events
from core.sse_stream import SSE_HEADERS
from routers.admin import _require_admin_key

_log = logging.getLogger(__name__)

router = APIRouter(tags=["admin-reports"])

PLACEHOLDER_MARKER = "Ningún reporte generado aún"

_PLACEHOLDER_HTML = f"""<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><title>Reporte</title></head>
<body style="font-family:system-ui;padding:2rem;color:#334155">
<h3>{PLACEHOLDER_MARKER}</h3>
<p>Abre el asistente (arriba a la derecha) y pide un dashboard con <strong>ui_designer</strong> o el worker de reporting que tengas configurado, o sube un archivo <strong>.html</strong> desde esta pantalla.</p>
</body></html>"""

_CSP = (
    "default-src 'self' https: data:; "
    "script-src 'self' https: cdn.jsdelivr.net cdnjs.cloudflare.com unpkg.com cdn.tailwindcss.com 'unsafe-inline'; "
    "style-src 'self' https: 'unsafe-inline'"
)


def _open_vault(vault_path: str, *, read_only: bool = True) -> Any:
    from routers.admin import _open_playground_vault_db

    return _open_playground_vault_db(vault_path, read_only=read_only)


def _html_from_custom_report_rows(rows: Any) -> str | None:
    if not rows:
        return None
    row = rows[0]
    if isinstance(row, dict):
        html = row.get("html_content")
    elif isinstance(row, (list, tuple)) and row:
        html = row[0]
    else:
        return None
    text = str(html or "").strip()
    return text or None


@router.get("/reports/llm-usage/summary", dependencies=[Depends(_require_admin_key)])
async def llm_usage_summary(days: int = Query(7, ge=1, le=90)):
    from routers.admin import _overview_usage_metrics
    from duckclaw import DuckClaw
    from duckclaw.gateway_db import get_gateway_db_path, resolve_env_duckdb_path

    path = resolve_env_duckdb_path(get_gateway_db_path())
    db = DuckClaw(path, read_only=True)
    try:
        return _overview_usage_metrics(db, days=days, group_by="worker")
    finally:
        db.close()


@router.get("/reports/{report_id}", response_class=HTMLResponse, dependencies=[Depends(_require_admin_key)])
async def get_rendered_report(
    report_id: str,
    vault: str = Query(..., description="Ruta absoluta del vault .duckdb"),
):
    rid = (report_id or "").strip()
    vp = (vault or "").strip()
    if not rid or not vp:
        raise HTTPException(status_code=400, detail="report_id y vault requeridos")

    try:
        db = _open_vault(vp, read_only=True)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="vault no encontrado") from None
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        try:
            rows = db.execute(
                "SELECT html_content FROM main.custom_reports WHERE report_id = ?",
                [rid],
            )
        except Exception as exc:
            _log.info(
                "get_rendered_report placeholder report_id=%s vault=%s reason=query_error err=%s",
                rid,
                vp,
                exc,
            )
            return HTMLResponse(content=_PLACEHOLDER_HTML, headers={"Content-Security-Policy": _CSP})
    finally:
        try:
            db.close()
        except Exception:
            pass

    html = _html_from_custom_report_rows(rows)
    if not html:
        _log.info(
            "get_rendered_report placeholder report_id=%s vault=%s reason=empty_row",
            rid,
            vp,
        )
        return HTMLResponse(content=_PLACEHOLDER_HTML, headers={"Content-Security-Policy": _CSP})
    return HTMLResponse(content=html, headers={"Content-Security-Policy": _CSP})


def _title_from_upload_filename(filename: str | None) -> str:
    base = (filename or "Reporte").rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    stem = re.sub(r"\.(html?|htm)$", "", base, flags=re.IGNORECASE).strip()
    return (stem or "Reporte")[:200]


class UploadCustomReportResponse(BaseModel):
    status: str
    report_id: str
    message: str = ""


@router.post(
    "/reports/{report_id}/upload",
    response_model=UploadCustomReportResponse,
    dependencies=[Depends(_require_admin_key)],
)
async def upload_custom_report(
    report_id: str,
    vault: str = Form(..., description="Ruta absoluta del vault .duckdb"),
    title: str = Form(""),
    file: UploadFile = File(...),
):
    """Publica HTML subido por admin vía CUSTOM_REPORT_UPSERT (mismo camino que publish_custom_report)."""
    rid = (report_id or "").strip()
    vp = (vault or "").strip()
    if not rid or not vp:
        raise HTTPException(status_code=400, detail="report_id y vault requeridos")

    fname = (file.filename or "").strip().lower()
    if not fname.endswith((".html", ".htm")):
        raise HTTPException(status_code=400, detail="Solo archivos .html o .htm")

    raw = await file.read()
    if len(raw) > 512 * 1024:
        raise HTTPException(status_code=400, detail="HTML excede 512KB")

    try:
        html_content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise HTTPException(status_code=400, detail="El archivo debe estar en UTF-8") from exc

    try:
        _open_vault(vp, read_only=True)
    except FileNotFoundError:
        raise HTTPException(status_code=404, detail="vault no encontrado") from None
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    from duckclaw.forge.skills.custom_reports_bridge import _publish_custom_report_impl

    db_stub = type("_VaultRef", (), {"_path": vp})()
    resolved_title = (title or "").strip() or _title_from_upload_filename(file.filename)
    result_raw = _publish_custom_report_impl(
        db_stub,
        report_id=rid,
        html_content=html_content,
        title=resolved_title,
        created_by="admin-ui-upload",
    )
    try:
        payload = json.loads(result_raw)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=500, detail="Respuesta inválida al encolar reporte") from exc

    if payload.get("status") != "success":
        raise HTTPException(status_code=400, detail=str(payload.get("message") or "No se pudo publicar"))

    return UploadCustomReportResponse(
        status="success",
        report_id=rid,
        message=str(payload.get("message") or "Reporte encolado para publicación"),
    )


@router.get("/reports/{report_id}/stream", dependencies=[Depends(_require_admin_key)])
async def report_stream(request: Request, report_id: str):
    rid = (report_id or "").strip()
    if not rid:
        raise HTTPException(status_code=400, detail="report_id requerido")

    redis_client = getattr(request.app.state, "redis", None)

    async def event_generator():
        stop = asyncio.Event()
        queue: asyncio.Queue[str | None] = asyncio.Queue()

        async def listener() -> None:
            try:
                async for evt in iter_report_reload_events(redis_client, rid, stop=stop):
                    await queue.put(evt)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                _log.debug("report stream listener ended: %s", exc)
            finally:
                await queue.put(None)

        task = asyncio.create_task(listener())
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    evt = await asyncio.wait_for(queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
                    continue
                if evt is None:
                    break
                yield f"data: {evt}\n\n"
        finally:
            stop.set()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    return StreamingResponse(event_generator(), media_type="text/event-stream", headers=SSE_HEADERS)
