"""
Resiliencia de planificación en el grafo Manager: reintentos con replan y mensaje final agotado.

Variables de entorno:
- ``DUCKCLAW_AGENT_MAX_PLAN_ATTEMPTS``: intentos de plan → invoke worker (default 3, rango 1–10).
- ``DUCKCLAW_AGENT_REPLAN_STRATEGY``: cualquier valor salvo ``off``/``false``/``0``/``no`` deja el replan activo (p. ej. ``hybrid``, ``on``). ``off`` lo desactiva.
"""

from __future__ import annotations

import os
import re
from typing import Any

from duckclaw.integrations.llm_providers import is_transient_inference_connection_error


def plan_max_attempts_from_env() -> int:
    raw = (os.environ.get("DUCKCLAW_AGENT_MAX_PLAN_ATTEMPTS") or "3").strip()
    try:
        n = int(raw)
        return max(1, min(n, 10))
    except ValueError:
        return 3


def replan_strategy_from_env() -> str:
    return (os.environ.get("DUCKCLAW_AGENT_REPLAN_STRATEGY") or "hybrid").strip().lower()


def replan_enabled() -> bool:
    return replan_strategy_from_env() not in ("off", "false", "0", "no")


def format_replan_task_suffix(plan_attempt_index: int, max_attempts: int) -> str:
    """Directiva añadida al planned_task cuando ``plan_attempt_index > 0`` (antes del invoke actual)."""
    # plan_attempt_index es el índice del intento actual (0-based): en el segundo paso vale 1.
    attempt_human = plan_attempt_index + 1
    return (
        f"\n\n[REPLAN intento {attempt_human}/{max_attempts}] "
        "Prioriza herramientas con datos verificables (read_sql, inspect_schema, get_ibkr_portfolio). "
        "Evita repetir una estrategia que ya falló; usa llamadas mínimas y cita evidencia de tools en la respuesta."
    )


def format_exhausted_plan_failure(reasons: list[str]) -> str:
    """Mensaje visible al usuario cuando se agotan los intentos de replan."""
    unique: list[str] = []
    for r in reasons:
        s = (r or "").strip()
        if s and s not in unique:
            unique.append(s)
    body = "; ".join(unique) if unique else "varios fallos al ejecutar el plan o la inferencia."
    return (
        "No pude completarlo tras varios intentos. Causas registradas: "
        f"{body}\n\n"
        "Revisa que el backend de inferencia (p. ej. MLX) esté arriba, la base DuckDB accesible "
        "y vuelve a intentar con una petición más concreta."
    )


_INFERENCE_FAIL_PATTERNS = re.compile(
    r"(no pude completar la inferencia|backend de inferencia|inferencia \(.*\) no está|"
    r"connection refused|econnrefused|errno 61|remote protocol|failed to establish)",
    re.IGNORECASE,
)


def worker_reply_suggests_replan_without_tools(raw_reply: str) -> bool:
    """
    Heurística: respuesta “exitosa” del worker pero sin herramientas usadas y con indicios de fallo de backend.
    """
    text = (raw_reply or "").strip()
    if len(text) < 12:
        return False
    return bool(_INFERENCE_FAIL_PATTERNS.search(text))


def classify_exception_for_replan(exc: BaseException, duckdb_config_clash: bool) -> tuple[bool, str]:
    """
    Devuelve ``(retryable_for_replan, reason_label)`` para excepciones en ``invoke_worker``.
    """
    if duckdb_config_clash:
        return False, "duckdb: conflicto RO/RW en el mismo archivo (configuración)"
    if is_transient_inference_connection_error(exc):
        return True, "inferencia: error transitorio de conexión o timeout"
    low = str(exc).lower()
    if any(
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
        return True, "inferencia: conexión rechazada o protocolo remoto"
    return False, f"error: {type(exc).__name__}"


def resilience_escalation_wants_read_sql(incoming: str, plan_attempt_index: int) -> bool:
    """
    Híbrido: en reintentos del manager, fuerza lectura SQL en Finanz ante consultas de datos locales.
    """
    if plan_attempt_index < 1:
        return False
    low = (incoming or "").lower()
    if plan_attempt_index >= 2:
        keys = (
            "cuenta",
            "cuentas",
            "saldo",
            "balance",
            "iban",
            "duckdb",
            "tabla",
            "datos",
            "finanz",
            "extracto",
            "movimiento",
        )
        return any(k in low for k in keys)
    keys = ("cuenta", "cuentas", "saldo", "balance", "extracto", "movimiento", "iban")
    return any(k in low for k in keys)


def merge_failure_reasons(prev: Any, new: str) -> list[str]:
    out = list(prev) if isinstance(prev, list) else []
    n = (new or "").strip()
    if n and n not in out:
        out.append(n)
    return out
