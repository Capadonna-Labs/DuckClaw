"""Tools de disco bajo ALLOWED_ROOTS (SOTA: parity UI ↔ agente sin indexar)."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.forge.skills.knowledge_tool_copy import (
    LIST_DISK_FOLDER_DESCRIPTION,
    LIST_DISK_ROOTS_DESCRIPTION,
    READ_DISK_TEXT_DESCRIPTION,
)

_TEXT_SUFFIXES = {
    ".md",
    ".markdown",
    ".txt",
    ".py",
    ".pyi",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".css",
    ".scss",
    ".html",
    ".htm",
    ".xml",
    ".csv",
    ".sql",
    ".sh",
    ".rs",
    ".go",
    ".java",
    ".kt",
    ".swift",
    ".rb",
    ".php",
    ".c",
    ".h",
    ".cpp",
    ".hpp",
    ".env.example",
}
_READ_MAX_CHARS = 80_000


def _tool_error(message: str, *, hint: str = "") -> str:
    payload: dict[str, Any] = {"ok": False, "error": message, "retry": False}
    if hint:
        payload["hint"] = hint
    return json.dumps(payload, ensure_ascii=False)


def list_disk_roots() -> str:
    """Lista raíces de disco permitidas (no RAG)."""
    from duckclaw.forge.rag.knowledge_paths import knowledge_allowed_roots

    roots = knowledge_allowed_roots()
    if not roots:
        return _tool_error(
            "No hay DUCKCLAW_KNOWLEDGE_ALLOWED_ROOTS configurado.",
            hint="Configura .env y reinicia el Gateway.",
        )
    rows = []
    for root in roots:
        try:
            exists = root.exists()
        except OSError:
            exists = False
        rows.append(
            {
                "label": root.name or str(root),
                "path": str(root),
                "exists": exists,
                "kind": "root",
            }
        )
    return json.dumps({"ok": True, "roots": rows, "lane": "disk"}, ensure_ascii=False)


def list_disk_folder(path: str = "", include_files: bool = False) -> str:
    """Explora una carpeta permitida en disco.

    Args:
        path: Ruta absoluta bajo ALLOWED_ROOTS, o vacío para listar solo las raíces.
        include_files: Si true, incluye archivos (además de carpetas).
    """
    from duckclaw.forge.rag.knowledge_paths import browse_knowledge_directories

    try:
        suffixes = ["*"] if include_files else None
        payload = browse_knowledge_directories(
            path or "",
            include_suffixes=suffixes,
            root_set="allowed",
        )
        if not include_files:
            payload["entries"] = [
                e for e in payload.get("entries") or [] if e.get("kind") != "file"
            ]
        payload["ok"] = True
        payload["lane"] = "disk"
        return json.dumps(payload, ensure_ascii=False)
    except ValueError as exc:
        return _tool_error(
            str(exc),
            hint="Usa list_disk_roots() o un path absoluto dentro de ALLOWED_ROOTS.",
        )
    except Exception as exc:
        return _tool_error(str(exc))


def read_disk_text(path: str = "", root_hint: str = "") -> str:
    """Lee un archivo de texto bajo raíces permitidas.

    Args:
        path: Ruta absoluta del archivo, o relative_path bajo una raíz permitida.
        root_hint: Raíz absoluta opcional cuando path es relativo.
    """
    from duckclaw.forge.rag.knowledge_paths import resolve_readable_document_path

    cleaned = (path or "").strip()
    if not cleaned:
        return _tool_error(
            "Indica path del archivo.",
            hint="Ejemplo: list_disk_folder → elige un .py/.md → read_disk_text(path=...).",
        )
    try:
        target = resolve_readable_document_path(
            relative_path=cleaned,
            root_hint=root_hint or "",
        )
    except ValueError as exc:
        return _tool_error(str(exc), hint="Path debe estar bajo ALLOWED_ROOTS u OUTPUT.")
    except Exception as exc:
        return _tool_error(str(exc))

    suffix = target.suffix.lower()
    name = target.name.lower()
    ok_suffix = suffix in _TEXT_SUFFIXES or name.endswith(".env.example")
    if not ok_suffix:
        return _tool_error(
            f"Tipo no soportado para read_disk_text: {suffix or name}",
            hint="Para PDF/Word/PPT usa extract_document_text.",
        )
    try:
        raw = target.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return _tool_error(f"No se pudo leer: {exc}")
    truncated = len(raw) > _READ_MAX_CHARS
    content = raw if not truncated else raw[:_READ_MAX_CHARS] + "\n…[truncated]"
    return json.dumps(
        {
            "ok": True,
            "lane": "disk",
            "path": str(target),
            "suffix": suffix,
            "char_count": len(raw),
            "truncated": truncated,
            "content": content,
        },
        ensure_ascii=False,
    )


def register_disk_knowledge_tools(tools_list: list[Any]) -> None:
    tools_list.append(
        StructuredTool.from_function(
            list_disk_roots,
            name="list_disk_roots",
            description=LIST_DISK_ROOTS_DESCRIPTION,
        )
    )
    tools_list.append(
        StructuredTool.from_function(
            list_disk_folder,
            name="list_disk_folder",
            description=LIST_DISK_FOLDER_DESCRIPTION,
        )
    )
    tools_list.append(
        StructuredTool.from_function(
            read_disk_text,
            name="read_disk_text",
            description=READ_DISK_TEXT_DESCRIPTION,
        )
    )
