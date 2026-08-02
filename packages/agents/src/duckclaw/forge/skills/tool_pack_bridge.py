"""Meta-tools de discovery / unlock de runtime tool packs."""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import StructuredTool

from duckclaw.workers.tool_pack_catalog import resolve_runtime_packs_config
from duckclaw.workers.tool_pack_policy import (
    LIST_PACKS_TOOL_NAME,
    UNLOCK_TOOL_NAME,
    catalog_public_summary,
)

LIST_TOOL_PACKS_DESCRIPTION = (
    "[Packs] Qué hace: lista packs de herramientas disponibles (carta corta vs catálogo). "
    "Cuándo: necesitas una capacidad que no ves en las tools actuales "
    "(informes Word, research web, escritura OUTPUT, visual). "
    "NO ejecuta la capacidad: solo informa. "
    "Siguiente: unlock_tool_pack(pack_id) y reintenta la acción."
)

UNLOCK_TOOL_PACK_DESCRIPTION = (
    "[Packs] Qué hace: desbloquea un pack para el resto del turno "
    "(p. ej. reports, research, docs_output, knowledge, visual). "
    "Cuándo: list_tool_packs mostró el pack y lo necesitas ahora. "
    "NO sustituye la tool de dominio (tras unlock llama search_project_knowledge, "
    "render_report_instance, etc.). "
    "Devuelve JSON {{ok, pack_id}}."
)


def register_tool_pack_meta_tools(tools_list: list[Any], *, spec: Any = None) -> None:
    """Registra meta-tools cerradas sobre el WorkerSpec del grafo."""

    def list_tool_packs() -> str:
        cfg = resolve_runtime_packs_config(spec)
        if not cfg.enabled:
            return json.dumps(
                {
                    "ok": True,
                    "enabled": False,
                    "message": (
                        "runtime_packs desactivado en tool_surface; "
                        "todas las tools van always-loaded."
                    ),
                    "packs": [],
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "ok": True,
                "enabled": True,
                "orphan_policy": cfg.catalog.orphan_policy,
                "max_bound_tools": cfg.catalog.max_bound_tools,
                "packs": catalog_public_summary(cfg),
                "hint": "Para activar un pack en este turno: unlock_tool_pack(pack_id).",
            },
            ensure_ascii=False,
        )

    def unlock_tool_pack(pack_id: str = "") -> str:
        cleaned = (pack_id or "").strip()
        cfg = resolve_runtime_packs_config(spec)
        if not cleaned:
            return json.dumps(
                {
                    "ok": False,
                    "error": "pack_id vacío",
                    "hint": "Usa list_tool_packs() y pasa un pack_id válido.",
                },
                ensure_ascii=False,
            )
        if not cfg.enabled:
            return json.dumps(
                {
                    "ok": True,
                    "pack_id": cleaned,
                    "unlocked": cleaned,
                    "note": "runtime_packs desactivado; unlock no cambia el surface.",
                },
                ensure_ascii=False,
            )
        known = {p.pack_id for p in cfg.catalog.packs} - set(cfg.disabled_packs)
        if cleaned not in known:
            return json.dumps(
                {
                    "ok": False,
                    "error": f"pack_id desconocido o deshabilitado: {cleaned}",
                    "known_packs": sorted(known),
                    "hint": "list_tool_packs() para ver ids.",
                },
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "ok": True,
                "pack_id": cleaned,
                "unlocked": cleaned,
                "unlocked_packs": [cleaned],
                "hint": (
                    f"Pack «{cleaned}» activo en el resto del turno; "
                    "llama la tool de dominio."
                ),
            },
            ensure_ascii=False,
        )

    tools_list.append(
        StructuredTool.from_function(
            list_tool_packs,
            name=LIST_PACKS_TOOL_NAME,
            description=LIST_TOOL_PACKS_DESCRIPTION,
        )
    )
    tools_list.append(
        StructuredTool.from_function(
            unlock_tool_pack,
            name=UNLOCK_TOOL_NAME,
            description=UNLOCK_TOOL_PACK_DESCRIPTION,
        )
    )
