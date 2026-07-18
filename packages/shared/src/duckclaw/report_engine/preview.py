"""HTML preview from report instance state."""

from __future__ import annotations

import base64
import html
import mimetypes
from pathlib import Path
from typing import Any

_PREVIEW_IMAGE_MAX_BYTES = 2_500_000


def _section_kind(entry: dict[str, Any], schema_row: dict[str, Any] | None) -> str:
    raw = entry.get("kind")
    if raw is None and isinstance(schema_row, dict):
        raw = schema_row.get("kind")
    return "image" if str(raw or "").strip().lower() == "image" else "text"


def _image_preview_html(path_raw: str) -> str:
    """Data-URI thumbnail for admin preview (file:// is blocked in browser)."""
    path = Path(path_raw).expanduser()
    try:
        resolved = path.resolve()
    except OSError:
        return (
            f"<p class='empty'>Imagen no accesible: "
            f"<code>{html.escape(path_raw)}</code></p>"
        )
    if not resolved.is_file():
        return (
            f"<p class='empty'>Imagen no encontrada: "
            f"<code>{html.escape(str(resolved))}</code></p>"
        )
    try:
        size = resolved.stat().st_size
    except OSError:
        size = 0
    if size <= 0 or size > _PREVIEW_IMAGE_MAX_BYTES:
        return (
            f"<p class='meta'>Imagen lista para Word "
            f"(<code>{html.escape(resolved.name)}</code>, {size} bytes). "
            f"Abre el .docx descargado para verla.</p>"
        )
    mime, _ = mimetypes.guess_type(resolved.name)
    mime = mime or "image/png"
    if not mime.startswith("image/"):
        mime = "image/png"
    try:
        b64 = base64.b64encode(resolved.read_bytes()).decode("ascii")
    except OSError:
        return (
            f"<p class='empty'>No se pudo leer: "
            f"<code>{html.escape(str(resolved))}</code></p>"
        )
    return (
        f"<figure class='img-slot'>"
        f"<img src='data:{mime};base64,{b64}' alt='{html.escape(resolved.name)}' />"
        f"<figcaption class='meta'>{html.escape(resolved.name)}</figcaption>"
        f"</figure>"
    )


def render_preview_html(
    *,
    title: str,
    period_key: str,
    state: dict[str, Any],
    section_schema: list[dict[str, Any]] | None = None,
) -> str:
    sections = state.get("sections") if isinstance(state.get("sections"), dict) else {}
    schema_by_id: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for raw in section_schema or []:
        if not isinstance(raw, dict):
            continue
        sid = str(raw.get("id") or "").strip()
        if not sid:
            continue
        order.append(sid)
        schema_by_id[sid] = raw
    if not order:
        order = list(sections.keys())

    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<style>body{font-family:system-ui,sans-serif;max-width:820px;margin:2rem auto;padding:0 1rem;}",
        "h1{font-size:1.5rem} h2{font-size:1.1rem;margin-top:1.5rem;border-bottom:1px solid #ddd;}",
        ".meta{color:#666;font-size:.9rem} .empty{color:#999;font-style:italic} ",
        ".badge{display:inline-block;font-size:.7rem;padding:.1rem .4rem;border-radius:.25rem;margin-left:.5rem}",
        ".partial{background:#fef3c7}.complete{background:#d1fae5}.empty-b{background:#f3f4f6}",
        ".img-slot img{max-width:100%;height:auto;border:1px solid #e5e7eb;border-radius:8px}",
        ".img-slot figcaption{margin-top:.35rem}</style></head><body>",
        f"<h1>{html.escape(title or 'Informe')}</h1>",
    ]
    if period_key:
        parts.append(f"<p class='meta'>{html.escape(period_key)}</p>")

    for sid in order:
        entry = sections.get(sid) if isinstance(sections.get(sid), dict) else {}
        label = html.escape(str(entry.get("label") or sid))
        st = str(entry.get("status") or "empty")
        badge_cls = {"complete": "complete", "partial": "partial"}.get(st, "empty-b")
        content = str(entry.get("content") or "").strip()
        kind = _section_kind(entry if isinstance(entry, dict) else {}, schema_by_id.get(sid))
        parts.append(f"<h2>{label}<span class='badge {badge_cls}'>{html.escape(st)}</span></h2>")
        if not content:
            parts.append("<p class='empty'>Sin contenido</p>")
            continue
        if kind == "image":
            parts.append(_image_preview_html(content))
        else:
            parts.append(f"<div>{html.escape(content).replace(chr(10), '<br>')}</div>")

    parts.append("</body></html>")
    return "".join(parts)
