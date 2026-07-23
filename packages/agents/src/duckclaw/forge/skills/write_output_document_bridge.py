"""Tool bridge: escribir markdown/texto en raíces OUTPUT (Obsidian vault)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.document_toolbox.registry import assert_author_text_path
from duckclaw.forge.rag.knowledge_core import safe_relative_path, sha256_text
from duckclaw.forge.rag.knowledge_paths import (
    knowledge_output_roots,
    normalize_output_relative_path,
    path_under_any_root,
    resolve_knowledge_output_path,
)


def _targets_for_write(relative_path: str, output_root: str = "") -> list[Path]:
    """Una raíz explícita, o todas las DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS (dual-write)."""
    roots = knowledge_output_roots()
    if not roots:
        raise ValueError("DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS no configurado para escritura")

    rel = normalize_output_relative_path(relative_path)
    assert_author_text_path(rel)

    if (output_root or "").strip():
        return [resolve_knowledge_output_path(relative_path=rel, output_root=output_root)]

    targets: list[Path] = []
    for root in roots:
        base = root.expanduser().resolve()
        safe_relative_path(base, base / rel)
        target = (base / rel).resolve()
        if not path_under_any_root(target.parent if target.suffix else target, roots):
            raise ValueError("ruta de salida fuera de raíces permitidas")
        targets.append(target)
    return targets


def write_output_document(relative_path: str, content: str, output_root: str = "") -> str:
    """Escribe un documento markdown/texto bajo DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS.

    Sin output_root y con varias raíces: escribe en TODAS (espejo local + Drive),
    igual que el Report Engine. No inventes output_root.
    """
    text = (content or "").strip()
    if not text:
        return json.dumps({"error": "El contenido está vacío."}, ensure_ascii=False)

    try:
        targets = _targets_for_write(relative_path, output_root)
        data = text.encode("utf-8")
        written: list[str] = []
        for target in targets:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            written.append(str(target))

        primary = targets[0]
        rel = normalize_output_relative_path(relative_path)
        payload: dict[str, Any] = {
            "relative_path": rel,
            "path": str(primary),
            "paths": written,
            "byte_size": len(data),
            "checksum": sha256_text(text),
        }
        try:
            from duckclaw.forge.rag.knowledge_auto_sync import auto_sync_enabled, sync_file_after_write
            from duckclaw.forge.skills.knowledge_tool_context import (
                get_knowledge_tool_project_id,
                get_knowledge_tool_tenant_id,
            )

            if auto_sync_enabled():
                rag_sync = sync_file_after_write(
                    file_path=primary,
                    tenant_id=get_knowledge_tool_tenant_id(),
                    project_id=get_knowledge_tool_project_id(),
                )
            else:
                rag_sync = {"synced": False, "reason": "auto_sync_disabled"}
            payload["rag_sync"] = rag_sync
        except Exception as exc:
            payload["rag_sync"] = {"synced": False, "reason": str(exc)}
        try:
            from duckclaw.productivity_artifacts import register_vault_artifact_from_path

            indexed = register_vault_artifact_from_path(
                primary,
                source_kind="write_output",
                source_ref=rel,
                title=primary.name,
            )
            if indexed:
                payload["productivity_artifact_id"] = indexed.get("artifact_id")
        except Exception as exc:
            payload["productivity_index"] = {"ok": False, "reason": str(exc)}
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def delete_output_document(relative_path: str) -> str:
    """Elimina un archivo bajo DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS (todas las raíces).

    Acepta .md/.txt y también .docx/.pdf generados por Report Engine.
    """
    try:
        rel = (relative_path or "").replace("\\", "/").strip().lstrip("/")
        if not rel or ".." in rel.split("/"):
            raise ValueError("relative_path inválido")
        roots = knowledge_output_roots()
        if not roots:
            return json.dumps(
                {"error": "DUCKCLAW_KNOWLEDGE_OUTPUT_ROOTS no configurado"},
                ensure_ascii=False,
            )
        deleted: list[str] = []
        missing: list[str] = []
        for root in roots:
            root_r = root.expanduser().resolve()
            target = (root_r / rel).resolve()
            if target != root_r and root_r not in target.parents:
                raise ValueError(f"Ruta fuera de output: {rel}")
            if target.is_file():
                target.unlink()
                deleted.append(str(target))
            else:
                missing.append(str(target))
        return json.dumps(
            {
                "relative_path": rel,
                "deleted": deleted,
                "missing": missing,
                "ok": bool(deleted),
            },
            ensure_ascii=False,
        )
    except Exception as exc:
        return json.dumps({"error": str(exc)}, ensure_ascii=False)


def register_write_output_document_tool(tools_list: list[Any]) -> None:
    tools_list.append(
        StructuredTool.from_function(
            write_output_document,
            name="write_output_document",
            description=(
                "Escribe un archivo de texto UTF-8 en output/ "
                "(.md, .txt, .json, .csv, .yaml, .py, .html, …). "
                "Con varias raíces (local + Drive) escribe en TODAS automáticamente; "
                "NO pases output_root salvo que el usuario lo pida. "
                "Prohibido .docx/.pdf/.xlsx. "
                "Word por plantilla: Report Engine (register → create → patch → render). "
                "Borrar: delete_output_document."
            ),
        )
    )
    tools_list.append(
        StructuredTool.from_function(
            delete_output_document,
            name="delete_output_document",
            description=(
                "Elimina un archivo en output/ (todas las raíces: local + Drive). "
                "Úsalo para borrar .docx/.pdf/.md erróneos. "
                "Para archivar un informe del Report Engine preferí delete_report_instance "
                "(también puede borrar el .docx renderizado)."
            ),
        )
    )
