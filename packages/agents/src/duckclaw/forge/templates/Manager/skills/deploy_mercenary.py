"""StructuredTool deploy_mercenary — sesión efímera Caged Beast (spec: Caged_Beast_Mercenary)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

from duckclaw.forge.skills.research_bridge import _run_async_from_sync
from duckclaw.graphs.sandbox import run_mercenary_ephemeral_async

_log = logging.getLogger(__name__)


class DeployMercenaryInput(BaseModel):
    directive: str = Field(..., min_length=1, description="Instrucción explícita para el proceso enjaulado.")
    timeout: int = Field(default=300, ge=1, le=600, description="Segundos máximos de ejecución (1–600).")


def _run(directive: str, timeout: int = 300) -> dict[str, Any]:
    preview = (directive[:80] + "…") if len(directive) > 80 else directive
    _log.info("deploy_mercenary: start timeout=%s directive_preview=%r", timeout, preview)
    task_id = uuid.uuid4().hex[:20]
    return _run_async_from_sync(
        run_mercenary_ephemeral_async(directive.strip(), int(timeout), task_id=task_id)
    )


def get_deploy_mercenary_tool() -> StructuredTool:
    return StructuredTool.from_function(
        _run,
        name="deploy_mercenary",
        args_schema=DeployMercenaryInput,
        description=(
            "Ejecuta una sesión efímera Docker aislada (Zero-Trust por defecto sin red). "
            "El contenedor debe escribir /workspace/output/result.json. "
            "Úsalo solo para trabajo pesado aislado cuando el worker normal no aplique."
        ),
    )
