"""Report Engine — template + instance + section state (transversal)."""

from duckclaw.report_engine.analyzer import analyze_docx_template
from duckclaw.report_engine.preview import render_preview_html
from duckclaw.report_engine.render import render_instance_docx_from_uri
from duckclaw.report_engine.state import (
    build_render_context,
    init_state_from_schema,
    patch_section,
    summarize_status,
)

__all__ = [
    "analyze_docx_template",
    "build_render_context",
    "init_state_from_schema",
    "patch_section",
    "render_instance_docx_from_uri",
    "render_preview_html",
    "summarize_status",
]
