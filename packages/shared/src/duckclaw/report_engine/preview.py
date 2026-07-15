"""HTML preview from report instance state."""

from __future__ import annotations

import html
from typing import Any


def render_preview_html(
    *,
    title: str,
    period_key: str,
    state: dict[str, Any],
    section_schema: list[dict[str, Any]] | None = None,
) -> str:
    sections = state.get("sections") if isinstance(state.get("sections"), dict) else {}
    order = [
        str(s.get("id") or "").strip()
        for s in (section_schema or [])
        if isinstance(s, dict)
    ] or list(sections.keys())

    parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'>",
        "<style>body{font-family:system-ui,sans-serif;max-width:820px;margin:2rem auto;padding:0 1rem;}",
        "h1{font-size:1.5rem} h2{font-size:1.1rem;margin-top:1.5rem;border-bottom:1px solid #ddd;}",
        ".meta{color:#666;font-size:.9rem} .empty{color:#999;font-style:italic} ",
        ".badge{display:inline-block;font-size:.7rem;padding:.1rem .4rem;border-radius:.25rem;margin-left:.5rem}",
        ".partial{background:#fef3c7}.complete{background:#d1fae5}.empty-b{background:#f3f4f6}</style></head><body>",
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
        parts.append(f"<h2>{label}<span class='badge {badge_cls}'>{html.escape(st)}</span></h2>")
        if content:
            parts.append(f"<div>{html.escape(content).replace(chr(10), '<br>')}</div>")
        else:
            parts.append("<p class='empty'>Sin contenido</p>")

    parts.append("</body></html>")
    return "".join(parts)
