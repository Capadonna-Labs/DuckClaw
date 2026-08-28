"""Worker-to-worker delegation tool (manifest ``allowed_delegates``)."""

from __future__ import annotations

import json
import logging
from typing import Any

_log = logging.getLogger(__name__)


def register_worker_delegate_tools(
    tools: list[Any],
    *,
    db: Any,
    spec: Any,
    tenant_id: str = "default",
) -> None:
    allowed = tuple(getattr(spec, "allowed_delegates", None) or ())
    if not allowed:
        return
    if any(getattr(t, "name", None) == "invoke_worker" for t in tools):
        return

    from langchain_core.tools import StructuredTool

    caller_worker_id = str(
        getattr(spec, "logical_worker_id", None)
        or getattr(spec, "worker_id", None)
        or ""
    ).strip()

    def invoke_worker(worker_id: str, task: str) -> str:
        from duckclaw.workers.worker_delegate_runtime import get_worker_delegate_runtime
        from duckclaw.workers.worker_invoke import invoke_delegated_worker

        runtime = get_worker_delegate_runtime()
        if runtime is None:
            return json.dumps(
                {"status": "error", "message": "invoke_worker: runtime no disponible"},
                ensure_ascii=False,
            )

        state = runtime.state if isinstance(runtime.state, dict) else {}
        result = invoke_delegated_worker(
            caller_worker_id=caller_worker_id,
            caller_spec=runtime.spec or spec,
            target_worker_id=worker_id,
            task=task,
            state=state,
            db=runtime.db or db,
            llm=runtime.llm,
            templates_root=runtime.templates_root,
            tenant_id=str(runtime.tenant_id or tenant_id or "default"),
            vault_db_path=str(state.get("vault_db_path") or "").strip(),
            shared_db_path=str(state.get("shared_db_path") or "").strip(),
            llm_provider=runtime.llm_provider or "",
            llm_model=runtime.llm_model or "",
            llm_base_url=runtime.llm_base_url or "",
        )
        payload: dict[str, Any] = {
            "status": result.status,
            "reply": result.reply,
            "elapsed_ms": result.elapsed_ms,
            "delegate_worker_id": result.delegate_worker_id,
        }
        if result.report_id:
            payload["report_id"] = result.report_id
        if result.error:
            payload["error"] = result.error
        return json.dumps(payload, ensure_ascii=False)

    tools.append(
        StructuredTool.from_function(
            func=invoke_worker,
            name="invoke_worker",
            description=(
                "Invoca otro worker del catálogo (solo ids en allowed_delegates). "
                "Pasa task con contexto completo; para dashboards HTML incluye report_id=<chat_id>."
            ),
        )
    )


__all__ = ["register_worker_delegate_tools"]
