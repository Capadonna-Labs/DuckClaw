"""Format and classify exceptions raised while invoking a worker from the manager."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

from duckclaw.graphs.agent_resilience import (
    classify_exception_for_replan,
    merge_failure_reasons,
    replan_enabled,
)
from duckclaw.utils.logger import get_obs_logger, log_sys

_obs = get_obs_logger()


@dataclass
class InvokeExceptionOutcome:
    reply_msg: str
    replan_after: bool
    exhausted_final: bool
    next_plan_attempt: int
    reasons_acc: list[str]


def _is_wall_clock_invoke_timeout(exc: BaseException, low: str) -> bool:
    return isinstance(exc, TimeoutError) or (
        "delegate worker graph exceeded" in low and "chat_id=" in low
    )


def _is_duckdb_config_clash(low: str) -> bool:
    return ("same database file" in low and "different configuration" in low) or (
        "duckdb" in low and "read_only" in low
    )


def _wall_clock_timeout_user_message() -> str:
    try:
        from duckclaw.workers.worker_invoke import _manager_worker_timeout_sec

        lim = int(_manager_worker_timeout_sec() or 0)
        if lim <= 0:
            lim = int(float(os.environ.get("DUCKCLAW_DELEGATE_INVOKE_TIMEOUT_SEC") or "900"))
    except Exception:
        lim = 900
    return (
        f"No pude cerrar el turno a tiempo (límite ~{lim}s). "
        "Las tools pudieron ejecutarse, pero falló la síntesis final por timeout. "
        "Reintenta pidiendo un resumen más corto o acota la tarea."
    )


def _connection_failure_user_message(exc: BaseException, llm_provider: str) -> str | None:
    low = str(exc).lower()
    if not any(
        x in low
        for x in (
            "connection error",
            "connection refused",
            "remote protocol",
            "failed to establish",
            "errno 61",
            "econnrefused",
        )
    ):
        return None
    prov = (llm_provider or "").strip().lower()
    detail = str(exc)[:400]
    if prov in ("openrouter", "or", "router", "deepseek", "groq", "openai", "anthropic", "gemini"):
        return (
            f"No se pudo conectar al proveedor LLM «{prov or 'cloud'}». "
            "Comprueba red, API key en Integraciones y que el modelo sea el slug correcto "
            "(en OpenRouter: `deepseek/deepseek-v4-flash`, no la API directa de DeepSeek).\n\n"
            f"Detalle: {detail}"
        )
    return (
        "El backend de inferencia local no está disponible o se reinició "
        "(p. ej. MLX en :8080). Si usas OpenRouter u otra API cloud, elige ese proveedor "
        "en el selector de modelos; no hace falta MLX.\n\n"
        f"Detalle: {detail}"
    )


def resolve_invoke_worker_exception(
    exc: BaseException,
    *,
    llm_provider: str,
    chat_id: str,
    pa: int,
    max_a: int,
    reasons_acc: list[str],
) -> InvokeExceptionOutcome:
    """Map an invoke failure to user-visible reply + replan flags."""
    msg = str(exc)[:2048]
    low = msg.lower()
    wall = _is_wall_clock_invoke_timeout(exc, low)
    duckdb_clash = _is_duckdb_config_clash(low)

    if wall:
        msg = _wall_clock_timeout_user_message()
    elif not duckdb_clash:
        conn_msg = _connection_failure_user_message(exc, llm_provider)
        if conn_msg:
            msg = conn_msg

    replan_after = False
    exhausted_final = False
    next_plan_attempt = pa
    reasons = list(reasons_acc or [])

    if wall:
        # Replanning would discard tool results and often re-hit the same ceiling.
        reasons = merge_failure_reasons(reasons, "timeout: wall-clock invoke (~síntesis no cerró)")
        try:
            from duckclaw.graphs.chat_cancel import clear_graph_interrupt

            clear_graph_interrupt(str(chat_id or "").strip())
        except Exception:
            pass
        log_sys(
            _obs,
            "manager invoke timeout: reporting to user (no replan) chat_id=%s",
            chat_id,
        )
    else:
        retryable, reason = classify_exception_for_replan(exc, duckdb_clash)
        if replan_enabled() and retryable:
            reasons = merge_failure_reasons(reasons, reason)
            if pa + 1 < max_a:
                replan_after = True
                next_plan_attempt = pa + 1
                log_sys(
                    _obs,
                    "manager replan: excepción recuperable -> intento %s/%s (%s)",
                    pa + 2,
                    max_a,
                    reason,
                )
            else:
                exhausted_final = True

    return InvokeExceptionOutcome(
        reply_msg=msg,
        replan_after=replan_after,
        exhausted_final=exhausted_final,
        next_plan_attempt=next_plan_attempt,
        reasons_acc=reasons,
    )


__all__ = ["InvokeExceptionOutcome", "resolve_invoke_worker_exception"]
