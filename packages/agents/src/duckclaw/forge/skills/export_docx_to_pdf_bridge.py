"""Tool: exportar .docx (Report Engine / OUTPUT) → PDF vía LibreOffice."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.document_toolbox.export_pdf import export_docx_to_pdf_file, libreoffice_available
from duckclaw.forge.rag.knowledge_paths import (
    knowledge_allowed_roots,
    knowledge_output_roots,
    path_under_any_root,
    resolve_knowledge_output_path,
    resolve_readable_document_path,
)


def _resolve_docx_source(
    *,
    docx_path: str = "",
    relative_path: str = "",
    instance_id: str = "",
) -> Path:
    iid = (instance_id or "").strip()
    if iid:
        from duckclaw.forge.skills.report_engine_bridge import _open_hub_db, _session_scope
        from duckclaw.report_engine.admin_report_read import (
            actor_can_access_instance,
            get_report_instance,
        )

        tenant_id, actor_email, _ = _session_scope()
        db = _open_hub_db()
        try:
            instance = get_report_instance(db, instance_id=iid, tenant_id=tenant_id)
            if not instance:
                raise ValueError(f"Instancia no encontrada: {iid}")
            if not actor_can_access_instance(db, instance=instance, actor_email=actor_email):
                raise ValueError("Acceso denegado a la instancia")
            uri = str(instance.get("rendered_docx_uri") or "").strip()
            if not uri:
                raise ValueError(
                    "La instancia aún no tiene Word renderizado. "
                    "Llama render_report_instance antes de export_docx_to_pdf."
                )
            return Path(uri).expanduser().resolve()
        finally:
            try:
                db.close()
            except Exception:
                pass

    rel = (relative_path or "").strip()
    if rel:
        if rel.lower().endswith(".docx"):
            return resolve_readable_document_path(relative_path=rel)
        raise ValueError("relative_path debe apuntar a un .docx")

    raw = (docx_path or "").strip()
    if raw:
        candidate = Path(raw).expanduser().resolve()
        roots = knowledge_output_roots() + knowledge_allowed_roots()
        if not roots or not path_under_any_root(candidate, roots):
            raise ValueError(
                "docx_path debe estar bajo DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS "
                "o DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS"
            )
        return candidate

    raise ValueError(
        "Indica instance_id (tras render), relative_path bajo OUTPUT, o docx_path absoluto permitido."
    )


def export_docx_to_pdf(
    instance_id: str = "",
    relative_path: str = "",
    docx_path: str = "",
) -> str:
    """Exporta un Word (.docx) a PDF en el mismo directorio (LibreOffice headless)."""
    try:
        source = _resolve_docx_source(
            docx_path=docx_path,
            relative_path=relative_path,
            instance_id=instance_id,
        )
        roots = knowledge_output_roots()
        # Prefer writing PDF under OUTPUT even if source was only under ALLOWED.
        if roots and path_under_any_root(source, roots):
            target = source.with_suffix(".pdf")
        elif roots:
            target = resolve_knowledge_output_path(
                relative_path=source.with_suffix(".pdf").name
            )
        else:
            target = source.with_suffix(".pdf")

        payload = export_docx_to_pdf_file(source=source, target=target)
        try:
            from duckclaw.productivity_artifacts import register_vault_artifact_from_path
            from duckclaw.forge.skills.knowledge_tool_context import (
                get_knowledge_tool_project_id,
                get_knowledge_tool_tenant_id,
            )

            indexed = register_vault_artifact_from_path(
                Path(str(payload["path"])),
                tenant_id=get_knowledge_tool_tenant_id(),
                source_kind="docx_to_pdf",
                source_ref=str(payload.get("source_path") or source),
                title=Path(str(payload["path"])).name,
            )
            if indexed:
                payload["productivity_artifact_id"] = indexed.get("artifact_id")
                payload["project_id"] = get_knowledge_tool_project_id()
        except Exception as exc:
            payload["productivity_index"] = {"ok": False, "reason": str(exc)}
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        out: dict[str, Any] = {"error": str(exc)}
        if not libreoffice_available():
            out["hint"] = (
                "Instala LibreOffice en el host del gateway "
                "(brew install --cask libreoffice)."
            )
        return json.dumps(out, ensure_ascii=False)


def register_export_docx_to_pdf_tool(tools_list: list[Any]) -> None:
    tools_list.append(
        StructuredTool.from_function(
            export_docx_to_pdf,
            name="export_docx_to_pdf",
            description=(
                "Convierte un .docx ya generado (Report Engine / OUTPUT) a PDF con LibreOffice. "
                "Preferir instance_id tras render_report_instance; "
                "alternativas: relative_path o docx_path bajo OUTPUT/ALLOWED. "
                "No convierte markdown: el Word serio sale del Report Engine."
            ),
        )
    )
