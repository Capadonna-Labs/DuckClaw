"""ADB helper tools alongside MCP Android connector (expand notification shade)."""

from __future__ import annotations

import json
import logging
from typing import Any

_log = logging.getLogger(__name__)


def register_android_adb_helper_tools(tools_list: list[Any]) -> int:
    """Register expand/collapse statusbar tools when worker has Android MCP grant."""
    try:
        from langchain_core.tools import StructuredTool
        from pydantic import BaseModel
    except ImportError:
        return 0

    class _Empty(BaseModel):
        pass

    def _expand() -> str:
        from duckclaw.mcp_android_adb import android_expand_notifications

        return json.dumps(android_expand_notifications(), ensure_ascii=False)

    def _collapse() -> str:
        from duckclaw.mcp_android_adb import android_collapse_statusbar

        return json.dumps(android_collapse_statusbar(), ensure_ascii=False)

    def _review_and_dismiss(max_dismiss: int = 12) -> str:
        from duckclaw.mcp_android_adb import android_review_and_dismiss_notifications

        return json.dumps(
            android_review_and_dismiss_notifications(max_dismiss=max_dismiss),
            ensure_ascii=False,
        )

    names = {str(getattr(t, "name", "") or "") for t in tools_list}
    added = 0
    if "android_expand_notifications" not in names:
        tools_list.append(
            StructuredTool.from_function(
                _expand,
                name="android_expand_notifications",
                description=(
                    "Abre el panel de notificaciones Android vía ADB "
                    "(cmd statusbar expand-notifications). "
                    "Usar ANTES de get_ui_dump cuando necesites leer/descartar notificaciones; "
                    "preferir esto sobre swipe vertical para abrir el panel."
                ),
                args_schema=_Empty,
                infer_schema=False,
            )
        )
        added += 1
    if "android_collapse_notifications" not in names:
        tools_list.append(
            StructuredTool.from_function(
                _collapse,
                name="android_collapse_notifications",
                description="Cierra el panel de notificaciones (cmd statusbar collapse).",
                args_schema=_Empty,
                infer_schema=False,
            )
        )
        added += 1
    if "android_review_and_dismiss_notifications" not in names:
        tools_list.append(
            StructuredTool.from_function(
                _review_and_dismiss,
                name="android_review_and_dismiss_notifications",
                description=(
                    "Lee y descarta en lote las notificaciones Android dismissible visibles. "
                    "Usar cuando el usuario pida revisar/descartar todas/todo en un solo turno; "
                    "devuelve processed[] con title/body para resumir insights."
                ),
            )
        )
        added += 1
    if added:
        _log.info("Android ADB helper tools registered: %d", added)
    return added
