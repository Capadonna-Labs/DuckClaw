"""Worker-to-worker delegation tool (manifest ``allowed_delegates``)."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

_log = logging.getLogger(__name__)

from duckclaw.stall_detector import StallDetector

# the same task to the same worker with the same outcome three times: the caller is going in circles
_STALL = StallDetector(repeats=3)


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

    def _call(worker_id: str, task: str, runtime: Any) -> dict[str, Any]:
        from duckclaw.workers.worker_invoke import invoke_delegated_worker

        if runtime is None:
            return {"status": "error", "message": "invoke_worker: runtime no disponible"}

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
        sig = hashlib.sha1(f"{result.status}|{result.reply}".encode("utf-8", "ignore")).hexdigest()
        task_key = hashlib.sha1(task.encode("utf-8", "ignore")).hexdigest()[:12]
        if _STALL.observe(f"{caller_worker_id}>{worker_id}>{task_key}", sig):
            payload["stalled"] = True
            payload["note"] = "Misma tarea y mismo resultado 3 veces seguidas: cambia de enfoque, acota la tarea o responde al usuario con lo que ya tienes."
        return payload

    def invoke_worker(worker_id: str, task: str) -> str:
        from duckclaw.workers.worker_delegate_runtime import get_worker_delegate_runtime

        return json.dumps(_call(worker_id, task, get_worker_delegate_runtime()), ensure_ascii=False)

    allowed_list = ", ".join(allowed)
    tools.append(
        StructuredTool.from_function(
            func=invoke_worker,
            name="invoke_worker",
            description=(
                "Invoca otro worker del catálogo (solo ids en allowed_delegates: "
                f"{allowed_list}). "
                "Pasa task con contexto completo; para dashboards HTML incluye report_id=<chat_id>."
            ),
        )
    )

    from duckclaw.workers.worker_jobs import async_workers_max, get_worker_jobs

    if async_workers_max() <= 0:
        return

    def start_worker(worker_id: str, task: str) -> str:
        from duckclaw.workers.worker_delegate_runtime import get_worker_delegate_runtime

        runtime = get_worker_delegate_runtime()      # captured here: the job thread does not see this turn's context
        job_id = get_worker_jobs().start(lambda: _call(worker_id, task, runtime))
        if job_id is None:
            return json.dumps({"status": "busy", "message": f"tope de {async_workers_max()} workers en segundo plano"}, ensure_ascii=False)
        return json.dumps({"status": "Started", "job_id": job_id}, ensure_ascii=False)

    def worker_result(job_id: str) -> str:
        return json.dumps(get_worker_jobs().result(job_id), ensure_ascii=False)

    def stop_worker(job_id: str) -> str:
        return json.dumps({"stopped": get_worker_jobs().stop(job_id)}, ensure_ascii=False)

    tools.extend(
        StructuredTool.from_function(func=fn, name=name, description=desc)
        for fn, name, desc in (
            (start_worker, "start_worker", f"Como invoke_worker (ids: {allowed_list}) pero vuelve al instante con un job_id; el worker sigue en segundo plano."),
            (worker_result, "worker_result", "Estado de un job de start_worker: running, done (con result), cancelled o unknown."),
            (stop_worker, "stop_worker", "Descarta un job de start_worker que ya no hace falta; su resultado no se entregará."),
        )
    )


__all__ = ["register_worker_delegate_tools"]
