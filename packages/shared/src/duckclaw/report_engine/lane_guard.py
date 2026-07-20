"""Carril Report Engine — transversal: plantilla registrada ⇒ Word vía motor, no pandoc."""

from __future__ import annotations

from typing import Any

_REPORT_ENGINE_FLOW = (
    "register_report_template → create_report_instance → "
    "patch_report_section (cada {{ campo }}) → render_report_instance"
)


def actor_has_report_templates(
    db: Any,
    *,
    tenant_id: str,
    actor_email: str,
) -> bool:
    """True si el actor ve ≥1 plantilla Report Engine (propia o visibility=tenant)."""
    if db is None:
        return False
    from duckclaw.report_engine.admin_report_read import list_report_templates

    rows = list_report_templates(
        db,
        tenant_id=(tenant_id or "default").strip() or "default",
        actor_email=(actor_email or "system").strip() or "system",
        limit=1,
    )
    return len(rows) > 0


def build_report_engine_required_error(*, blocked_tool: str, relative_path: str = "") -> str:
    target = f" «{relative_path}»" if (relative_path or "").strip() else ""
    return (
        f"{blocked_tool} bloqueado{target}: este usuario tiene plantilla(s) Word "
        f"registradas. El entregable .docx debe salir del Report Engine "
        f"({_REPORT_ENGINE_FLOW}). "
        "No uses convertidores genéricos ni escribas un Word paralelo. "
        "Si necesitas una conversión ad hoc sin plantilla, pasa allow_ad_hoc_docx=true. "
        "PDF: export_docx_to_pdf sobre el .docx del Report Engine."
    )


def assert_docx_uses_report_engine_when_templates_exist(
    *,
    blocked_tool: str,
    relative_path: str = "",
    output_format: str = "",
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "system",
    allow_ad_hoc_docx: bool = False,
    fail_closed_without_db: bool = False,
) -> None:
    """
    Fail-loud si se intenta producir .docx fuera del Report Engine
    cuando el actor ya tiene plantillas registradas.

    Transversal: no mira el nombre del archivo ni el nicho.
    Criterio: ¿hay plantilla visible? → Word = motor.
    Escape: allow_ad_hoc_docx=true.
    fail_closed_without_db: si no hay DB, bloquear (tools de Word paralelo).
    """
    if allow_ad_hoc_docx:
        return

    fmt = (output_format or "").strip().lower()
    rel = (relative_path or "").strip()
    wants_docx = fmt == "docx" or rel.lower().endswith(".docx")
    if not wants_docx:
        return

    if db is None:
        if fail_closed_without_db:
            raise ValueError(
                f"{blocked_tool} bloqueado: no se pudo verificar plantillas Report Engine. "
                "Usa render_report_instance o reintenta con hub disponible. "
                "Escape explícito: allow_ad_hoc_docx=true."
            )
        return

    try:
        has_templates = actor_has_report_templates(
            db, tenant_id=tenant_id, actor_email=actor_email
        )
    except Exception as exc:
        if fail_closed_without_db:
            raise ValueError(
                f"{blocked_tool} bloqueado: error verificando plantillas ({exc}). "
                "Usa Report Engine o allow_ad_hoc_docx=true."
            ) from exc
        return

    if not has_templates:
        return

    raise ValueError(
        build_report_engine_required_error(blocked_tool=blocked_tool, relative_path=rel)
    )


# Alias legacy (tests / imports antiguos)
assert_corporate_word_uses_report_engine = assert_docx_uses_report_engine_when_templates_exist
