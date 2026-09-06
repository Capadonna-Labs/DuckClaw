"""Generic single retry for a manifest-forced tool that closed a turn in prose.

Mirrors ``sandbox_force_repair.py``, which only covers sandbox tools
(``execute_sandbox_script``/``run_sandbox``). Any other manifest ``tool_chains``/``replan``
force had no repair path: if the provider's tool_choice forcing wasn't honored and the
model answered in prose, the turn simply closed without the required side effect —
confirmed live for a delegated worker turn that never called its forced tool despite
being forced.
"""

from __future__ import annotations

import logging
from typing import Any

from langchain_core.messages import SystemMessage


def retry_forced_tool_once(
    invoked_llm: Any,
    groq_msgs: list[Any],
    force_orch_tool: str,
    *,
    worker_log_label: str,
    log: logging.Logger,
) -> tuple[Any | None, list[Any]]:
    """Re-invoke ``invoked_llm`` (already tool_choice-bound to ``force_orch_tool``) once
    more when the first response had no tool_calls. Returns (retry_response, tool_calls);
    tool_calls is empty when the retry also produced none or the call failed.
    """
    from duckclaw.integrations.llm_providers import invoke_chat_model_with_transient_retries

    retry_sys = SystemMessage(
        content=(
            f"OBLIGATORIO: invoca únicamente la tool `{force_orch_tool}` en este turno "
            "con los argumentos requeridos. Prohibido responder en prosa sin tool_call."
        )
    )
    try:
        retry_resp = invoke_chat_model_with_transient_retries(
            invoked_llm, list(groq_msgs) + [retry_sys]
        )
    except Exception as exc:
        log.warning(
            "[%s] orchestration force repair retry failed for forced=%s: %s",
            worker_log_label,
            force_orch_tool,
            exc,
        )
        return None, []

    retry_calls = getattr(retry_resp, "tool_calls", None) or []
    if retry_calls:
        log.info(
            "[%s] orchestration force repair: retry tool_calls=%s",
            worker_log_label,
            [
                tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", None)
                for tc in retry_calls
            ],
        )
    else:
        log.warning(
            "[%s] orchestration force repair: retry produced no tool_calls for "
            "forced=%s — turn will close without it",
            worker_log_label,
            force_orch_tool,
        )
    return retry_resp, retry_calls
