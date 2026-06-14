"""Fast-path planning helpers for the manager graph."""

from __future__ import annotations

import re
from typing import Any

from duckclaw.guardrails.loader import load_guardrail
from duckclaw.manager.routing import (
    _LONE_HTTP_URL_ONLY_LINE,
    _is_job_hunter_worker,
    _pick_quant_trader_worker,
)
from duckclaw.prompt_policies import PromptPolicyResolver
from duckclaw.utils.logger import get_obs_logger, log_sys


_obs = get_obs_logger()

_QUANT_HRP_AFFIRM_RE = re.compile(
    r"^\s*("
    r"sí|si|ok|dale|adelante|procede|proceda|proceder|"
    r"continua|continúa|continuar|sigue|siguiente|hazlo|"
    r"confirmo|yes|vamos|listo|claro"
    r")\s*\.?[\s!¡?¿]*$",
    re.IGNORECASE | re.UNICODE,
)


def _stringify_turn_content_for_hrp(content: Any) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for p in content:
            if isinstance(p, dict) and (str(p.get("type") or "").lower() == "text"):
                parts.append(str(p.get("text") or ""))
            elif isinstance(p, str):
                parts.append(p)
        return " ".join(x for x in parts if x)
    return str(content)


def _iter_assistant_bodies_newest_first(history: Any) -> list[str]:
    """Cuerpos assistant de más reciente a más antiguo."""
    out: list[str] = []
    if not history:
        return out
    for turn in reversed(list(history)):
        if not isinstance(turn, dict):
            continue
        role = str(turn.get("role") or turn.get("type") or "").lower()
        if role not in ("assistant", "ai", "model"):
            continue
        body = _stringify_turn_content_for_hrp(turn.get("content")).strip()
        if body:
            out.append(body)
    return out


def _find_hrp_rebalance_affirm_context_assistant_body(history: Any) -> str | None:
    """Localiza el assistant más reciente que pide cierre/continuación de un hilo HRP."""
    for body in _iter_assistant_bodies_newest_first(history):
        if _assistant_asks_hrp_rebalance_followup(body):
            return body
    return None


def _manager_extract_tickers(text: str) -> list[str]:
    """Extrae tickers US de texto assistant/planned."""
    raw = str(text or "")
    if not raw:
        return []
    banned = {
        "SYSTEM",
        "EVENT",
        "GOALS",
        "HITL",
        "IBKR",
        "UUID",
        "JSON",
        "SQL",
        "HRP",
        "CFD",
        "PNL",
        "LIVE",
        "PAPER",
        "PARA",
        "LUEGO",
        "CON",
        "DEL",
        "LAS",
        "LOS",
        "QUE",
        "UNA",
        "UNO",
        "POR",
        "AND",
        "THE",
        "FOR",
        "TO",
        "Y",
        "O",
        "TAREA",
        "TASK",
    }
    out: list[str] = []
    seen: set[str] = set()
    for tk in re.findall(r"\b[A-Z]{1,5}\b", raw):
        tk = tk.upper()
        if tk in banned:
            continue
        if tk not in seen:
            out.append(tk)
            seen.add(tk)
    return out


def _manager_hrp_ticker_label(hrp_body: str) -> str:
    tickers = _manager_extract_tickers(hrp_body)
    if len(tickers) >= 2:
        return f"({tickers[0]}/{tickers[1]})"
    if len(tickers) == 1:
        return f"({tickers[0]})"
    return "(HRP)"


def _assistant_asks_generic_confirmation(assistant_text: str) -> bool:
    """Asistente pide confirmación genérica (¿procedo?, ¿deseas?, ¿quieres?, etc.)."""
    text = (assistant_text or "").strip()
    if not text:
        return False
    if "?" not in text and "¿" not in text:
        return False
    low = text.lower()
    return any(k in low for k in ("procedo", "proceda", "proceder", "deseas", "quieres"))


def _assistant_asks_hrp_rebalance_followup(assistant_text: str) -> bool:
    text = (assistant_text or "").strip()
    if not text:
        return False
    low = text.lower()
    if "deseas" in low and "genere" in low and any(
        x in low for x in ("señal", "señales", "compra", "rebalance", "hrp", "meta", "spy")
    ):
        return True
    if "rebalance_hrp" in low or "rebalanceo hrp" in low or ("rebalanceo" in low and "hrp" in low):
        if "?" in text or "¿" in text or "procedo" in low or "señal" in low or "rebalance" in low:
            return True
    if ("procedo" in low or "proceda" in low) and any(
        x in low for x in ("señal", "rebalance", "hrp", "meta", "spy", "alineación", "alineacion", "ibkr")
    ):
        return True
    if "revisión" in low and "alineación" in low and "hrp" in low and "ibkr" in low:
        return True
    if "pypfopt" in low or "pyportfolioopt" in low or "hierarchical risk" in low or (
        "hrp" in low and any(x in low for x in ("óptim", "optim", "peso", "pypfopt"))
    ):
        if "?" in text or "procedo" in low or "señal" in low or "rebalance" in low or "deseas" in low:
            return True
    return False


def _try_quant_hrp_affirm_followup(
    incoming: str,
    history: Any,
    assigned: str,
    tenant_id: str,
    available_plan: list[str],
) -> tuple[str, list[str], str, str] | None:
    if not _QUANT_HRP_AFFIRM_RE.match((incoming or "").strip()):
        return None
    plans = [str(x) for x in (available_plan or []) if x]
    if "Quant-Trader" not in plans:
        return None
    worker = (assigned or "").strip()
    tenant = (tenant_id or "").strip().lower()
    if worker != "Quant-Trader" and tenant != "cuantitativo":
        return None
    bodies = _iter_assistant_bodies_newest_first(history)
    newest = bodies[0] if bodies else None
    if newest and _assistant_asks_hrp_rebalance_followup(newest):
        last_assistant = newest
    elif newest and _assistant_asks_generic_confirmation(newest):
        return None
    else:
        last_assistant = _find_hrp_rebalance_affirm_context_assistant_body(history)
    if not last_assistant:
        return None
    ticker_label = _manager_hrp_ticker_label(last_assistant)
    title = f"Confirmación rebalanceo HRP {ticker_label}"
    task_list = [
        load_guardrail("manager_tasks", "quant_hrp_affirm_task_confirm"),
        load_guardrail("manager_tasks", "quant_hrp_affirm_task_flow"),
    ]
    planned = f"{ticker_label} " + load_guardrail("manager_tasks", "quant_hrp_affirm_planned")
    return (title, task_list, planned, "Quant-Trader")


def _try_quant_generic_affirm_followup(
    incoming: str,
    history: Any,
    assigned: str,
    tenant_id: str,
    available_plan: list[str],
) -> tuple[str, list[str], str, str] | None:
    """Confirmación corta tras pregunta genérica del asistente."""
    if not _QUANT_HRP_AFFIRM_RE.match((incoming or "").strip()):
        return None
    plans = [str(x) for x in (available_plan or []) if x]
    if "Quant-Trader" not in plans:
        return None
    worker = (assigned or "").strip()
    tenant = (tenant_id or "").strip().lower()
    if worker != "Quant-Trader" and tenant != "cuantitativo":
        return None
    bodies = _iter_assistant_bodies_newest_first(history)
    newest = bodies[0] if bodies else None
    if not newest:
        return None
    if _assistant_asks_hrp_rebalance_followup(newest):
        return None
    if not _assistant_asks_generic_confirmation(newest):
        return None
    title = "Confirmación — continuar plan Quant-Trader"
    task_list = [load_guardrail("manager_tasks", "quant_generic_affirm_task_flow")]
    planned = load_guardrail("manager_tasks", "quant_generic_affirm_planned")
    planned = f"{planned}\n\nContexto del mensaje anterior del asistente:\n{newest[:4000]}"
    return (title, task_list, planned, "Quant-Trader")


def _manager_visual_generation_intent(incoming: str) -> bool:
    """Pedido explícito de imagen (txt2img) -> delegar a Quant-Trader sin planner MLX."""
    text = (incoming or "").strip()
    if not text or len(text) > 2000:
        return False
    low = text.lower()
    if re.search(
        r"(?:\b(?:genera|generar|crea|crear|dibuja|dibujar|haz(?:me)?|hacer|pinta|pintar)\b.{0,50}\b(?:imagen(?:es)?|foto(?:s)?|ilustraci[oó]n(?:es)?|caricatura(?:s)?|avatar(?:es)?|picture|image(?:s)?)\b)",
        low,
        re.IGNORECASE | re.DOTALL,
    ):
        return True
    return bool(re.search(r"\b(?:txt2img|text-to-image|stable\s*diffusion|comfyui)\b", low, re.IGNORECASE))


def _try_visual_generation_fast_plan(
    incoming: str,
    available_plan: list[str],
) -> tuple[str, list[str], str, str] | None:
    """Evita planner MLX lento en admin/Telegram cuando el usuario pide una imagen."""
    if not _manager_visual_generation_intent(incoming):
        return None
    quant_trader = _pick_quant_trader_worker(available_plan)
    if not quant_trader:
        return None
    title = "Generar imagen (ComfyUI)"
    task_list = [
        "Usar generate_visual_asset una sola vez con el prompt del usuario.",
        "No repetir la herramienta si ya hubo un ToolMessage OK en este turno.",
    ]
    planned = (incoming or "").strip()
    log_sys(_obs, "Plan rápido imagen -> %s (sin planner MLX)", quant_trader)
    return (title, task_list, planned, quant_trader)


def _try_quant_url_research_fast_plan(
    incoming: str,
    available_plan: list[str],
) -> tuple[str, list[str], str, str] | None:
    """Mensaje solo URL (HTTPS): evita planner MLX lento."""
    inc = (incoming or "").strip()
    if not _LONE_HTTP_URL_ONLY_LINE.match(inc):
        return None
    if _manager_visual_generation_intent(inc):
        return None
    quant_trader = _pick_quant_trader_worker(available_plan)
    if not quant_trader:
        return None
    low = inc.lower()
    if "reddit.com" in low:
        title = "Investigar enlace Reddit"
        task_list = [
            "Usar reddit_get_post o reddit_search_reddit con el enlace del usuario.",
            "Sintetizar hallazgos; no inventar contenido del post.",
        ]
    elif "mql5.com" in low:
        title = "Extraer código MQL5 (browser)"
        task_list = [
            "Usar run_browser_sandbox primero (PROTOCOLO MQL5, plantilla stealth).",
            "No usar solo tavily_search sin haber pasado por el sandbox para esta URL.",
        ]
    else:
        title = "Investigar URL"
        task_list = [
            "Usar run_browser_sandbox o tavily_search según el dominio.",
            "Entregar resumen con evidencia de tools del mismo turno.",
        ]
    planned = inc
    log_sys(_obs, "Plan rápido URL -> %s (sin planner MLX)", quant_trader)
    return (title, task_list, planned, quant_trader)


def _manager_greeting_fast_path_ok(incoming: str) -> bool:
    """Saludo corto sin comando fly: evita plan LLM y delegación al worker."""
    raw = (incoming or "").strip()
    if not raw or raw.startswith("/"):
        return False
    from duckclaw.graphs.on_the_fly_commands import _is_simple_greeting

    return _is_simple_greeting(raw)


def _manager_capabilities_fast_path_ok(incoming: str) -> bool:
    """"Qué puedes hacer?" y similares: respuesta fija sin plan ni subagente."""
    raw = (incoming or "").strip()
    if not raw or raw.startswith("/"):
        return False
    from duckclaw.graphs.on_the_fly_commands import _is_capabilities_smalltalk

    return _is_capabilities_smalltalk(raw)


def _greeting_fast_reply_text(worker_id: str | None) -> str:
    worker = (worker_id or "").strip()
    worker_lower = worker.lower()
    if _is_job_hunter_worker(worker):
        return (
            "Hola. Soy **OSINT JobHunter** (búsqueda y extracción de ofertas). "
            "Di rol, ubicación o remoto y, si quieres, portales (LinkedIn, Lever, etc.). "
            "Necesitas `/sandbox on` para ejecutar código en el contenedor browser."
        )
    if worker_lower == "bi-analyst":
        return (
            "Hola. Soy tu analista de BI (DuckDB): consultas de solo lectura, esquema, métricas y gráficos cuando lo pidas. "
            "¿Qué quieres revisar?"
        )
    if worker:
        return f"Hola. Aquí {worker}. ¿En qué puedo ayudarte?"
    return "Hola. ¿En qué puedo ayudarte?"


def _capabilities_fast_reply_text(
    worker_id: str | None,
    *,
    coordinator_id: str | None = None,
    delegation_pool: list[str] | None = None,
    prompt_policies: PromptPolicyResolver | None = None,
) -> str:
    if prompt_policies is None:
        raise RuntimeError(
            "capabilities fast reply requires an injected PromptPolicyResolver "
            "with a migrated DuckDB connection"
        )
    coord = (coordinator_id or "").strip()
    pool = [x for x in (delegation_pool or []) if (x or "").strip()]
    if coord and pool:
        lines = "\n".join(f"- {worker}" for worker in pool)
        return prompt_policies.format("capability", "axis_coordinator", coord=coord, lines=lines)
    worker = (worker_id or "").strip()
    worker_lower = worker.lower()
    worker_lower_norm = worker_lower.replace("_", "-")
    if _is_job_hunter_worker(worker):
        return prompt_policies.load("capability", "job_hunter")
    if worker_lower == "bi-analyst":
        return prompt_policies.load("capability", "bi_analyst")
    if worker_lower == "finanz":
        return prompt_policies.load("capability", "finanz")
    if worker_lower_norm == "siata-analyst":
        return prompt_policies.load("capability", "siata_analyst")
    if worker:
        return prompt_policies.format("capability", "generic_worker", worker_id=worker)
    return prompt_policies.load("capability", "default_fallback")


__all__ = [
    "_capabilities_fast_reply_text",
    "_greeting_fast_reply_text",
    "_manager_capabilities_fast_path_ok",
    "_manager_greeting_fast_path_ok",
    "_manager_visual_generation_intent",
    "_try_quant_generic_affirm_followup",
    "_try_quant_hrp_affirm_followup",
    "_try_quant_url_research_fast_plan",
    "_try_visual_generation_fast_plan",
]
