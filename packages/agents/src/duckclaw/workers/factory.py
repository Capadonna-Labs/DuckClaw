"""
WorkerFactory: build a LangGraph instance from a worker template.

Input: worker_id, db_path, optional telegram_chat_id, instance_name.
Output: Compiled LangGraph with persistent state, ready for events.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import URLError
from urllib import request as _urllib_request

_log = logging.getLogger(__name__)
from pathlib import Path
from typing import Any, Literal, Optional

from duckclaw.db_write_queue import enqueue_duckdb_write_sync, poll_task_status_sync
from duckclaw.debug_session_log import agent_debug_log

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore[misc, assignment]

from duckclaw.integrations.telegram import effective_telegram_bot_token_outbound
from duckclaw.debug_session_log import agent_debug_log
from duckclaw.utils.logger import format_chat_log_identity, log_tool_execution_sync, set_log_context
from duckclaw.utils.telegram_markdown_v2 import llm_markdown_to_telegram_html
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.workers import read_pool
from duckclaw.workers.manifest import WorkerSpec, load_manifest
from duckclaw.workers.loader import append_domain_closure_block, load_system_prompt, load_skills
from duckclaw.workers.field_reflection import (
    collect_tool_error_digest,
    finanz_field_reflection_enabled,
    format_field_experience_block,
    last_tool_batch_has_error,
    lesson_belief_key,
    parse_reflection_json,
    persist_field_lesson,
)

_NO_TASK_PATTERN = re.compile(
    r"^(hola|hi|hey|buenos?\s*d[ií]as?|buenas?\s*tardes?|buenas?\s*noches?|"
    r"qu[eé]\s*tal|qu[eé]\s*hay|saludos?|hello|ciao|adios?|chao)\s*[!.]?$",
    re.IGNORECASE,
)

# Preguntas por filas/contenido (no catálogo). Incluye «hay algo en la tabla X» (evita confundir con listar tablas).
_TABLE_CONTENT_PHRASE = re.compile(
    r"\b(que\s+hay\s+en\s+la\s+tabla|qué\s+hay\s+en\s+la\s+tabla|"
    r"hay\s+algo\s+en\s+(la\s+)?tabla|hay\s+datos\s+en\s+(la\s+)?tabla|"
    r"contenido\s+de\s+la\s+tabla|muestr(a|ame)\s+la\s+tabla|ver\s+datos\s+de\s+la\s+tabla|"
    r"registros?\s+de\s+la\s+tabla|filas?\s+de\s+la\s+tabla|select\s+\*\s+from|select\s+.+\s+from)\b",
    re.IGNORECASE,
)

# Preguntas sobre DB/tablas/esquema son siempre tarea concreta (evitar "¿Cuál es mi tarea?")
_CONCRETE_TASK_KEYWORDS = re.compile(
    r"\b(db|database|base\s+de\s+datos|tablas?|tables?|esquema|schema|nombre\s+de\s+la\s+db|"
    r"qu[eé]\s+tablas|estructura|get_db_path|read_sql|admin_sql|consultar|cuenta|saldo|portfolio)\b",
    re.IGNORECASE,
)

# read_sql sobre read_json_auto sin LIMIT puede devolver megabytes y saturar el contexto del LLM.
_READ_SQL_MAX_RESPONSE_CHARS = max(8_000, int(os.environ.get("DUCKCLAW_READ_SQL_MAX_RESPONSE_CHARS", "80000")))

# run_sandbox puede volcar cientos de KB; sin context_monitor el ToolMessage iría entero al LLM.
_RUN_SANDBOX_TOOL_LLM_MAX_CHARS = max(4_000, int(os.environ.get("DUCKCLAW_RUN_SANDBOX_TOOL_LLM_MAX_CHARS", "12000")))

# Cache en memoria por chat para comparar PnL entre ticks consecutivos de /goals.
_GOALS_PREV_UNREALIZED_PNL_BY_CHAT: dict[str, float] = {}


def _truncate_read_sql_result_for_llm(raw: str) -> str:
    if not isinstance(raw, str) or len(raw) <= _READ_SQL_MAX_RESPONSE_CHARS:
        return raw
    return json.dumps(
        {
            "warning": (
                "Salida truncada por límite de tamaño del gateway. Para JSON remotos usa LIMIT, "
                "menos columnas, o run_sandbox para aplanar/resumir el archivo completo."
            ),
            "preview": raw[:_READ_SQL_MAX_RESPONSE_CHARS],
            "total_chars": len(raw),
            "omitted_chars": len(raw) - _READ_SQL_MAX_RESPONSE_CHARS,
        },
        ensure_ascii=False,
    )


# Tarea explícita del manager (plan): nunca tratar como "sin tarea"
def _worker_log_label(worker_id: str) -> str:
    """Etiqueta corta solo para texto de log (no sustituye el id real del estado)."""
    w = (worker_id or "").strip()
    low = w.lower().replace("_", "")
    if low == "themindcrupier":
        return "crupier"
    return w or "worker"


def _worker_use_heuristic_first_tool(spec: WorkerSpec) -> bool:
    """Manifest ``agent_node.heuristic_first_tool`` tiene prioridad sobre ``DUCKCLAW_WORKER_HEURISTIC_FIRST_TOOL``."""
    o = getattr(spec, "agent_node_heuristic_first_tool", None)
    if isinstance(o, bool):
        return o
    raw = (os.getenv("DUCKCLAW_WORKER_HEURISTIC_FIRST_TOOL") or "true").strip().lower()
    return raw in ("1", "true", "yes", "on")


_PLANNED_TASK_PREFIX = (
    "TAREA:",
    "TAREA ",
    "Ejecuta la herramienta",
    "Ejecuta read_sql",
    "Ejecuta admin_sql",
    "Usa read_sql",
    "Usa admin_sql",
    "usa get_db_path",
)


_PQRSD_ACK_ONLY = re.compile(
    r"^(gracias|muchas\s+gracias|ok\.?|vale\.?|listo\.?|perfecto\.?|entendido\.?)\s*!?$",
    re.IGNORECASE,
)


def _pqrsd_substantive_forced_fetch(incoming: str, *, summarize_directive: bool) -> bool:
    """
    True si conviene forzar ``pqrsd_fetch_canonical`` como primera tool (worker PQRSD).
    Excluye directivas de resumen, saludos cortos y agradecimientos sin pregunta.
    """
    if summarize_directive:
        return False
    text = (incoming or "").strip()
    if not text:
        return False
    if _is_no_task(text):
        return False
    if _PQRSD_ACK_ONLY.match(text):
        return False
    if len(text) <= 12 and text.lower() in {"ok", "vale", "sip", "sí", "si", "👍", "👍🏻"}:
        return False
    return True


def _pqrsd_sandbox_prefers_chat_datos_over_forced_fetch(incoming: str) -> bool:
    """
    True cuando el mensaje sugiere **radicación / llenado de formulario / automatización**
    en sandbox: en ese caso **no** forzar ``pqrsd_fetch_canonical`` como primera tool
    para que el modelo pueda **preguntar datos en el chat** antes de invocar tools.
    """
    t = (incoming or "").strip().lower()
    if not t:
        return False
    if re.search(r"\bno\s+autorizo\b", t) or re.search(r"\bno\s+consiento\b", t):
        return False
    # Evitar falsos positivos de “solo información” (p. ej. plazos) salvo que también
    # haya señales claras de acción en el portal.
    if re.search(
        r"\b(solo\s+quiero\s+saber|informaci[oó]n\s+sobre|cu[aá]nto\s+(demora|tarda)|"
        r"plazo[s]?\s+de\s+respuesta|tiempo[s]?\s+de\s+respuesta)\b",
        t,
    ) and not re.search(
        r"\b(radicar|radico|radique|radicaci[oó]n|formulario|llenar|ingresar\s+datos|"
        r"datos\s+para|automatiz|vnc|pqrsd?\s+con\s+ident|an[oó]nima|autorizo|consiento|"
        r"verificaci[oó]n|otp)\b",
        t,
    ):
        return False
    return any(
        re.search(p, t)
        for p in (
            r"\b(radicar|radico|radique|radicaci[oó]n|radicacion)\b",
            r"\b(rellen\w*|llenar)\s+(el\s+)?(formulario|datos)\b",
            r"\bingresar\s+(los\s+)?datos\b",
            r"\b(mis\s+datos|datos\s+para(\s+(el|la)\s+(formulario|portal|pqr))?)\b",
            r"\bautomatiz",
            r"\b(pqr(s|sd)?|pqrsd)\s+con\s+ident",
            r"\b(pqr(s|sd)?|pqrsd)\s+an[oó]n",
            r"\bidentificaci[oó]n\s+an[oó]nima\b",
            r"\bobtener\s+(el\s+)?(n[uú]mero\s+de\s+)?verificaci[oó]n\b",
            r"\bn[uú]mero\s+de\s+verificaci[oó]n\b",
            r"\bc[oó]digo\s+de\s+verificaci[oó]n\b",
            r"\botp\b",
            r"\b(autorizo|consiento)\b",
            r"\bs[ií],?\s*autorizo\b",
            r"\bvnc\b",
        )
    )


def _pqrsd_rad_perfil_datos_first(incoming: str) -> bool:
    """
    True cuando el mensaje indica intención de **presentar** solicitud/PQRSD/denuncia por el canal
    Alcaldía y conviene **preguntar datos** (y opcionalmente persistir perfil) **antes** de forzar
    ``pqrsd_fetch_canonical``. Complementa la heurística de sandbox sin exigir ``/sandbox on``.
    """
    t = (incoming or "").strip().lower()
    if not t:
        return False
    if re.search(r"\bno\s+autorizo\b", t) or re.search(r"\bno\s+consiento\b", t):
        return False
    if re.search(
        r"\b(solo\s+quiero\s+saber|informaci[oó]n\s+sobre|cu[aá]nto\s+(demora|tarda)|"
        r"plazo[s]?\s+de\s+respuesta|tiempo[s]?\s+de\s+respuesta)\b",
        t,
    ) and not re.search(
        r"\b(radicar|solicitud|denuncia|pqrsd|pqr|formulario|presentar|interponer|quiero\s+hacer)\b",
        t,
    ):
        return False
    return bool(
        re.search(r"\b(hacer|presentar|quiero)\s+(una\s+)?solicitud\b", t)
        or re.search(r"\bquiero\s+hacer\s+una\s+solicitud\b", t)
        or re.search(r"\bquiero\s+hacer\s+una\s+petici[oó]n\b", t)
        or re.search(r"\bpetici[oó]n\s+(de\s+)?(pqrsd|pqr|pqrs)\b", t)
        or re.search(r"\b(me\s+gustar[ií]a|quisiera|deseo)\s+hacer\s+(una\s+)?(solicitud|denuncia)\b", t)
        or re.search(
            r"\bc[oó]mo\s+(puedo\s+)?(hacer|presentar|interponer|radicar)\s+(una\s+)?"
            r"(solicitud|denuncia|(?:pqr|pqrs|pqrsd)|petici[oó]n)\b",
            t,
        )
        or re.search(r"\binterponer\s+(una\s+)?(denuncia|queja|reclamo)\b", t)
        or re.search(
            r"\bpresentar\s+(una\s+)?((?:pqr|pqrs|pqrsd)|petici[oó]n|queja|reclamo)\b",
            t,
        )
    )


def _pqrsd_datos_first_over_forced_fetch(incoming: str) -> bool:
    """Incluye flujo sandbox (datos en chat) y flujo perfil/radicación explícita."""
    return _pqrsd_sandbox_prefers_chat_datos_over_forced_fetch(
        incoming
    ) or _pqrsd_rad_perfil_datos_first(incoming)


def _pqrsd_contact_only_skip_forced_fetch(incoming: str) -> bool:
    """
    True cuando el mensaje parece **solo** bloque de identificación/contacto sin relato del caso.
    Evita forzar ``pqrsd_fetch_canonical`` (y el plano enorme del portal) antes de pedir hechos.
    """
    t = (incoming or "").strip()
    if len(t) < 30:
        return False
    if "@" not in t:
        return False
    if not re.search(r"\d{6,}", re.sub(r"[.\s]", "", t)):
        return False
    narrative = re.compile(
        r"\b(qu[eé]\s+pas|porque|por\s+que|funcionari|vigilant|secretar[ií]a|oficina|"
        r"maltrat|retraso|plata|corrup|pas[oó]\b|ayer\b|hoy\b|semana\s+pas|"
        r"sucedi[oó]|ocurr[ií]|me\s+grit|denunci|reclam|quej[ao]|insul|"
        r"atenci[oó]n\s+deficient|ventanill|catastr|bibliotec|basur|poste)\b",
        re.IGNORECASE,
    )
    if narrative.search(t):
        return False
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if len(lines) >= 2:
        return True
    return bool(re.search(r"\b\d{1,3}([.\s]\d{3})+\b", t)) and len(t) < 400


def _is_no_task(incoming: str) -> bool:
    """True si el mensaje está vacío o es solo un saludo genérico (sin tarea concreta)."""
    text = (incoming or "").strip()
    if not text:
        return True
    if len(text) < 4:
        return True
    # Tarea planificada por el manager (instrucción explícita)
    if any(text.startswith(p) or p in text for p in _PLANNED_TASK_PREFIX):
        return False
    # Preguntas sobre db/tablas/esquema/nombre son tarea concreta
    if _CONCRETE_TASK_KEYWORDS.search(text):
        return False
    return bool(_NO_TASK_PATTERN.match(text))


def _is_finanz_local_account_write_query(text: str) -> bool:
    """
    True si el usuario pide mutar saldo/cuenta en la DuckDB local (finance_worker).
    Usado para forzar la primera tool `admin_sql` (cola → db-writer), no IBKR.
    """
    if not text or not text.strip():
        return False
    t = text.strip().lower()
    if any(
        k in t
        for k in (
            "ibkr",
            "interactive brokers",
            "bolsa",
            "acciones",
            "portfolio",
            "portafolio",
            "[system_directive:",
        )
    ):
        return False
    if not re.search(
        r"\b(actualiza|actualizar|cambia|cambiar|modifica|modificar|ajusta|ajustar|"
        r"pone|poner|ponga|pon\b|establece|establecer|fija|fijar|deja|dejar|corrige|corregir|"
        r"setea|setear)\b",
        t,
    ):
        return False
    if "saldo" in t or "balance" in t:
        return True
    if "cuenta" in t and any(
        k in t
        for k in (
            "bancolombia",
            "nequi",
            "davivienda",
            "efectivo",
            "global 66",
            "global66",
            "scotiabank",
            "finance_worker",
            "cop",
            "pesos",
            "cero",
        )
    ):
        return True
    if re.search(r"\b(cero|0)\b", t) and ("cop" in t or "peso" in t) and any(
        k in t for k in ("bancolombia", "nequi", "davivienda", "cuenta", "efectivo")
    ):
        return True
    return False


def _is_finanz_local_accounts_query(text: str) -> bool:
    """Cuentas/saldos en DuckDB local (finance_worker); no mezclar con IBKR ni portfolio de bolsa."""
    if not text or not text.strip():
        return False
    t = text.strip().lower()
    if any(k in t for k in ("ibkr", "interactive brokers", "bolsa", "acciones", "portfolio", "portafolio")):
        return False
    return bool(
        re.search(
            r"\b(resumen\s+(de\s+)?(mis\s+)?cuentas|saldos?\s+(de\s+)?(mis\s+)?cuentas|"
            r"mis\s+cuentas\s+bancarias|cuentas\s+bancarias|estado\s+actual\s+de\s+mis\s+cuentas)\b",
            t,
        )
    )


def _is_finanz_debts_query(text: str) -> bool:
    """Deudas en DuckDB local (finance_worker.deudas). Obliga read_sql para no inventar desde el historial."""
    if not text or not text.strip():
        return False
    t = text.strip().lower()
    if "[system_directive:" in t:
        return False
    return bool(
        re.search(
            r"\b("
            r"resumen\s+(de\s+)?(mis\s+)?deudas|"
            r"mis\s+deudas|"
            r"deudas\s+(activas|pendientes|registradas)|"
            r"cu[aá]nto\s+debo\b|"
            r"cu[aá]ntas\s+deudas|"
            r"estado\s+(de\s+)?(mis\s+)?deudas|"
            r"listado\s+(de\s+)?(mis\s+)?deudas|"
            r"qu[eé]\s+deudas\s+tengo|"
            r"total\s+(de\s+)?(mis\s+)?deudas|"
            r"deudas\s+en\s+(la\s+)?(base|db|duckdb)"
            r")\b",
            t,
        )
    )


def _is_finanz_budgets_query(text: str) -> bool:
    """Presupuestos en DuckDB local (finance_worker.presupuestos). Obliga read_sql; sin tool el LLM inventa meses/cifras."""
    if not text or not text.strip():
        return False
    t = text.strip().lower()
    if "[system_directive:" in t:
        return False
    return bool(
        re.search(
            r"\b("
            r"resumen\s+(de\s+)?(mis\s+)?presupuestos?|"
            r"mis\s+presupuestos?|"
            r"presupuestos?\s+(del\s+)?mes|"
            r"estado\s+(de\s+)?(mis\s+)?presupuestos?|"
            r"listado\s+(de\s+)?(mis\s+)?presupuestos?|"
            r"presupuesto\s+vs\s+real|"
            r"presupuestos?\s+vs\s+real|"
            r"cu[aá]nto\s+llevo\s+(gastad[oa]\s+)?(de\s+)?(mis\s+)?presupuestos?|"
            r"presupuestos?\s+en\s+(la\s+)?(base|db|duckdb)"
            r")\b",
            t,
        )
    )


def _finanz_user_requests_ohlcv_ingest(text: str) -> bool:
    """
    True si el usuario pide traer/descargar velas OHLCV (evita que el LLM invente tool calls).
    Requiere palabra clave de mercado + símbolo tipo ticker (1–5 letras mayúsculas).
    """
    if not text or not text.strip():
        return False
    raw = text.strip()
    low = raw.lower()
    # Inyecciones del gateway (p. ej. fallo VLM): suelen mencionar «ingesta» y tokens MLX/VLM en mayúsculas;
    # no deben forzar fetch_market_data (evidencia: logs finanz incoming=META… forced_tool=fetch_market_data).
    if low.startswith("[meta:"):
        return False
    if "quant_core.ohlcv" in low and any(
        k in low for k in ("trae", "descarga", "importa", "ingesta", "actualiza", "bajar", "pull")
    ):
        return True
    # No usar la palabra suelta «ingesta» aquí: en español cubre ingesta VLM/memoria y dispara falsos positivos
    # con acrónimos en mayúsculas (MLX, VLM) en mensajes META del gateway.
    if not any(
        k in low
        for k in (
            "vela",
            "ohlcv",
            "candle",
            "fetch_market",
            "fetch market",
        )
    ):
        return False
    return bool(re.search(r"\b[A-Z]{1,5}\b", raw))


def _quant_user_requests_new_trade_signal(text: str) -> bool:
    """Pedido explícito de crear/proponer señal HITL (Quant Trader). Evidencia: gateway tools usadas=ninguna."""
    if not text or not str(text).strip():
        return False
    low = text.strip().lower()
    if "[system_directive:" in low or "[system_event:" in low:
        return False
    return bool(
        re.search(
            r"\b("
            r"genera(r)?\s+(una\s+)?nueva\s+se[nñ]al|"
            r"genera(r)?\s+(?:(?:la|el|una|tu)\s+)?se[nñ]al|"
            r"genera(r)?\s+se[nñ]ales|"
            r"crear\s+(una\s+)?se[nñ]al|"
            r"crear\s+se[nñ]ales|"
            r"proponer\s+(una\s+)?se[nñ]al|"
            r"proponer\s+se[nñ]ales|"
            r"registr(ar|a)\s+(una\s+)?se[nñ]al|"
            r"registr(ar|a)\s+se[nñ]ales|"
            r"se[nñ]al\s+de\s+rebalanceo|"
            r"se[nñ]ales\s+para\s+tickers?|"
            r"se[nñ]ales\s+con\s+(s[ií]mbolos|simbolos)\s+diferentes|"
            r"propose\s+(a\s+)?(new\s+)?(trade\s+)?signal"
            r")\b",
            low,
        )
    )


def _quant_user_requests_execute_approved_signal(text: str) -> bool:
    """Usuario pide ejecutar señal HITL (Quant Trader). Evidencia: gateway «ejecute execute_approved_signal» → tools usadas=ninguna."""
    if not text or not str(text).strip():
        return False
    low = text.strip().lower()
    if "[system_directive:" in low or "[system_event:" in low:
        return False
    if "/execute_signal" in low:
        return True
    # Mensaje post-HITL del gateway: …ejecute execute_approved_signal (Quant Trader)…
    if "execute_approved_signal" in low:
        return True
    if re.search(r"confirmaci[oó]n\s+registrada\s+para\s+la\s+se[nñ]al", low):
        return True
    if re.search(r"se[nñ]al\s+pendiente", low):
        return True
    if re.search(r"\b(ejecuta|ejecutar|ejecute|lanza|dispara)\b", low) and re.search(
        r"\b(se[nñ]al|orden)\b", low
    ):
        return True
    return False


def _quant_user_requests_autoexec_validation(text: str) -> bool:
    """Intención explícita: validar que auto-ejecución realmente impacta DB + portfolio IBKR."""
    if not text or not str(text).strip():
        return False
    low = text.strip().lower()
    if "[system_directive:" in low or "[system_event:" in low:
        return False
    if "auto-ejecuci" in low or "autoejecuci" in low or "auto ejecuci" in low:
        return True
    if "valida" in low and "funcionando" in low and "señal" in low:
        return True
    if "valida" in low and "ibkr" in low and "db" in low:
        return True
    return False


def _quant_fetch_tool_message_looks_successful(last_msg: Any) -> bool:
    nm = str(getattr(last_msg, "name", None) or "")
    if nm not in ("fetch_ib_gateway_ohlcv", "fetch_market_data"):
        return False
    raw = str(getattr(last_msg, "content", "") or "")
    try:
        d = json.loads(raw)
        if isinstance(d, dict) and d.get("error"):
            return False
    except Exception:
        if raw.strip().lower().startswith("error"):
            return False
    return True


def _quant_is_proceed_like(text: str) -> bool:
    if not text or not str(text).strip():
        return False
    low = str(text).strip().lower()
    if "[system_directive:" in low or "[system_event:" in low:
        return False
    return bool(re.search(r"\b(procede|continu(a|ar)|sigue|adelante|hazlo)\b", low))


def _quant_user_requests_inspect_macro_pgq(text: str) -> bool:
    """Usuario (o manager wrapper) pidió ejecutar grafo PGQ macro; debe invocarse la tool, no inventar estado."""
    if not text or not str(text).strip():
        return False
    low = str(text).strip().lower()
    if "[system_directive:" in low or "[system_event:" in low:
        return False
    collapsed = re.sub(r"[\s_]+", "", low, flags=re.UNICODE)
    if "inspectmacropgq" in collapsed:
        return True
    # "inspect macro pgq" / "inspector pgq macro" / español cercano
    if "macropgq" in collapsed and ("inspect" in low or "inspeccion" in low):
        return True
    return bool(
        re.search(
            r"(inspect(\s|_)*(macro\s*)?pgq|pgq\s*(macro\s*)?(inspect|inspeccion))",
            low,
            re.IGNORECASE,
        )
    )


def _quant_extract_signal_id(text: str) -> str:
    raw = str(text or "")
    m = re.search(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
        raw,
        flags=re.IGNORECASE,
    )
    return str(m.group(0)).lower() if m else ""


def _quant_extract_tickers(text: str) -> list[str]:
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
        # Manager synthetic tasks start with "TAREA: …" — not a valid equity symbol.
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


def _quant_last_human_index(messages: list[Any]) -> int:
    from langchain_core.messages import HumanMessage

    for i in range(len(messages) - 1, -1, -1):
        try:
            if isinstance(messages[i], HumanMessage):
                return i
        except NameError as exc:
            raise
    return -1


def _quant_tool_called_since(messages: list[Any], from_idx: int, tool_name: str) -> bool:
    from langchain_core.messages import ToolMessage

    for m in messages[max(0, from_idx + 1) :]:
        if isinstance(m, ToolMessage) and str(getattr(m, "name", "") or "") == tool_name:
            return True
    return False


def _quant_latest_tool_json_since(messages: list[Any], from_idx: int, tool_name: str) -> dict[str, Any]:
    from langchain_core.messages import ToolMessage

    for m in reversed(messages[max(0, from_idx + 1) :]):
        if not isinstance(m, ToolMessage) or str(getattr(m, "name", "") or "") != tool_name:
            continue
        try:
            raw = str(getattr(m, "content", "") or "")
            data = json.loads(raw) if raw.strip().startswith("{") else {}
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _finanz_should_force_ibkr_after_local_cuentas_read(
    messages: list[Any] | None,
    *,
    logical_worker_id: str,
    has_ibkr: bool,
) -> bool:
    """
    Tras un ToolMessage de read_sql, forzar get_ibkr_portfolio si el último HumanMessage
    fue un resumen general de cuentas locales y aún no hubo get_ibkr_portfolio en ese turno.
    """
    from langchain_core.messages import HumanMessage, ToolMessage

    if not has_ibkr or (logical_worker_id or "").strip().lower() != "finanz":
        return False
    msgs = messages or []
    if not msgs:
        return False
    last = msgs[-1]
    if not isinstance(last, ToolMessage) or (last.name or "") != "read_sql":
        return False
    last_human_idx: int | None = None
    for i in range(len(msgs) - 1, -1, -1):
        if isinstance(msgs[i], HumanMessage):
            last_human_idx = i
            break
    if last_human_idx is None:
        return False
    human_text = str(getattr(msgs[last_human_idx], "content", "") or "")
    if "[SYSTEM_DIRECTIVE:" in human_text:
        return False
    if not _is_finanz_local_accounts_query(human_text):
        return False
    for m in msgs[last_human_idx + 1 :]:
        if isinstance(m, ToolMessage) and (m.name or "") == "get_ibkr_portfolio":
            return False
    return True


_TASK_AWARENESS_PROMPT = """
Además:
- Si no recibes una tarea concreta (mensaje vacío o solo saludos), pregunta: "¿Cuál es mi tarea?" y ofrece ejemplos de lo que puedes hacer según tu rol.
- En tu cierre proactivo invita a usar fly commands: si hablaste de datos o ejecución sugiere /tasks o /team; invita a crear objetivos con /goals (por defecto están vacíos); si de configuración /prompt o /skills; en general /help para ver todos los comandos.
"""

# LeilaAssistant: canal retail; no mencionar comandos con / a la usuaria (ver soul / system_prompt).
_LEILA_TASK_AWARENESS_PROMPT = """
Además:
- Si el mensaje es vacío o solo un saludo, responde cálido y pregunta en qué puedes ayudar (ver catálogo, tallas, dejar datos para avisos) usando **solo lenguaje natural**. Nunca cites comandos con `/` ni pidas a la clienta que los escriba.
"""


def _escape_attach_path(path: str) -> str:
    return str(path).replace("'", "''")


def _same_duckdb_file(a: str, b: str) -> bool:
    """True si dos rutas apuntan al mismo archivo .duckdb (canonicalizadas)."""
    sa = (a or "").strip()
    sb = (b or "").strip()
    if not sa or not sb:
        return False
    try:
        return Path(sa).expanduser().resolve() == Path(sb).expanduser().resolve()
    except Exception:
        return os.path.abspath(sa) == os.path.abspath(sb)


def _resolve_shared_db_path(spec: WorkerSpec, override: Optional[str]) -> Optional[str]:
    """
    Segundo archivo .duckdb (catálogo compartido). Solo si el manifest declara
    forge_context.shared_db_path_env; el body `shared_db_path` puede sustituir la ruta
    sin depender del env.
    """
    env_key = (getattr(spec, "forge_shared_db_path_env", None) or "").strip()
    if not env_key:
        return None
    raw = (override or "").strip()
    if raw:
        return raw
    return (os.environ.get(env_key) or "").strip() or None


def _apply_forge_attaches(
    db: Any,
    private_path: str,
    shared_path: Optional[str],
    *,
    read_only_attaches: bool | None = None,
    private_attach_read_only: bool = False,
    shared_attach_read_only: bool = True,
    skip_private_attach: bool = False,
) -> None:
    """ATTACH bóveda privada y opcionalmente una segunda base como catálogo compartido.

    Por defecto el alias ``shared`` va en READ_ONLY. El alias ``private`` puede ir en RW
    cuando el worker tiene ``manifest.read_only: false`` (p. ej. Finanz + ``quant_core``).
    Si se pasa ``read_only_attaches`` (legado), se aplica el mismo modo a ambos ATTACH.
    """
    if read_only_attaches is not None:
        private_attach_read_only = bool(read_only_attaches)
        shared_attach_read_only = bool(read_only_attaches)
    ro_p = " (READ_ONLY)" if private_attach_read_only else ""
    ro_s = " (READ_ONLY)" if shared_attach_read_only else ""
    if not skip_private_attach:
        esc_p = _escape_attach_path(private_path)
        try:
            try:
                db.execute("DETACH private")
            except Exception:
                pass
            db.execute(f"ATTACH '{esc_p}' AS private{ro_p}")
        except Exception as exc:
            _log.debug("forge ATTACH private skipped: %s", exc)
    sp = (shared_path or "").strip()
    try:
        try:
            db.execute("DETACH shared")
        except Exception:
            pass
    except Exception:
        pass
    if not sp:
        return
    try:
        if Path(sp).resolve() == Path(private_path).resolve():
            return
    except Exception:
        if os.path.abspath(sp) == os.path.abspath(private_path):
            return
    Path(sp).parent.mkdir(parents=True, exist_ok=True)
    esc_s = _escape_attach_path(sp)
    try:
        db.execute(f"ATTACH '{esc_s}' AS shared{ro_s}")
    except Exception as exc:
        _log.warning("forge ATTACH shared failed (%s): %s", sp, exc)


def _bootstrap_shared_main_schema(db: Any, spec: WorkerSpec) -> None:
    """Replica declaraciones main.* de schema.sql en shared.main.* (MVP Leila / catálogo)."""
    if not getattr(spec, "forge_apply_schema_to_shared", False):
        return
    from duckclaw.workers.loader import _split_sql, load_schema_sql

    sql = load_schema_sql(spec)
    if not sql.strip():
        return
    adapted = sql.replace("CREATE TABLE IF NOT EXISTS main.", "CREATE TABLE IF NOT EXISTS shared.main.")
    for stmt in _split_sql(adapted):
        if stmt.strip():
            try:
                db.execute(stmt)
            except Exception as exc:
                _log.debug("forge shared schema stmt skipped: %s", exc)


def _infer_user_id_for_writer(db_path: str) -> str:
    parts = Path(db_path).expanduser().resolve().parts
    if "private" in parts:
        i = parts.index("private")
        if i + 1 < len(parts):
            return str(parts[i + 1])
    return "default"


def _get_db_path(worker_id: str, instance_name: Optional[str], base_path: Optional[str]) -> str:
    """Resolve DuckDB path for this worker instance."""
    base = (base_path or os.environ.get("DUCKDB_PATH") or get_gateway_db_path() or "").strip()
    if not base:
        base = str(Path.cwd() / "db" / "workers.duckdb")
    p = Path(base)
    # Multi-vault: si ya recibimos una ruta explícita a un archivo .duckdb (p. ej. db/private/<user>/x.duckdb),
    # respetarla tal cual y no reescribir a workers_<instance>.duckdb.
    if base_path and p.suffix.lower() == ".duckdb":
        p.parent.mkdir(parents=True, exist_ok=True)
        return str(p)
    if not p.suffix or p.suffix.lower() != ".duckdb":
        p = p / "workers.duckdb"
    # Optionally isolate per instance: db/workers_<instance>.duckdb
    if instance_name:
        p = p.parent / f"workers_{instance_name}.duckdb"
    p.parent.mkdir(parents=True, exist_ok=True)
    return str(p)


def _identity_fields(state: dict) -> dict:
    return {
        "chat_id": state.get("chat_id") or state.get("session_id"),
        "tenant_id": state.get("tenant_id") or "default",
        "user_id": state.get("user_id") or "",
        "username": (state.get("username") or "").strip(),
        "vault_db_path": state.get("vault_db_path") or "",
    }


def _normalized_context_pruning(spec: WorkerSpec) -> dict:
    raw = getattr(spec, "context_pruning_config", None)
    if not isinstance(raw, dict) or not raw.get("enabled"):
        return {}
    return {
        "enabled": True,
        "max_messages": max(2, int(raw.get("max_messages", 10))),
        "max_estimated_tokens": max(500, int(raw.get("max_estimated_tokens", 4000))),
        "keep_last_messages": max(1, int(raw.get("keep_last_messages", 3))),
        "tool_content_max_chars": max(500, int(raw.get("tool_content_max_chars", 8000))),
        "sandbox_heartbeat": bool(raw.get("sandbox_heartbeat", True)),
    }


def _compose_bi_system_prompt(base: str, analytical_summary: str) -> str:
    b = (base or "").strip()
    s = (analytical_summary or "").strip()
    if not s:
        return b
    return b + "\n\n## Resumen analítico del hilo\n" + s


def _estimate_tokens_from_messages(messages: list) -> int:
    total = 0
    for m in messages or []:
        c = getattr(m, "content", None) or ""
        if isinstance(c, str):
            total += len(c)
        elif isinstance(c, list):
            for part in c:
                if isinstance(part, dict) and part.get("type") == "text":
                    total += len(str(part.get("text", "")))
    return max(0, total // 4)


def _groq_max_estimated_input_tokens() -> int:
    """
    Tope estimado (chars/4) para el contenido serializado de mensajes hacia Groq.
    El límite efectivo del tier free/on_demand (~12k TPM por petición) incluye esquemas de tools;
    este tope debe quedar por debajo para no disparar 413.
    """
    raw = (os.environ.get("DUCKCLAW_GROQ_MAX_INPUT_TOKENS") or "").strip()
    if raw:
        try:
            return max(1500, min(int(raw), 11500))
        except ValueError:
            pass
    return 5000


def _groq_tool_message_max_chars() -> int:
    raw = (os.environ.get("DUCKCLAW_GROQ_TOOL_MESSAGE_MAX_CHARS") or "").strip()
    if raw:
        try:
            return max(400, min(int(raw), 100_000))
        except ValueError:
            pass
    return 3500


def _trim_messages_to_estimated_cap(
    messages: list[Any],
    *,
    cap: int,
    tool_cap: int,
    note_brand: str,
) -> list[Any]:
    """Recorta historial + tool output para no exceder ``cap`` tokens estimados (chars/4)."""
    from langchain_core.messages import AIMessage, SystemMessage, ToolMessage

    msgs = _truncate_tool_messages(list(messages), tool_cap)

    while len(msgs) > 2 and _estimate_tokens_from_messages(msgs) > cap:
        if isinstance(msgs[0], SystemMessage):
            if len(msgs) < 3:
                break
            victim = msgs.pop(1)
            if isinstance(victim, AIMessage) and getattr(victim, "tool_calls", None):
                while len(msgs) > 1 and isinstance(msgs[1], ToolMessage):
                    msgs.pop(1)
        else:
            msgs.pop(0)

    if msgs and isinstance(msgs[0], SystemMessage) and _estimate_tokens_from_messages(msgs) > cap:
        sys0 = msgs[0]
        c_raw = getattr(sys0, "content", "") or ""
        c = c_raw if isinstance(c_raw, str) else str(c_raw)
        if c:
            over_tok = _estimate_tokens_from_messages(msgs) - cap
            cut = min(len(c), over_tok * 4 + 400)
            tail = c[:-cut] if cut < len(c) else c[: max(3000, len(c) // 2)]
            note = (
                f"\n\n[{note_brand}: system prompt truncado por límite de contexto; "
                "prioriza reglas críticas y herramientas.]"
            )
            msgs = [SystemMessage(content=tail + note)] + list(msgs[1:])

    return msgs


def _apply_groq_message_budget(messages: list[Any], *, provider: str) -> list[Any]:
    """Recorta mensajes LangChain antes de invoke cuando el proveedor es Groq (evita 413 TPM)."""
    if (provider or "").strip().lower() != "groq" or not messages:
        return messages
    return _trim_messages_to_estimated_cap(
        messages,
        cap=_groq_max_estimated_input_tokens(),
        tool_cap=_groq_tool_message_max_chars(),
        note_brand="GROQ",
    )


def _mlx_max_estimated_input_tokens() -> int:
    """
    Tope estimado para MLX local (Metal VRAM). Prompts muy largos pueden tumbar mlx_lm con OOM;
    ver logs [METAL] Insufficient Memory.
    """
    raw = (os.environ.get("DUCKCLAW_MLX_MAX_INPUT_TOKENS") or "").strip()
    if raw:
        try:
            return max(2000, min(int(raw), 12000))
        except ValueError:
            pass
    return 7000


def _mlx_tool_message_max_chars() -> int:
    raw = (os.environ.get("DUCKCLAW_MLX_TOOL_MESSAGE_MAX_CHARS") or "").strip()
    if raw:
        try:
            return max(400, min(int(raw), 80_000))
        except ValueError:
            pass
    return 5000


def _apply_mlx_message_budget(messages: list[Any], *, provider: str) -> list[Any]:
    if (provider or "").strip().lower() not in ("mlx", "iotcorelabs") or not messages:
        return messages
    return _trim_messages_to_estimated_cap(
        messages,
        cap=_mlx_max_estimated_input_tokens(),
        tool_cap=_mlx_tool_message_max_chars(),
        note_brand="MLX",
    )


def _apply_provider_input_budget(messages: list[Any], *, provider: str) -> list[Any]:
    """Recorte de contexto por proveedor (Groq TPM / MLX VRAM)."""
    pl = (provider or "").strip().lower()
    m = messages
    if pl == "groq":
        m = _apply_groq_message_budget(m, provider=provider)
    elif pl in ("mlx", "iotcorelabs"):
        m = _apply_mlx_message_budget(m, provider=provider)
    return m


def _groq_tools_without_reddit_for_bind(tools: list[Any]) -> list[Any]:
    """
    Groq tier on_demand (~12k TPM por petición) cuenta mensajes + **definiciones de tools**.
    El MCP de Reddit registra muchas herramientas; en rutas genéricas (p. ej. presupuestos) no hacen falta
    y empujan el request por encima del límite. Las rutas forzadas Reddit siguen ligando el set completo.
    """
    return [t for t in (tools or []) if not str(getattr(t, "name", None) or "").startswith("reddit_")]


_REDDIT_SHARE_PATH_RE = re.compile(r"reddit\.com/r/[\w_]+/s/[a-zA-Z0-9]+", re.IGNORECASE)
_REDDIT_COMMENTS_IN_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?reddit\.com/r/[\w_]+/comments/[a-z0-9]+",
    re.IGNORECASE,
)
# post_id en la ruta (p. ej. 1skcbpd), no el slug /s/xxxx
_REDDIT_COMMENTS_SUB_POST_RE = re.compile(
    r"reddit\.com/r/([\w_]+)/comments/([a-z0-9]+)",
    re.IGNORECASE,
)


def _subreddit_and_post_id_from_reddit_comments_url(url: str) -> tuple[Optional[str], Optional[str]]:
    m = _REDDIT_COMMENTS_SUB_POST_RE.search(url or "")
    if not m:
        return None, None
    return m.group(1), m.group(2)


def _patch_reddit_get_post_args_from_canonical_url(resp: Any, canonical_comments_url: str) -> Any:
    """
    tool_choice fuerza reddit_get_post pero el modelo a veces pone el slug /s/... como post_id.
    Si ya resolvimos la URL canónica, sobrescribimos subreddit/post_id antes de tools_node.
    """
    sub, pid = _subreddit_and_post_id_from_reddit_comments_url(canonical_comments_url)
    if not sub or not pid or resp is None:
        return resp
    tcs = list(getattr(resp, "tool_calls", None) or [])
    if not tcs:
        return resp
    new_tcs: list[Any] = []
    patched_any = False
    for tc in tcs:
        if isinstance(tc, dict):
            name = tc.get("name")
            if name != "reddit_get_post":
                new_tcs.append(tc)
                continue
            args = dict(tc.get("args") or {})
            args["subreddit"] = sub
            args["post_id"] = pid
            new_tcs.append({**tc, "args": args})
            patched_any = True
            continue
        name = getattr(tc, "name", None)
        if name != "reddit_get_post":
            new_tcs.append(tc)
            continue
        base = getattr(tc, "args", None)
        args = dict(base) if isinstance(base, dict) else {}
        args["subreddit"] = sub
        args["post_id"] = pid
        try:
            new_tcs.append(tc.model_copy(update={"args": args}))
            patched_any = True
        except Exception:
            new_tcs.append(tc)
    if not patched_any:
        return resp
    try:
        return resp.model_copy(update={"tool_calls": new_tcs})
    except Exception:
        return resp


def _resolve_reddit_share_url_to_comments_url(url: str, *, timeout: float = 12.0) -> Optional[str]:
    """
    Sigue redirecciones HTTP de enlaces de compartir /r/<sub>/s/<slug> hasta la URL canónica
    .../comments/<post_id>/... para usar reddit_get_post. mcp-reddit suele fallar con
    reddit_search_reddit(query=<url>) (p. ej. error leyendo 'children').
    """
    raw = (url or "").strip()
    if not raw or not _REDDIT_SHARE_PATH_RE.search(raw):
        return None
    ua = (os.environ.get("REDDIT_USER_AGENT") or "duckclaw:share-resolve/0.1 (by duckclaw)").strip()
    try:
        req = _urllib_request.Request(raw, headers={"User-Agent": ua, "Accept": "text/html"})
        with _urllib_request.urlopen(req, timeout=timeout) as resp:
            final = resp.geturl()
        if not isinstance(final, str):
            return None
        final = final.split("#")[0].split("?")[0].rstrip("/")
        if not _REDDIT_COMMENTS_IN_URL_RE.search(final):
            return None
        if not final.lower().startswith("http"):
            final = f"https://{final}"
        return final
    except Exception:
        return None


def _extract_first_reddit_url(text: str) -> Optional[str]:
    if not text or not str(text).strip():
        return None
    m = re.search(r"https?://(?:www\.)?reddit\.com/[^\s)>\]\"']+", str(text), re.IGNORECASE)
    if m:
        u = m.group(0)
        while u and u[-1] in ".,);":
            u = u[:-1]
        return u or None
    m2 = re.search(r"https?://redd\.it/[a-zA-Z0-9]+", str(text), re.IGNORECASE)
    return m2.group(0) if m2 else None


def _finanz_followup_reddit_read_intent(text: str) -> bool:
    t = (text or "").lower()
    if "reddit" not in t and "redd.it" not in t:
        return False
    return any(
        k in t
        for k in (
            "leer",
            "lee",
            "read",
            "post",
            "hilo",
            "thread",
            "enlace",
            "link",
            "url",
            "muestra",
            "mostrar",
            "ver ",
            "contenido",
            "abrir",
        )
    )


def _most_recent_reddit_url_in_human_messages(messages: list[Any]) -> Optional[str]:
    from langchain_core.messages import HumanMessage

    from duckclaw.integrations.llm_providers import lc_message_content_to_text

    for m in reversed(messages or []):
        if not isinstance(m, HumanMessage):
            continue
        txt = lc_message_content_to_text(m)
        u = _extract_first_reddit_url(txt)
        if u:
            return u
    return None


def _agent_node_llm_failure_user_message(exc: BaseException, *, provider: str) -> str:
    """Mensaje Telegram cuando falla invoke del LLM en agent_node (sin culpar a MLX si el proveedor es Groq)."""
    pl = (provider or "").strip().lower()
    raw = str(exc)
    low = raw.lower()
    mlx_hint = (
        "No pude completar la inferencia: el motor local (p. ej. MLX) no respondió o se reinició, "
        "a veces por **falta de memoria GPU**. Revisa `pm2 logs MLX-Inference`.\n\n"
        "Si el fallo fue tras `/context --summary`, prueba bajar el volcado con la variable "
        "`DUCKCLAW_SEMANTIC_SUMMARY_MAX_CHARS` (p. ej. 6000) o desactiva la segunda pasada de síntesis "
        "con `DUCKCLAW_DISABLE_NL_REPLY_SYNTHESIS=1`."
    )
    groq_tokens_hint = (
        "No pude completar la inferencia con **Groq**: el envío supera el límite de tokens de tu plan "
        "(p. ej. ~12k TPM en tier on_demand). El gateway ya omite herramientas **reddit_*** en rutas "
        "genéricas con Groq para ahorrar esquema; si sigue fallando, prueba:\n"
        "- `DUCKCLAW_GROQ_MAX_INPUT_TOKENS` más bajo y/o `DUCKCLAW_GROQ_TOOL_MESSAGE_MAX_CHARS` más bajo\n"
        "- Acortar el historial del chat o subir tier en console.groq.com\n"
        "- `DUCKCLAW_DISABLE_NL_REPLY_SYNTHESIS=1` si ocurre tras muchas herramientas."
    )
    is_groq_size_or_tpm = (
        "413" in raw
        or "rate_limit_exceeded" in low
        or "tokens per minute" in low
        or "request too large" in low
        or "too large for model" in low
    )
    if pl == "groq" and is_groq_size_or_tpm:
        return groq_tokens_hint
    if pl == "groq":
        return (
            "No pude completar la inferencia con **Groq**. Revisa API key y cuotas. "
            "Detalle: "
            + raw[:380]
            + ("…" if len(raw) > 380 else "")
        )
    if pl == "deepseek":
        return (
            "No pude completar la inferencia con **DeepSeek**. Revisa `DEEPSEEK_API_KEY`, red y cuotas; "
            "el fallo no es el servidor MLX local.\n\n"
            f"Detalle: {raw[:380]}"
            + ("…" if len(raw) > 380 else "")
        )
    if pl == "openai":
        return (
            "No pude completar la inferencia con **OpenAI** (API compatible). Revisa `OPENAI_API_KEY` y red.\n\n"
            f"Detalle: {raw[:380]}"
            + ("…" if len(raw) > 380 else "")
        )
    if pl in ("mlx", "iotcorelabs"):
        return mlx_hint
    return (
        "No pude completar la inferencia con el proveedor LLM configurado. Detalle: "
        + raw[:380]
        + ("…" if len(raw) > 380 else "")
    )


def _compact_run_sandbox_tool_content_for_llm(content: str, max_chars: int) -> str:
    """
    El JSON de run_sandbox incluye figure_base64 (cientos de KB). Para el LLM se omite ese campo
    y se acorta el resto; el PNG real vive en state['sandbox_photo_base64'] (tools_node).
    """
    c = content or ""
    s = c.strip()
    if not s.startswith("{"):
        return c if len(c) <= max_chars else c[:max_chars] + "\n…[truncado por tamaño]"
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        return c if len(c) <= max_chars else c[:max_chars] + "\n…[truncado por tamaño]"
    if not isinstance(data, dict):
        return c[:max_chars] + "\n…[truncado por tamaño]"
    if data.get("figure_base64"):
        # Quitar del JSON para el LLM; el PNG real sigue en state['sandbox_photo_base64'] (tools_node).
        data.pop("figure_base64", None)
    for key in ("output", "stdout", "stderr"):
        if key in data and isinstance(data[key], str) and len(data[key]) > 4000:
            data[key] = data[key][:4000] + "…[truncado]"
    compact = json.dumps(data, ensure_ascii=False)
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars] + "\n…[truncado por tamaño]"


def _truncate_tool_messages(messages: list, max_chars: int) -> list:
    from langchain_core.messages import ToolMessage
    from duckclaw.utils.formatters import format_reddit_mcp_reply_if_applicable

    out = []
    for m in messages or []:
        if isinstance(m, ToolMessage) and max_chars > 0:
            c = m.content
            if not isinstance(c, str):
                out.append(m)
                continue
            name = getattr(m, "name", "") or ""
            orig_c = c
            if name.startswith("reddit_"):
                c = format_reddit_mcp_reply_if_applicable(c)
            if name in ("run_sandbox", "run_browser_sandbox", "pqrsd_run_identificacion_step1"):
                compacted = _compact_run_sandbox_tool_content_for_llm(c, max_chars)
                out.append(
                    ToolMessage(
                        content=compacted,
                        tool_call_id=m.tool_call_id,
                        name=name,
                    )
                )
            elif len(c) > max_chars:
                out.append(
                    ToolMessage(
                        content=c[:max_chars] + "\n…[truncado por tamaño]",
                        tool_call_id=m.tool_call_id,
                        name=name,
                    )
                )
            elif c != orig_c:
                out.append(
                    ToolMessage(
                        content=c,
                        tool_call_id=m.tool_call_id,
                        name=name,
                    )
                )
            else:
                out.append(m)
        else:
            out.append(m)
    return out


def _serialize_messages_for_summary(messages: list) -> str:
    lines: list[str] = []
    for m in messages or []:
        c = getattr(m, "content", None) or ""
        if not isinstance(c, str):
            c = str(c)
        c = c[:6000]
        name = type(m).__name__
        if name == "HumanMessage":
            lines.append("user: " + c)
        elif name == "AIMessage":
            lines.append("assistant: " + c)
        elif name == "ToolMessage":
            tn = getattr(m, "name", "") or "tool"
            lines.append(f"tool_{tn}: " + c[:4000])
    return "\n".join(lines)


def _split_for_pruning(non_system: list, keep_last: int) -> tuple[list, list]:
    """Divide non-system messages en cabeza (a resumir) y cola estable (preserva ToolMessage tras AI)."""
    from langchain_core.messages import AIMessage, ToolMessage

    if keep_last < 1:
        keep_last = 1
    if len(non_system) <= keep_last:
        return [], non_system[:]
    s = len(non_system) - keep_last
    while s > 0 and isinstance(non_system[s], ToolMessage):
        s -= 1
    tail = non_system[s:]
    if tail and isinstance(tail[-1], AIMessage):
        last_ai = tail[-1]
        if getattr(last_ai, "tool_calls", None):
            e = len(non_system)
            t_end = s + len(tail)
            while t_end < e and isinstance(non_system[t_end], ToolMessage):
                t_end += 1
            tail = non_system[s:t_end]
    head = non_system[:s]
    return head, tail


def _llm_fold_conversation_summary(llm: Any, head_msgs: list, prior: str) -> str:
    from langchain_core.messages import HumanMessage, SystemMessage

    blob = _serialize_messages_for_summary(head_msgs)
    sys = (
        "Eres un asistente de compresión de contexto para un analista BI. "
        "Produce un resumen analítico breve en español: consultas y decisiones, hallazgos numéricos, errores. "
        "Sin saludos. Máximo ~800 palabras."
    )
    human = (
        "Resumen previo del hilo (puede estar vacío):\n"
        + (prior or "")
        + "\n\n---\nTranscript a compactar:\n"
        + blob
    )
    try:
        r = llm.invoke([SystemMessage(content=sys), HumanMessage(content=human)])
        return (str(getattr(r, "content", None) or "") or "").strip()[:12000]
    except Exception as exc:
        _log.warning("context pruning summary LLM failed: %s", exc)
        return ((prior or "").strip() + "\n[Error al generar resumen; contexto truncado.]").strip()


def _sandbox_heartbeat_allowed(spec: WorkerSpec) -> bool:
    cp = _normalized_context_pruning(spec)
    if not cp.get("sandbox_heartbeat"):
        return False
    v = (os.getenv("DUCKCLAW_SANDBOX_HEARTBEAT", "true").strip().lower())
    if v in ("0", "false", "no", "off"):
        return False
    return bool((os.getenv("N8N_OUTBOUND_WEBHOOK_URL") or "").strip()) or bool(
        effective_telegram_bot_token_outbound()
    )


def _heartbeat_elapsed_sec(state: dict) -> float | None:
    t0 = state.get("subagent_turn_started_monotonic")
    if not isinstance(t0, (int, float)):
        return None
    return max(0.0, time.monotonic() - float(t0))


def _send_sandbox_heartbeat_telegram(state: dict) -> None:
    from duckclaw.graphs.chat_heartbeat import format_tool_heartbeat, normalize_telegram_chat_id_for_outbound

    cid_raw = str(state.get("chat_id") or state.get("session_id") or "").strip()
    cid = normalize_telegram_chat_id_for_outbound(cid_raw) or cid_raw
    uid = str(state.get("user_id") or "").strip() or cid
    if not cid:
        return
    _hb = (state.get("subagent_instance_label") or "").strip() or None
    _pt = (state.get("heartbeat_plan_title") or "").strip() or None
    text = format_tool_heartbeat(
        _hb,
        "📊 Estoy procesando los datos y generando tus gráficos. "
        "Esto puede tomar unos segundos...",
        plan_title=_pt,
        elapsed_sec=_heartbeat_elapsed_sec(state),
    )
    token = effective_telegram_bot_token_outbound()
    if token:
        try:
            from duckclaw.integrations.telegram.telegram_outbound_sync import (
                send_long_plain_text_markdown_v2_chunks_sync,
            )

            n = send_long_plain_text_markdown_v2_chunks_sync(
                bot_token=token,
                chat_id=cid,
                plain_text=text,
                log=_log,
            )
            if n > 0:
                _log.info("sandbox heartbeat: nativo OK chat_id=%r", cid)
                return
        except Exception as exc:
            _log.debug("sandbox heartbeat nativo falló: %s", exc)

    url = (os.getenv("N8N_OUTBOUND_WEBHOOK_URL") or "").strip()
    if not url:
        _log.debug("sandbox heartbeat: sin token ni N8N_OUTBOUND_WEBHOOK_URL")
        return
    auth = (os.getenv("N8N_AUTH_KEY") or "").strip()
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["X-DuckClaw-Secret"] = auth
    payload = json.dumps(
        {
            "chat_id": cid,
            "user_id": uid,
                "text": llm_markdown_to_telegram_html(text),
            "parse_mode": "HTML",
        },
        ensure_ascii=False,
    ).encode("utf-8")
    req = _urllib_request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with _urllib_request.urlopen(req, timeout=10) as resp:
            _ = resp.read()
        _log.info("sandbox heartbeat: webhook OK chat_id=%r", cid)
    except URLError as exc:
        _log.debug("sandbox heartbeat webhook failed: %s", exc)
    except Exception as exc:
        _log.debug("sandbox heartbeat error: %s", exc)


def _novnc_pre_dm_always_enabled() -> bool:
    v = (os.getenv("DUCKCLAW_BROWSER_NOVNC_PRE_DM") or "").strip().lower()
    return v in ("1", "true", "yes", "on", "always")


def _send_novnc_pre_dm_fallback(
    state: dict,
    vnc_url: str,
    *,
    routing_worker_id: str,
    novnc_session_id: str = "",
) -> None:
    """DM corto con enlace si heartbeat de chat está off y ``DUCKCLAW_BROWSER_NOVNC_PRE_DM=always``."""
    import threading

    from duckclaw.graphs.chat_heartbeat import (
        _resolve_heartbeat_outbound_bot_token,
        normalize_telegram_chat_id_for_outbound,
    )
    from duckclaw.graphs import novnc_registry as nr  # noqa: PLC0415
    from duckclaw.integrations.telegram.telegram_outbound_sync import (
        send_long_plain_text_markdown_v2_chunks_sync,
    )

    cid_raw = str(state.get("chat_id") or state.get("session_id") or "").strip()
    cid = normalize_telegram_chat_id_for_outbound(cid_raw) or cid_raw
    if not cid or not vnc_url:
        return
    _ns = (novnc_session_id or "").strip()
    if _ns and not nr.consume_initial_vnc_telegram_link(_ns):
        return
    tok_ex = (state.get("outbound_telegram_bot_token") or "").strip() or None
    token = _resolve_heartbeat_outbound_bot_token(
        tok_ex,
        (routing_worker_id or "").strip() or None,
    )
    if not token:
        _log.debug("novnc pre-dm: sin token Bot API")
        return
    plain = (
        "🖥️ NoVNC (sandbox browser)\n\n"
        f"{vnc_url}\n\n"
        "🌐 El agente ejecutará la automatización en el sandbox."
    )

    def _run() -> None:
        try:
            n = send_long_plain_text_markdown_v2_chunks_sync(
                bot_token=token,
                chat_id=cid,
                plain_text=plain,
                log=_log,
            )
            if n > 0:
                _log.info("novnc pre-dm fallback: nativo OK chat_id=%r", cid)
        except Exception as exc:
            _log.debug("novnc pre-dm fallback failed: %s", exc)

    threading.Thread(target=_run, name="duckclaw-novnc-pre-dm", daemon=True).start()


def _schedule_run_browser_novnc_tool_heartbeat(
    state: dict,
    *,
    routing_worker_id: str,
    vnc_url: str | None,
    novnc_session_id: str = "",
) -> None:
    from duckclaw.graphs import novnc_registry as nr  # noqa: PLC0415
    from duckclaw.graphs.chat_heartbeat import (
        format_tool_heartbeat,
        heartbeat_message_for_tool,
        is_chat_heartbeat_enabled,
        schedule_chat_heartbeat_dm,
    )

    _hb_head = (state.get("subagent_instance_label") or "").strip() or None
    _hb_uname = (state.get("username") or "").strip() or None
    _hb_plan = (state.get("heartbeat_plan_title") or "").strip() or None
    _hb_tok = (state.get("outbound_telegram_bot_token") or "").strip() or None
    _htid = (state.get("tenant_id") or "default").strip() or "default"
    _hcid = str(state.get("chat_id") or state.get("session_id") or "").strip()
    _huid = str(state.get("user_id") or "").strip() or _hcid

    _ns = (novnc_session_id or "").strip()
    _hb_on = is_chat_heartbeat_enabled(_htid, _hcid)

    if vnc_url:
        if _hb_on:
            _include_link = nr.consume_initial_vnc_telegram_link(_ns) if _ns else True
            if _include_link:
                body = (
                    "🖥️ Enlace noVNC (pantalla del navegador en vivo):\n"
                    f"{vnc_url}\n\n"
                    "🌐 El agente ejecutará ahora la automatización en el sandbox; puedes seguirla en este enlace."
                )
            else:
                body = (
                    "🌐 Automatización del sandbox en curso. "
                    "El enlace noVNC ya se envió al inicio de esta sesión; si lo necesitas otra vez, "
                    "pide «enlace noVNC» o usa la herramienta get_browser_session_url."
                )
        else:
            body = heartbeat_message_for_tool("run_browser_sandbox")
    else:
        body = heartbeat_message_for_tool("run_browser_sandbox")

    _elapsed = _heartbeat_elapsed_sec(state)
    text = format_tool_heartbeat(
        _hb_head,
        body,
        plan_title=_hb_plan,
        elapsed_sec=_elapsed,
    )

    if _hb_on:
        schedule_chat_heartbeat_dm(
            _htid,
            _hcid,
            _huid,
            text,
            log_worker_id=_hb_head,
            log_username=_hb_uname,
            log_plan_title=_hb_plan,
            outbound_bot_token=_hb_tok,
            routing_worker_id=routing_worker_id,
        )
    elif vnc_url and _novnc_pre_dm_always_enabled():
        _send_novnc_pre_dm_fallback(
            state,
            vnc_url,
            routing_worker_id=routing_worker_id,
            novnc_session_id=_ns,
        )


def _sync_finanz_lake_beliefs(db: Any, spec: WorkerSpec) -> None:
    """Actualiza observed_value de creencias lake_* según env (Capadonna SSH)."""
    _lid = (getattr(spec, "logical_worker_id", None) or spec.worker_id or "").strip().lower()
    if _lid != "finanz":
        return
    _qcfg = getattr(spec, "quant_config", None)
    if not isinstance(_qcfg, dict) or not _qcfg.get("enabled"):
        return
    try:
        from duckclaw.forge.skills.quant_market_bridge import lake_belief_observed_values

        host_v, online_v = lake_belief_observed_values()
    except Exception:
        _log.debug("lake_belief_observed_values failed", exc_info=True)
        return
    schema = "".join(c if c.isalnum() or c == "_" else "_" for c in (spec.schema_name or "").strip())
    if not schema:
        return
    for key, val in (
        ("lake_host_configured", host_v),
        ("lake_status_online", online_v),
    ):
        try:
            db.execute(
                f"""
                INSERT INTO {schema}.agent_beliefs (
                    belief_key, target_value, observed_value, threshold, belief_kind
                )
                VALUES ('{key}', 1.0, {val}, 0.0, 'numeric')
                ON CONFLICT (belief_key) DO UPDATE SET
                    observed_value = excluded.observed_value,
                    last_updated = CURRENT_TIMESTAMP
                """
            )
        except Exception:
            _log.debug("sync lake belief %s skipped", key, exc_info=True)


def _ensure_worker_duckdb_extensions(db: Any, spec: WorkerSpec) -> None:
    """INSTALL/LOAD extensiones declaradas en manifest (p. ej. httpfs + json para APIs remotas)."""
    exts = getattr(spec, "duckdb_extensions", None) or []
    if not exts:
        return
    for raw in exts:
        ext = str(raw).strip().lower()
        if not ext or not re.match(r"^[a-z][a-z0-9_]*$", ext):
            continue
        try:
            db.execute(f"INSTALL {ext};")
        except Exception:
            pass
        try:
            db.execute(f"LOAD {ext};")
        except Exception:
            pass


def _build_worker_tools(db: Any, spec: WorkerSpec) -> list:
    """Build tool list: template skills + read/admin SQL (with allow-list)."""
    from langchain_core.tools import StructuredTool

    tools = load_skills(spec, db)
    schema = spec.schema_name

    # TimeContextSkill: si el manifest declara get_current_time o time_context, añadir la tool
    skills_list = getattr(spec, "skills_list", None) or []
    if "get_current_time" in skills_list or "time_context" in skills_list:
        try:
            from duckclaw.forge.skills.time_context import get_current_time
            tools.append(get_current_time)
        except Exception:
            pass

    def _enforce_allowed_tables(q_upper: str) -> Optional[json]:
        """Allow-list validation for queries touching DB tables."""
        if not spec.allowed_tables:
            return None
        # Permitir siempre information_schema (SHOW TABLES, esquema, etc.)
        if "INFORMATION_SCHEMA" in q_upper or "SHOW TABLES" in q_upper or "SHOW " in q_upper:
            return None
        for t in spec.allowed_tables:
            t_str = str(t)
            if t_str.upper() in q_upper or f"{schema}.{t_str}".upper() in q_upper:
                return None
        # No allowed table mentioned; check if query likely touches tables.
        if any(k in q_upper for k in ("FROM", "INTO", "UPDATE", "DELETE", "JOIN", "TABLE")):
            return json.dumps({"error": f"Solo se permiten las tablas: {', '.join(spec.allowed_tables)}."})
        return None

    def _qualify_allowed_tables(query: str, schema_name: str) -> str:
        """
        Prefix allowed table names with schema when unqualified.
        Example: FROM the_mind_games -> FROM main.the_mind_games
        """
        if not spec.allowed_tables:
            return query
        out = query
        for table in spec.allowed_tables:
            if "." in str(table):
                continue
            escaped = re.escape(table)
            # Replace only unqualified names (not already schema.table)
            out = re.sub(rf"(?<!\.)\b{escaped}\b", f"{schema_name}.{table}", out, flags=re.IGNORECASE)
        return out

    def _read_sql_worker(query: str) -> str:
        return read_pool.run_worker_read_sql(lambda qq: db.query(qq), spec, query)

    _read_sql_worker = log_tool_execution_sync(name="read_sql")(_read_sql_worker)

    tools.append(
        StructuredTool.from_function(
            _read_sql_worker,
            name="read_sql",
            description="Solo lectura SQL. SELECT/WITH/SHOW/DESCRIBE/EXPLAIN/PRAGMA. Restringe a tablas permitidas del worker.",
        )
    )

    def _admin_sql_worker(query: str) -> str:
        if not query or not query.strip():
            return json.dumps({"error": "Query vacío."})
        q = query.strip()
        upper = q.upper()

        allowed_tables_error = _enforce_allowed_tables(upper)
        if allowed_tables_error:
            return allowed_tables_error

        # Respetar read_only del worker para operaciones destructivas/escrituras.
        if spec.read_only and any(
            kw in upper
            for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE")
        ):
            return json.dumps({"error": "Este trabajador es solo lectura. No se permiten escrituras."})

        try:
            # Para cualquier query de lectura, usar query()
            if upper.startswith(("SELECT", "WITH", "SHOW", "DESCRIBE", "EXPLAIN", "PRAGMA")):
                return db.query(q)

            # Escrituras: cola singleton (workers RO) o ejecución en proceso (workers RW).
            db_path_str = str(getattr(db, "_path", "") or "").strip()
            if not db_path_str:
                return json.dumps({"error": "Sin ruta de base de datos para encolar escritura."})
            ro = bool(getattr(db, "_read_only", False))
            # Worker RW: este proceso ya mantiene ``duckdb.connect(..., read_only=False)`` al archivo.
            # Encolar un segundo RW en db-writer falla con lock en el mismo PID (gateway); ver logs db-writer.
            # Alineado con ``insert_transaction``: mutar en el handle actual.
            if not ro and db_path_str != ":memory:":
                try:
                    db.execute(q)
                    return json.dumps({"status": "success"})
                except Exception as e:
                    return json.dumps({"error": str(e)})

            released_ro = False
            st = None
            try:
                # DuckDB: un handle RO en el gateway puede impedir que db-writer tome lock RW;
                # suspender antes de encolar.
                if ro and db_path_str != ":memory:":
                    susp = getattr(db, "suspend_readonly_file_handle", None)
                    resu = getattr(db, "resume_readonly_file_handle", None)
                    if callable(susp) and callable(resu):
                        susp()
                        released_ro = True
                resolved = str(Path(db_path_str).expanduser().resolve())
                uid = _infer_user_id_for_writer(resolved)
                task_id = enqueue_duckdb_write_sync(
                    db_path=resolved,
                    query=q,
                    user_id=uid,
                    tenant_id="default",
                )
                _poll = 15.0 if released_ro else 3.0
                st = poll_task_status_sync(task_id, timeout_sec=_poll)
            except Exception as e:
                return json.dumps({"error": str(e)})
            finally:
                if released_ro:
                    try:
                        resu = getattr(db, "resume_readonly_file_handle", None)
                        if callable(resu):
                            resu()
                    except Exception:
                        pass
            if st is not None and st.status == "success":
                return json.dumps({"status": "success"})
            if st is not None and st.status == "failed":
                return json.dumps({"status": "failed", "detail": st.detail or "writer failed"})
            return json.dumps({"status": "enqueued_pending_confirmation"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    if not spec.read_only:
        tools.append(
            StructuredTool.from_function(
                _admin_sql_worker,
                name="admin_sql",
                description="SQL con permisos admin: lectura + escrituras (INSERT/UPDATE/DELETE/CREATE/ALTER/DROP si el worker no es read_only). Respeta allow-list de tablas del worker si aplica.",
            )
        )

    def _inspect_schema_worker() -> str:
        """Lista tablas de todos los esquemas (main, finance_worker, etc.)."""
        return read_pool.run_inspect_schema_worker(lambda qq: db.query(qq))

    tools.append(
        StructuredTool.from_function(
            _inspect_schema_worker,
            name="inspect_schema",
            description="Lista las tablas disponibles en la base de datos. Usar para preguntas sobre tablas, esquema o estructura.",
        )
    )

    from duckclaw.graphs.tools import get_db_path as _get_db_path_tool

    def _get_db_path_worker() -> str:
        return _get_db_path_tool(db)

    tools.append(
        StructuredTool.from_function(
            _get_db_path_worker,
            name="get_db_path",
            description="Devuelve la ruta o nombre del archivo .duckdb al que tiene acceso el agente. Usar cuando pregunten por el nombre de la base de datos.",
        )
    )
    return tools


def filter_tools_for_sandbox(tools: list[Any], enabled: bool) -> list[Any]:
    """
    Helper (unit-testable): si sandbox está OFF, elimina `run_sandbox`, `run_browser_sandbox` y `get_browser_session_url`.
    """
    if enabled:
        return list(tools)
    deny = {"run_sandbox", "run_browser_sandbox", "get_browser_session_url", "pqrsd_run_identificacion_step1"}
    return [t for t in tools if getattr(t, "name", "") not in deny]


class WorkerFactory:
    """Factory for Virtual Workers (template-based LangGraph agents)."""

    def __init__(self, templates_root: Optional[Path] = None):
        self.templates_root = templates_root

    def create(
        self,
        worker_id: str,
        db_path: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        instance_name: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        shared_db_path: Optional[str] = None,
    ) -> Any:
        """
        Build and return a compiled LangGraph for the worker.
        Shim: delega a build_worker_graph (compatible con AgentAssembler).
        """
        return build_worker_graph(
            worker_id,
            db_path,
            None,
            templates_root=self.templates_root,
            instance_name=instance_name,
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            shared_db_path=shared_db_path,
            tool_surface="full",
        )


def build_worker_graph(
    worker_id: str,
    db_path: Optional[str],
    llm: Optional[Any],
    *,
    templates_root: Optional[Path] = None,
    instance_name: Optional[str] = None,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    shared_db_path: Optional[str] = None,
    reuse_db: Any | None = None,
    tool_surface: Literal["full", "context_synthesis"] = "full",
) -> Any:
    """
    Build a compiled LangGraph for a worker. Used by AgentAssembler._build_worker
    and by WorkerFactory.create() (shim).

    Si ``reuse_db`` apunta al mismo archivo que ``path``, **no** está en solo lectura,
    y el worker **no** necesita catálogo ``shared`` (``shared_resolved`` vacío), reutiliza
    esa conexión y omite ATTACH del privado para no duplicar handles. Si ``reuse_db`` es RO
    (manager/gateway típico) **no** reutilizar: abrir ``DuckClaw(path, read_only=spec.read_only)``
    para que workers con ``read_only: false`` puedan INSERT en quant_core.*.
    Si hace falta ``shared``, se abre otra conexión para no pisar el estado ATTACH entre
    workers distintos en caché.

    ``tool_surface=context_synthesis``: turnos con directivas ``SUMMARIZE_*`` del gateway;
    omite bridges MCP stdio pesados (GitHub, Google Trends) para reducir cold start.
    **Reddit** sí se registra si el manifest lo declara: URLs ``/r/.../s/...`` en
    ``SUMMARIZE_NEW_CONTEXT`` deben poder usar ``reddit_get_post`` / ``reddit_search_reddit``.
    """
    spec = load_manifest(worker_id, templates_root)
    path = _get_db_path(worker_id, instance_name, db_path)
    shared_resolved = _resolve_shared_db_path(spec, shared_db_path)

    from duckclaw import DuckClaw

    reuse_path = ""
    if reuse_db is not None:
        reuse_path = str(getattr(reuse_db, "_path", "") or "").strip()
    reuse_read_only = bool(getattr(reuse_db, "_read_only", False)) if reuse_db is not None else False
    skip_private = bool(
        reuse_db is not None
        and reuse_path
        and _same_duckdb_file(reuse_path, path)
        and not (shared_resolved or "").strip()
        and not reuse_read_only
    )
    if skip_private:
        db = reuse_db
        _log.debug("build_worker_graph: reuse DuckClaw (same file, no shared, skip private ATTACH) path=%s", path)
    else:
        # Manifest ``read_only: false`` (p. ej. Finanz): conexión RW para INSERT en quant_core.* / señales.
        db = DuckClaw(path, read_only=bool(spec.read_only))
    _apply_forge_attaches(
        db,
        path,
        shared_resolved,
        private_attach_read_only=bool(spec.read_only),
        shared_attach_read_only=True,
        skip_private_attach=skip_private,
    )

    system_prompt = load_system_prompt(spec)
    tools = _build_worker_tools(db, spec)
    if tool_surface == "full":
        if getattr(spec, "github_config", None):
            try:
                from duckclaw.forge.skills.github_bridge import register_github_skill

                lw = (getattr(spec, "logical_worker_id", None) or spec.worker_id or "").strip()
                register_github_skill(
                    tools,
                    spec.github_config,
                    logical_worker_id=lw,
                    manifest_worker_slug=str(spec.worker_id or "").strip(),
                )
            except Exception:
                pass
        if getattr(spec, "google_trends_config", None) is not None:
            try:
                from duckclaw.forge.skills.google_trends_bridge import register_google_trends_skill

                register_google_trends_skill(tools, spec.google_trends_config)
            except Exception:
                pass
    # Reddit: necesario en SUMMARIZE_NEW_CONTEXT con URL /r/.../s/... (spec Context Injection).
    if getattr(spec, "reddit_config", None) and tool_surface in ("full", "context_synthesis"):
        try:
            from duckclaw.forge.skills.reddit_bridge import register_reddit_skill

            register_reddit_skill(tools, spec.reddit_config)
        except Exception:
            pass
    tools_by_name = {t.name: t for t in tools}

    # Inferencia Elástica (Hardware-Aware): si el manifest tiene inference y no se pasó provider/model/base_url explícito, detectar hardware
    inference_config = getattr(spec, "inference_config", None)
    if inference_config is not None and not llm_provider and not llm_model and not llm_base_url:
        try:
            from duckclaw.integrations.hardware_detector import (
                get_inference_config,
                resolve_llm_params_from_config,
            )
            config = get_inference_config(inference_config)
            provider, model, base_url = resolve_llm_params_from_config(config)
            provider = (provider or "none_llm").strip().lower()
            model = (model or "").strip()
            base_url = (base_url or "").strip()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Hardware detection failed or fallback disabled: %s", e)
            provider = "none_llm"
            model = ""
            base_url = ""
    else:
        provider = (llm_provider or os.environ.get("DUCKCLAW_LLM_PROVIDER") or "none_llm").strip().lower()
        model = (llm_model or os.environ.get("DUCKCLAW_LLM_MODEL") or "").strip()
        base_url = (llm_base_url or os.environ.get("DUCKCLAW_LLM_BASE_URL") or "").strip()

    if llm is None and provider != "none_llm":
        from duckclaw.integrations.llm_providers import build_llm
        llm = build_llm(provider, model, base_url)
    elif llm is None:
        llm = None

    if llm is not None:
        from duckclaw.integrations.llm_providers import reconcile_worker_provider_label

        provider = reconcile_worker_provider_label(llm, provider, llm_provider)

    llm_fallback: Any | None = None
    if llm is not None:
        try:
            from duckclaw.integrations.llm_providers import build_llm_fallback_from_env

            llm_fallback = build_llm_fallback_from_env()
        except Exception as _fb_exc:
            _log.debug("LLM fallback skipped: %s", _fb_exc)

    _logical_id_early = (getattr(spec, "logical_worker_id", None) or spec.worker_id or "").strip()
    _cp_early = _normalized_context_pruning(spec)
    llm_summary: Any = None
    if llm is not None and _cp_early.get("enabled") and _logical_id_early == "bi_analyst":
        from duckclaw.integrations.llm_providers import build_llm as _build_llm_sum

        sp = (os.getenv("DUCKCLAW_SUMMARY_LLM_PROVIDER") or "").strip() or provider
        sm = (os.getenv("DUCKCLAW_SUMMARY_LLM_MODEL") or "").strip() or model
        su = (os.getenv("DUCKCLAW_SUMMARY_LLM_BASE_URL") or "").strip() or base_url
        try:
            if (sp or "").lower() != "none_llm":
                llm_summary = _build_llm_sum(sp, sm, su)
        except Exception as exc:
            _log.warning("summary LLM build failed, using primary: %s", exc)
        if llm_summary is None:
            llm_summary = llm

    if getattr(spec, "research_config", None):
        try:
            from duckclaw.forge.skills.research_bridge import register_research_skill
            register_research_skill(tools, spec.research_config, llm=llm)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            pass

    if getattr(spec, "openweather_config", None) is not None:
        try:
            from duckclaw.forge.skills.openweather_bridge import register_openweather_skill

            register_openweather_skill(tools, spec.openweather_config, getattr(spec, "research_config", None))
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            pass

    if getattr(spec, "tailscale_config", None):
        try:
            from duckclaw.forge.skills.tailscale_bridge import register_tailscale_skill
            register_tailscale_skill(tools, spec.tailscale_config)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            pass

    if getattr(spec, "ibkr_config", None) is not None:
        try:
            from duckclaw.forge.skills.ibkr_bridge import register_ibkr_skill
            register_ibkr_skill(tools, spec.ibkr_config)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            pass

    if getattr(spec, "fmp_config", None) is not None:
        try:
            from duckclaw.forge.skills.fmp_bridge import register_fmp_skill

            register_fmp_skill(tools, spec.fmp_config)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            pass

    _qcfg = getattr(spec, "quant_config", None)
    _lid_q = (getattr(spec, "logical_worker_id", None) or spec.worker_id or "").strip().lower()
    if isinstance(_qcfg, dict) and _qcfg.get("enabled") and _lid_q == "finanz":
        try:
            from duckclaw.forge.skills.quant_market_bridge import register_quant_market_skill
            from duckclaw.forge.skills.quant_trade_bridge import register_quant_trade_skills

            register_quant_market_skill(db, tools, spec)
            register_quant_trade_skills(db, spec, tools)
            if _qcfg.get("cfd"):
                from duckclaw.forge.skills.quant_cfd_bridge import register_quant_cfd_skill

                register_quant_cfd_skill(db, spec, tools)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            _log.debug("quant skills registration skipped", exc_info=True)
    elif isinstance(_qcfg, dict) and _qcfg.get("enabled") and _lid_q == "quant_trader" and llm is not None:
        try:
            from duckclaw.forge.skills.quant_trader_bridge import register_quant_trader_skills

            register_quant_trader_skills(db, llm, tools)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            _log.debug("quant_trader skills registration skipped", exc_info=True)

    if getattr(spec, "sft_config", None):
        try:
            from duckclaw.forge.skills.sft_bridge import register_sft_skill
            register_sft_skill(tools, spec.sft_config)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            pass

    if getattr(spec, "homeostasis_config", None):
        try:
            from duckclaw.forge.skills.homeostasis_bridge import register_homeostasis_skill
            register_homeostasis_skill(tools, spec, db, tools_by_name)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            pass

    # Strix Sandbox: `run_sandbox` si hay security_policy.yaml; `run_browser_sandbox` si browser_sandbox en manifest.
    try:
        security_policy_path = spec.worker_dir / "security_policy.yaml"
        if security_policy_path.is_file() and llm is not None:
            from duckclaw.graphs.sandbox import (
                browser_sandbox_tool_factory,
                get_browser_session_url_tool_factory,
                sandbox_tool_factory,
            )

            if getattr(spec, "browser_sandbox", False) and "run_browser_sandbox" not in tools_by_name:
                tools.append(browser_sandbox_tool_factory(db, llm))
                tools_by_name = {t.name: t for t in tools}
            if getattr(spec, "browser_sandbox", False) and "get_browser_session_url" not in tools_by_name:
                tools.append(get_browser_session_url_tool_factory(db, llm))
                tools_by_name = {t.name: t for t in tools}
            if "run_sandbox" not in tools_by_name:
                tools.append(sandbox_tool_factory(db, llm))
                tools_by_name = {t.name: t for t in tools}
    except Exception:
        pass

    _jh_alnum = re.sub(r"[^a-z0-9]", "", (spec.worker_id or "").lower())
    _jh_logical = re.sub(r"[^a-z0-9]", "", (getattr(spec, "logical_worker_id", None) or "").lower())
    if (
        (_jh_alnum == "jobhunter" or _jh_logical == "jobhunter")
        and getattr(spec, "research_config", None)
        and (spec.research_config or {}).get("tavily_enabled", True)
        and "tavily_search" not in tools_by_name
    ):
        _log.warning(
            "Job-Hunter: manifest con Tavily habilitado pero la tool tavily_search no está en el grafo "
            "(instala tavily-python en el venv del gateway y define TAVILY_API_KEY en el proceso). "
            "Sin ello el LLM solo ve run_sandbox y puede simular búsquedas."
        )

    # Aplicar LangSmith config al grafo final (no solo al llm) si está habilitado
    send_to_langsmith = os.environ.get("DUCKCLAW_SEND_TO_LANGSMITH", "false").lower() == "true"
    if send_to_langsmith:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        # Honor explicitly set project in env, otherwise fallback to spec name or default
        if not os.environ.get("LANGCHAIN_PROJECT"):
            os.environ["LANGCHAIN_PROJECT"] = instance_name or getattr(spec, "name", "DuckClaw") or "default"
        # Si la API KEY no existe en el entorno, LangSmith simplemente la ignorará o fallará silenciosamente
    else:
        # Desactivar explícitamente para esta instanciación si estaba globalmente activo
        os.environ["LANGCHAIN_TRACING_V2"] = "false"

    from langgraph.graph import END, StateGraph
    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage

    has_homeostasis = bool(getattr(spec, "homeostasis_config", None))
    crm_config = getattr(spec, "crm_config", None) or {}
    crm_enabled = bool(crm_config.get("enabled", False))
    _task_block = (
        _LEILA_TASK_AWARENESS_PROMPT.strip()
        if (getattr(spec, "worker_id", None) or "").strip() == "LeilaAssistant"
        else _TASK_AWARENESS_PROMPT.strip()
    )
    _system_prompt_only = (system_prompt or "").strip()
    _task_block_resolved = _task_block
    effective_prompt = _system_prompt_only + "\n\n" + _task_block_resolved
    # Cierre de dominio = última instrucción al modelo (p. ej. LeilaAssistant/domain_closure.md).
    effective_prompt = append_domain_closure_block(effective_prompt, spec)
    _lid = (getattr(spec, "logical_worker_id", None) or spec.worker_id or "").strip()
    if _lid == "bi_analyst":
        _nm = (getattr(spec, "name", None) or "Analista BI").strip()
        effective_prompt = (
            f"Identidad activa (prioritaria sobre mensajes previos del hilo): eres **{_nm}**. "
            "No digas que eres «Agente de Investigación Activa» ni otro rol de investigación web; "
            "el historial puede mezclar conversaciones antiguas.\n\n"
            + effective_prompt
        )

    _cp = _normalized_context_pruning(spec)
    use_cm = bool(_cp.get("enabled") and _lid == "bi_analyst")
    _schema_digest = ""
    if _lid == "bi_analyst" and _cp.get("enabled"):
        at = ", ".join(spec.allowed_tables) if spec.allowed_tables else "(ninguna lista explícita)"
        _schema_digest = (
            f"\n\n## Contexto de esquema\nEsquema analítico `{spec.schema_name}`; tablas permitidas: {at}. "
            "Para tipos y DDL exactos, ejecuta `get_schema_info` al inicio del análisis.\n"
        )
    _bi_prompt_base: str | None = (effective_prompt + _schema_digest) if (_lid == "bi_analyst" and _cp.get("enabled")) else None

    def prepare_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        cfg = config or {}
        conf_obj = cfg.get("configurable")
        meta = cfg.get("metadata") or {}
        conf_incoming = (conf_obj.get("incoming") if isinstance(conf_obj, dict) else None) or (meta.get("incoming") if meta else None)
        incoming = (
            (state.get("incoming") or state.get("input") or "").strip()
            or (str(conf_incoming).strip() if conf_incoming else "")
        )
        if not incoming and state.get("messages"):
            for m in reversed(state["messages"]):
                if isinstance(m, HumanMessage) and getattr(m, "content", None):
                    incoming = (str(m.content) or "").strip()
                    break
        if not isinstance(incoming, str):
            incoming = str(incoming or "").strip()
        if _bi_prompt_base is not None:
            prompt = _compose_bi_system_prompt(_bi_prompt_base, (state.get("analytical_summary") or "").strip())
        elif _lid == "finanz" and finanz_field_reflection_enabled(spec):
            fe = format_field_experience_block(incoming, db, spec.schema_name, top_n=5)
            if fe:
                prompt = append_domain_closure_block(
                    _system_prompt_only + "\n\n" + fe + "\n\n" + _task_block_resolved,
                    spec,
                )
            else:
                prompt = effective_prompt
        else:
            prompt = effective_prompt
        if crm_enabled:
            try:
                from duckclaw.forge.crm.context_injector import graph_context_injector
                lead_id = state.get("chat_id") or state.get("session_id") or "default"
                lead_ctx = graph_context_injector(db, lead_id)
                if lead_ctx:
                    prompt = prompt + "\n\n<lead_context>\n" + lead_ctx + "\n</lead_context>"
            except Exception:
                pass
        if _lid == "quant_trader":
            try:
                from duckclaw.forge.skills.quant_trader_bridge import quant_trading_session_prompt_block

                _qblk = quant_trading_session_prompt_block(db)
                if _qblk:
                    prompt = prompt + "\n\n" + _qblk
            except Exception:
                pass
        messages = [SystemMessage(content=prompt)]
        for h in (state.get("history") or []):
            role = (h.get("role") or "").lower()
            content = h.get("content") or ""
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        needs_task = state.get("homeostasis_hint") == "ask_task" or _is_no_task(incoming)
        if needs_task:
            if (getattr(spec, "worker_id", None) or "").strip() == "LeilaAssistant":
                user_content = (
                    f"[El usuario dijo: '{incoming.strip() or '(vacío)'}'. Es saludo o mensaje muy breve. "
                    "Responde cordial como Leila Store, pregunta en qué puedes ayudar (catálogo, tallas, avisos) "
                    "en lenguaje natural. No uses la frase «¿Cuál es mi tarea?» ni comandos con /.]"
                )
            else:
                user_content = (
                    f"[El usuario dijo: '{incoming.strip() or '(vacío)'}'. No ha indicado una tarea concreta. "
                    "Pregúntale: ¿Cuál es mi tarea? Y ofrece ejemplos de lo que puedes hacer según tu rol.]"
                )
        else:
            user_content = incoming
        messages.append(HumanMessage(content=user_content))
        messages = _apply_provider_input_budget(messages, provider=provider)
        # LangGraph puede reemplazar/limitar el state entre nodos; preservamos chat_id para
        # que _sandbox_enabled_for_state (y otros flags por sesión) lean el ID correcto.
        out = {**state, "messages": messages, "incoming": incoming}
        if (state.get("analytical_summary") or "").strip():
            out["analytical_summary"] = (state.get("analytical_summary") or "").strip()
        out.update(_identity_fields(state))
        return out

    def context_monitor_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        if not _cp.get("enabled") or _lid != "bi_analyst":
            return state
        msgs = list(state.get("messages") or [])
        msgs = _truncate_tool_messages(msgs, _cp["tool_content_max_chars"])
        est = _estimate_tokens_from_messages(msgs)
        n = len(msgs)
        need = n > _cp["max_messages"] or est > _cp["max_estimated_tokens"]
        if not need:
            out = {**state, "messages": msgs}
            out.update(_identity_fields(state))
            return out
        if not msgs or not isinstance(msgs[0], SystemMessage):
            out = {**state, "messages": msgs}
            out.update(_identity_fields(state))
            return out
        rest = msgs[1:]
        head, tail = _split_for_pruning(rest, _cp["keep_last_messages"])
        prior = (state.get("analytical_summary") or "").strip()
        if need and not head:
            trimmed = list(rest)
            sys0 = msgs[0]
            while len(trimmed) > 1 and _estimate_tokens_from_messages([sys0] + trimmed) > _cp["max_estimated_tokens"]:
                trimmed = trimmed[1:]
            base = _bi_prompt_base or effective_prompt
            sys_content = _compose_bi_system_prompt(base, prior)
            new_msgs = [SystemMessage(content=sys_content)] + trimmed
            out = {**state, "messages": new_msgs, "analytical_summary": prior}
            out.update(_identity_fields(state))
            return out
        new_summary = prior
        if head:
            if llm_summary is not None:
                new_summary = _llm_fold_conversation_summary(llm_summary, head, prior)
            else:
                new_summary = ((prior + "\n") if prior else "").strip() + "[Contexto anterior truncado.]"
        base = _bi_prompt_base or effective_prompt
        sys_content = _compose_bi_system_prompt(base, new_summary)
        new_msgs = [SystemMessage(content=sys_content)] + tail
        out = {**state, "messages": new_msgs, "analytical_summary": new_summary}
        out.update(_identity_fields(state))
        return out

    def _sandbox_enabled_for_state(state: dict) -> bool:
        """Sandbox flag per chat/session (defaults to OFF)."""
        from duckclaw.graphs.on_the_fly_commands import get_chat_state

        chat_id = state.get("chat_id") or state.get("session_id") or "default"
        raw = get_chat_state(db, chat_id, "sandbox_enabled")
        v = (raw or "").strip().lower()
        enabled = v in ("true", "1", "on", "sí", "si")
        return enabled

    tools_sandbox_off = filter_tools_for_sandbox(tools, enabled=False)
    tools_by_name_sandbox_off = {t.name: t for t in tools_sandbox_off}

    _groq_bind = (provider or "").strip().lower() == "groq"
    _tools_for_llm_bind = _groq_tools_without_reddit_for_bind(tools) if _groq_bind else tools
    _tools_sandbox_off_bind = (
        _groq_tools_without_reddit_for_bind(tools_sandbox_off) if _groq_bind else tools_sandbox_off
    )
    if _groq_bind:
        _log.info(
            "Groq: bind genérico sin reddit_* (%d tools; forzados Reddit/otros usan set acorde).",
            len(_tools_for_llm_bind),
        )

    if llm is None:
        def agent_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
            out = {
                **state,
                "messages": state["messages"] + [AIMessage(content="Sin LLM configurado. Configura DUCKCLAW_LLM_PROVIDER.")],
            }
            out.update(_identity_fields(state))
            return out
    else:
        from duckclaw.integrations.llm_providers import (
            bind_tools_with_parallel_default as _bind_tools,
            extract_embedded_json_tool_invokes,
        )

        # Cache de re-ligado por modo (evita re-bind costoso por chat/turno).
        # parallel_tool_calls=True en APIs OpenAI-compat (incl. MLX): permite varias tool_calls en un turno.
        # Groq (~12k TPM): rutas genéricas sin reddit_* (ver _tools_for_llm_bind); Reddit forzado usa `tools` completo.
        llm_with_tools_on = _bind_tools(llm, _tools_for_llm_bind)
        llm_with_tools_off = _bind_tools(llm, _tools_sandbox_off_bind)

        has_ibkr = "get_ibkr_portfolio" in tools_by_name
        has_fmp_stock = "get_fmp_stock_dividends" in tools_by_name
        has_fmp_calendar = "get_fmp_dividends_calendar" in tools_by_name
        has_read_sql = "read_sql" in tools_by_name
        has_admin_sql = "admin_sql" in tools_by_name
        has_run_sandbox = "run_sandbox" in tools_by_name
        tool_choice_inspect_schema = {"type": "function", "function": {"name": "inspect_schema"}}
        tool_choice_read_sql = {"type": "function", "function": {"name": "read_sql"}}
        tool_choice_admin_sql = {"type": "function", "function": {"name": "admin_sql"}}
        tool_choice_portfolio = {"type": "function", "function": {"name": "get_ibkr_portfolio"}}
        tool_choice_fmp_stock = {"type": "function", "function": {"name": "get_fmp_stock_dividends"}}
        tool_choice_fmp_calendar = {"type": "function", "function": {"name": "get_fmp_dividends_calendar"}}
        tool_choice_run_sandbox = {"type": "function", "function": {"name": "run_sandbox"}}

        llm_force_schema_on = _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_inspect_schema)
        llm_force_schema_off = _bind_tools(
            llm, _tools_sandbox_off_bind, tool_choice=tool_choice_inspect_schema
        )
        llm_force_read_sql_on = _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_read_sql)
        llm_force_read_sql_off = _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_read_sql)
        llm_force_admin_sql_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_admin_sql) if has_admin_sql else None
        )
        llm_force_admin_sql_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_admin_sql)
            if has_admin_sql
            else None
        )
        llm_force_portfolio_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_portfolio) if has_ibkr else None
        )
        llm_force_portfolio_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_portfolio) if has_ibkr else None
        )
        llm_force_fmp_stock_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_fmp_stock) if has_fmp_stock else None
        )
        llm_force_fmp_stock_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_fmp_stock)
            if has_fmp_stock
            else None
        )
        llm_force_fmp_calendar_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_fmp_calendar)
            if has_fmp_calendar
            else None
        )
        llm_force_fmp_calendar_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_fmp_calendar)
            if has_fmp_calendar
            else None
        )
        llm_force_run_sandbox_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_run_sandbox)
            if has_run_sandbox
            else None
        )
        llm_force_run_sandbox_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_run_sandbox)
            if "run_sandbox" in tools_by_name_sandbox_off
            else None
        )

        has_tavily = "tavily_search" in tools_by_name
        tool_choice_tavily = {"type": "function", "function": {"name": "tavily_search"}}
        llm_force_tavily_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_tavily) if has_tavily else None
        )
        llm_force_tavily_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_tavily) if has_tavily else None
        )

        has_pqrsd_fetch = "pqrsd_fetch_canonical" in tools_by_name
        tool_choice_pqrsd_fetch = {"type": "function", "function": {"name": "pqrsd_fetch_canonical"}}
        llm_force_pqrsd_fetch_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_pqrsd_fetch)
            if has_pqrsd_fetch
            else None
        )
        llm_force_pqrsd_fetch_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_pqrsd_fetch)
            if has_pqrsd_fetch
            else None
        )

        has_fetch_market = "fetch_market_data" in tools_by_name
        tool_choice_fetch_market = {"type": "function", "function": {"name": "fetch_market_data"}}
        llm_force_fetch_market_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_fetch_market)
            if has_fetch_market
            else None
        )
        llm_force_fetch_market_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_fetch_market)
            if has_fetch_market
            else None
        )

        has_fetch_ib_gateway = "fetch_ib_gateway_ohlcv" in tools_by_name
        tool_choice_fetch_ib_gateway = {"type": "function", "function": {"name": "fetch_ib_gateway_ohlcv"}}
        llm_force_fetch_ib_gateway_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_fetch_ib_gateway)
            if has_fetch_ib_gateway
            else None
        )
        llm_force_fetch_ib_gateway_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_fetch_ib_gateway)
            if has_fetch_ib_gateway
            else None
        )

        has_propose_trade_signal = "propose_trade_signal" in tools_by_name
        tool_choice_propose_trade_signal = {"type": "function", "function": {"name": "propose_trade_signal"}}
        llm_force_propose_trade_signal_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_propose_trade_signal)
            if has_propose_trade_signal
            else None
        )
        llm_force_propose_trade_signal_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_propose_trade_signal)
            if has_propose_trade_signal and "propose_trade_signal" in tools_by_name_sandbox_off
            else None
        )

        has_execute_approved_signal = "execute_approved_signal" in tools_by_name
        tool_choice_execute_approved_signal = {
            "type": "function",
            "function": {"name": "execute_approved_signal"},
        }
        llm_force_execute_approved_signal_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_execute_approved_signal)
            if has_execute_approved_signal
            else None
        )
        llm_force_execute_approved_signal_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_execute_approved_signal)
            if has_execute_approved_signal and "execute_approved_signal" in tools_by_name_sandbox_off
            else None
        )

        has_evaluate_cfd_state = "evaluate_cfd_state" in tools_by_name
        tool_choice_evaluate_cfd_state = {
            "type": "function",
            "function": {"name": "evaluate_cfd_state"},
        }
        llm_force_evaluate_cfd_state_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_evaluate_cfd_state)
            if has_evaluate_cfd_state
            else None
        )
        llm_force_evaluate_cfd_state_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_evaluate_cfd_state)
            if has_evaluate_cfd_state and "evaluate_cfd_state" in tools_by_name_sandbox_off
            else None
        )

        has_inspect_macro_pgq = "inspect_macro_pgq" in tools_by_name

        _reddit_tool_names = sorted(k for k in tools_by_name if (k or "").startswith("reddit_"))
        has_reddit_tools = bool(_reddit_tool_names)

        def _reddit_tool_choice_dict(tool_nm: str) -> dict[str, Any]:
            return {"type": "function", "function": {"name": tool_nm}}

        llm_force_reddit_post_on = (
            _bind_tools(llm, tools, tool_choice=_reddit_tool_choice_dict("reddit_get_post"))
            if "reddit_get_post" in tools_by_name
            else None
        )
        llm_force_reddit_post_off = (
            _bind_tools(llm, tools_sandbox_off, tool_choice=_reddit_tool_choice_dict("reddit_get_post"))
            if "reddit_get_post" in tools_by_name_sandbox_off
            else None
        )
        llm_force_reddit_search_on = (
            _bind_tools(llm, tools, tool_choice=_reddit_tool_choice_dict("reddit_search_reddit"))
            if "reddit_search_reddit" in tools_by_name
            else None
        )
        llm_force_reddit_search_off = (
            _bind_tools(llm, tools_sandbox_off, tool_choice=_reddit_tool_choice_dict("reddit_search_reddit"))
            if "reddit_search_reddit" in tools_by_name_sandbox_off
            else None
        )
        _reddit_fallback_nm = None
        if has_reddit_tools and not llm_force_reddit_post_on and not llm_force_reddit_search_on:
            _reddit_fallback_nm = _reddit_tool_names[0]
        llm_force_reddit_fallback_on = (
            _bind_tools(llm, tools, tool_choice=_reddit_tool_choice_dict(_reddit_fallback_nm))
            if _reddit_fallback_nm and _reddit_fallback_nm in tools_by_name
            else None
        )
        llm_force_reddit_fallback_off = (
            _bind_tools(llm, tools_sandbox_off, tool_choice=_reddit_tool_choice_dict(_reddit_fallback_nm))
            if _reddit_fallback_nm and _reddit_fallback_nm in tools_by_name_sandbox_off
            else None
        )

        def _incoming_has_reddit_url(text: str) -> bool:
            if not text or not str(text).strip():
                return False
            return bool(re.search(r"(?:reddit\.com|redd\.it)/", str(text), re.IGNORECASE))

        def _incoming_looks_like_reddit_post_url(text: str) -> bool:
            if not text or not str(text).strip():
                return False
            return bool(
                re.search(
                    r"(?:https?://)?(?:www\.)?reddit\.com/r/[\w_]+/comments/[\w]+",
                    str(text),
                    re.IGNORECASE,
                )
            )

        def _first_reddit_url_in_text(text: str) -> Optional[str]:
            return _extract_first_reddit_url(text)

        def _incoming_has_reddit_share_path(text: str) -> bool:
            return bool(re.search(r"reddit\.com/r/[\w_]+/s/[a-zA-Z0-9]+", str(text or ""), re.IGNORECASE))

        def _reddit_share_slug_from_incoming(text: str) -> Optional[str]:
            m = re.search(r"/r/[\w_]+/s/([a-zA-Z0-9]+)", str(text or ""), re.IGNORECASE)
            return m.group(1) if m else None

        def _count_tool_messages_named(messages: list[Any], tool_name: str) -> int:
            n = 0
            for m in messages or []:
                if isinstance(m, ToolMessage) and (getattr(m, "name", None) or "") == tool_name:
                    n += 1
            return n

        def _reddit_tool_message_no_data(msg: Any) -> bool:
            if not isinstance(msg, ToolMessage):
                return False
            name = str(getattr(msg, "name", "") or "").strip()
            if not name.startswith("reddit_"):
                return False
            content = str(getattr(msg, "content", "") or "")
            low = content.lower()
            if "not found" in low:
                return True
            if '"posts": []' in content:
                return True
            return False

        def _tc_args_as_dict(tc: Any) -> dict[str, Any]:
            if isinstance(tc, dict):
                args = tc.get("args")
                if isinstance(args, dict):
                    return dict(args)
                raw = tc.get("arguments")
                if isinstance(raw, str) and raw.strip():
                    try:
                        parsed = json.loads(raw)
                        if isinstance(parsed, dict):
                            return dict(parsed)
                    except Exception:
                        pass
            return {}

        def _patch_ai_reddit_share_tool_calls(resp: Any, share_url: str) -> Any:
            """
            Fallback si no hubo resolución HTTP a URL /comments/ en agent_node: el slug /s/ no es post_id.
            Reescribe get_post → reddit_search_reddit(query=url). Nota: mcp-reddit puede fallar con query=URL;
            el camino preferido es _resolve_reddit_share_url_to_comments_url + reddit_get_post.
            """
            if not share_url or not _incoming_has_reddit_share_path(share_url):
                return resp
            tcs = list(getattr(resp, "tool_calls", None) or [])
            if not tcs:
                return resp
            patched: list[Any] = []
            changed = False
            for tc in tcs:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                tid = (tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)) or ""
                if name == "reddit_get_post":
                    patched.append(
                        {"name": "reddit_search_reddit", "args": {"query": share_url}, "id": tid}
                    )
                    changed = True
                    continue
                if name == "reddit_search_reddit" and isinstance(tc, dict):
                    args = _tc_args_as_dict(tc)
                    args["query"] = share_url
                    new_tc = {**tc, "args": args}
                    new_tc.pop("arguments", None)
                    patched.append(new_tc)
                    changed = True
                    continue
                patched.append(tc)
            if not changed:
                return resp
            return resp.model_copy(update={"tool_calls": patched})

        def _spec_is_job_hunter() -> bool:
            a = re.sub(r"[^a-z0-9]", "", (spec.worker_id or "").lower())
            b = re.sub(r"[^a-z0-9]", "", (getattr(spec, "logical_worker_id", None) or "").lower())
            return a == "jobhunter" or b == "jobhunter"

        def _is_portfolio_query(text: str) -> bool:
            if not text or not text.strip():
                return False
            t = text.strip().lower()
            # Excluir: gastos/transacciones locales (evitar que "acciones" en "transacciones" dispare IBKR)
            if any(k in t for k in ("transacciones", "gastos", "compras", "presupuesto")):
                return False
            # Excluir: tablas DuckDB, esquema o estructura de base de datos
            if any(k in t for k in ("tablas", "tabla", "duckdb", "esquema", "schema", "estructura", "qué tablas", "que tablas")):
                return False
            # Excluir: cuenta bancaria concreta (Bancolombia, etc.) -> debe usar read_sql/admin_sql sobre .duckdb
            if any(k in t for k in ("cuenta de ", "cuenta bancolombia", "bancolombia", "en bancolombia", "saldo en mi cuenta")):
                return False
            # "Portfolio total" / "cuánto tengo en total" -> no forzar solo IBKR; el agente debe usar get_ibkr_portfolio + read_sql (cuentas en .duckdb)
            if any(k in t for k in ("portfolio total", "en total", "resumen de todo", "cuánto tengo en total", "cuanto tengo en total")):
                return False
            # Cuentas locales en .duckdb (resumen de mis cuentas, etc.) — nunca forzar IBKR por subcadena "mis cuentas"
            if _is_finanz_local_accounts_query(text):
                return False
            # "acciones" como palabra completa (no subcadena de "transacciones")
            # "ibkr", "en ibkr" -> consultas explícitas al broker
            # No incluir "mis cuentas" / "estado de mis cuentas" (ambiguo con cuentas bancarias locales).
            kw = (
                "portfolio",
                "portafolio",
                "cuanto dinero",
                "cuánto dinero",
                "saldo ibkr",
                "dinero en bolsa",
                "resumen de mi portfolio",
                "en ibkr",
                "ibkr",
                "interactive brokers",
            )
            if any(k in t for k in kw):
                return True
            return bool(re.search(r"\bacciones\b", t))

        def _quant_retry_or_probe_needs_ibkr_portfolio(messages: list, text: str) -> bool:
            """Quant-Trader: probes/reintentos cortos sobre cuenta paper/IBKR o retry tras mensaje previo del agente sobre broker."""
            t = (text or "").strip().lower()
            if not t or len(t) > 180:
                return False
            probe_kw = (
                "cuenta paper",
                "validar conexión",
                "validar conexion",
                "probar conexión",
                "probar conexion",
                "conexion ibkr",
                "conexión ibkr",
                "conectar con ibkr",
                "servicio de portfolio",
                "snapshot ibkr",
                "validación de conexión",
                "validacion de conexion",
            )
            if any(k in t for k in probe_kw):
                return True
            if not re.search(
                r"\b(reintent|vuelv\w*|intent\w*|de\s+nuevo|otra\s+vez|try\s+again)\b",
                t,
            ):
                return False
            for m in reversed((messages or [])[-12:]):
                if not isinstance(m, AIMessage):
                    continue
                c = (str(m.content) or "").lower()
                if len(c) < 40:
                    continue
                if any(
                    x in c
                    for x in (
                        "ibkr",
                        "interactive brokers",
                        "portfolio",
                        "portafolio",
                        "cuenta paper",
                        "validación de conexión",
                        "validacion de conexion",
                        "servicio de portfolio",
                        "conexión",
                        "conexion",
                        "paper",
                        "gateway",
                    )
                ):
                    return True
            return False

        def _quant_execution_bug_probe_needs_ibkr_portfolio(text: str) -> bool:
            """Quant-Trader: consultas de verificación de bug/ejecución deben citar snapshot real de IBKR."""
            t = (text or "").strip().lower()
            if not t:
                return False
            has_bug_probe = any(k in t for k in ("bug", "falla", "falla", "error", "verifica", "revisa"))
            has_execution_context = any(
                k in t for k in ("ejec", "señal", "senal", "order id", "ib order", "broker", "paper")
            )
            return has_bug_probe and has_execution_context

        def _is_dividends_query(text: str) -> bool:
            if not text or not text.strip():
                return False
            t = text.strip().lower()
            return any(
                k in t
                for k in (
                    "dividendo",
                    "dividendos",
                    "ex-div",
                    "ex dividend",
                    "record date",
                    "payment date",
                )
            )

        def _is_schema_query(text: str) -> bool:
            if not text or not text.strip():
                return False
            t = text.strip().lower()
            # TAREA explícita: leer filas en job_opportunities → read_sql, no inspect_schema.
            if "read_sql" in t and "job_opportunities" in t:
                return False
            # "tabla o lista" = formato de presentación, no pedido de esquema DuckDB.
            if re.search(r"\btabla\s+o\s+lista\b", t):
                return False
            # Si piden contenido/filas de una tabla, NO forzar inspect_schema.
            if _TABLE_CONTENT_PHRASE.search(t):
                return False
            return any(k in t for k in ("tablas", "tabla", "duckdb", "esquema", "schema", "estructura", "qué tablas", "que tablas"))

        def _is_table_content_query(text: str) -> bool:
            if not text or not text.strip():
                return False
            t = text.strip().lower()
            if "read_sql" in t and "job_opportunities" in t:
                return True
            return bool(_TABLE_CONTENT_PHRASE.search(t))

        def _is_latest_game_query(text: str) -> bool:
            if not text or not text.strip():
                return False
            t = text.strip().lower()
            return bool(
                re.search(r"\b(ultima|última|mas\s+reciente|más\s+reciente)\s+partida\b", t)
            ) or ("partida" in t and ("ultima" in t or "última" in t or "reciente" in t))

        def agent_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
            _chat_ctx = state.get("chat_id") or state.get("session_id") or "default"
            _tenant_ctx = (state.get("tenant_id") or "").strip() or "default"
            _log_chat = format_chat_log_identity(str(_chat_ctx).strip() or "default", state.get("username"))
            set_log_context(tenant_id=_tenant_ctx, worker_id=worker_id, chat_id=_log_chat)
            _ev_msgs = state.get("messages") or []
            _ev_last = _ev_msgs[-1] if _ev_msgs else None
            if _lid == "quant_trader":
                from duckclaw.forge.skills.quant_tool_context import (
                    bind_quant_market_evidence_chat,
                    reset_quant_market_evidence,
                )

                bind_quant_market_evidence_chat(str(_chat_ctx))
                if _ev_last is None or isinstance(_ev_last, HumanMessage):
                    reset_quant_market_evidence()
            _wl = _worker_log_label(worker_id)
            cfg = config or {}
            incoming = (
                (state.get("incoming") or state.get("input") or "").strip()
                or (cfg.get("configurable") or {}).get("incoming") or ""
            )
            if isinstance(incoming, str):
                incoming = incoming.strip()
            else:
                incoming = str(incoming or "").strip()
            # Fallback: extraer del último HumanMessage
            if not incoming and state.get("messages"):
                for m in reversed(state["messages"]):
                    if isinstance(m, HumanMessage) and getattr(m, "content", None):
                        incoming = (str(m.content) or "").strip()
                        break
            telegram_context_summarize_directive = (
                "[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]" in (incoming or "")
                or "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]" in (incoming or "")
            )
            summarize_stored_directive = "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]" in (incoming or "")
            _is_goals_tick_msg = (
                str(incoming or "").strip().startswith("[SYSTEM_EVENT:")
                and "Revisión periódica de /goals" in str(incoming or "")
            )
            is_schema = _is_schema_query(incoming)
            is_table_content = _is_table_content_query(incoming)
            is_latest_game = _is_latest_game_query(incoming)
            _is_portfolio_kw = _is_portfolio_query(incoming)
            _is_portfolio_quant_retry = (
                (_lid or "").strip().lower() == "quant_trader"
                and _quant_retry_or_probe_needs_ibkr_portfolio(_ev_msgs, incoming)
            )
            _wants_new_signal = bool(
                (_lid or "").strip().lower() == "quant_trader"
                and _quant_user_requests_new_trade_signal(incoming)
            )
            _is_quant_operational_directive = bool(
                (_lid or "").strip().lower() == "quant_trader"
                and str(incoming or "").strip().lower().startswith(
                    "tarea: intención operativa cuant detectada".lower()
                )
            )
            _is_exec_bug_probe = (
                (_lid or "").strip().lower() == "quant_trader"
                and _quant_execution_bug_probe_needs_ibkr_portfolio(incoming)
            )
            is_portfolio = has_ibkr and (_is_portfolio_kw or _is_portfolio_quant_retry or _is_exec_bug_probe)
            if (_lid or "").strip().lower() == "quant_trader" and _wants_new_signal:
                # En comandos operativos de nueva señal no forzar `get_ibkr_portfolio` first.
                # Con Groq esto puede inducir tool_use_failed al mezclar tool_call + texto.
                is_portfolio = False
            if (_lid or "").strip().lower() == "quant_trader" and _is_quant_operational_directive:
                # TAREA sintética del manager incluye texto tipo "fetch+portfolio+..."; no forzar IBKR.
                is_portfolio = False
            if (_lid or "").strip().lower() == "quant_trader" and _is_goals_tick_msg:
                # En ticks /goals no forzar "solo portfolio": primero debe correr el ciclo CFD/HRP.
                is_portfolio = False
            force_finanz_cuentas = (
                (_lid or "").strip().lower() == "finanz"
                and has_read_sql
                and _is_finanz_local_accounts_query(incoming)
                and "[SYSTEM_DIRECTIVE:" not in (incoming or "")
            )
            force_finanz_deudas = (
                (_lid or "").strip().lower() == "finanz"
                and has_read_sql
                and _is_finanz_debts_query(incoming)
                and "[SYSTEM_DIRECTIVE:" not in (incoming or "")
            )
            force_finanz_presupuestos = (
                (_lid or "").strip().lower() == "finanz"
                and has_read_sql
                and _is_finanz_budgets_query(incoming)
                and "[SYSTEM_DIRECTIVE:" not in (incoming or "")
            )
            force_finanz_admin_sql = (
                (_lid or "").strip().lower() == "finanz"
                and has_admin_sql
                and _is_finanz_local_account_write_query(incoming)
                and "[SYSTEM_DIRECTIVE:" not in (incoming or "")
            )
            # Resumen post /context --add | --summary: el volcado ya va en el mensaje; no forzar inspect_schema
            # (p. ej. "esquemas criptográficos" dispara is_schema por subcadena "esquema"), read_sql, Reddit, etc.
            # SUMMARIZE_STORED_CONTEXT suele incluir URLs (reddit.com/...): sin esto, force_reddit roba el turno
            # y el modelo nunca sintetiza el snapshot de main.semantic_memory.
            if telegram_context_summarize_directive:
                is_schema = False
                is_table_content = False
                is_latest_game = False
                is_portfolio = False
                force_finanz_cuentas = False
                force_finanz_deudas = False
                force_finanz_presupuestos = False
                force_finanz_admin_sql = False
            # No forzar herramienta si el último mensaje ya es ToolMessage (ya ejecutamos la tool):
            # así el LLM puede responder con texto y no entrar en bucle (inspect_schema -> agent -> inspect_schema).
            last_msg = (state.get("messages") or [])[-1] if state.get("messages") else None
            already_has_tool_result = last_msg is not None and isinstance(last_msg, ToolMessage)
            if (
                (_lid or "").strip().lower() == "quant_trader"
                and telegram_context_summarize_directive
                and _incoming_has_reddit_url(incoming)
                and _reddit_tool_message_no_data(last_msg)
            ):
                _fallback_reply = (
                    "No pude recuperar ese post específico desde Reddit con el enlace corto "
                    "(no encontrado o sin resultados). Para mantener trazabilidad del contexto, "
                    "dejo marcado el estado como `source_unavailable` y no amplio con fuentes externas."
                )
                resp = AIMessage(content=_fallback_reply)
                out = {**state, "messages": state["messages"] + [resp]}
                out.update(_identity_fields(state))
                return out

            if _spec_is_job_hunter() and not has_tavily and not already_has_tool_result:
                try:
                    from duckclaw.graphs.manager_graph import job_hunter_user_requests_job_search as _jh_wants_search

                    if _jh_wants_search(incoming):
                        _no_tavily = (
                            "Error técnico: la herramienta **tavily_search** no está disponible en este despliegue "
                            "(falta `TAVILY_API_KEY` en el proceso del gateway o el paquete **tavily-python**). "
                            "No está permitido simular la búsqueda con **run_sandbox** ni inventar URLs. "
                            "Configura Tavily y reinicia el gateway."
                        )
                        resp = AIMessage(content=_no_tavily)
                        out = {**state, "messages": state["messages"] + [resp]}
                        out.update(_identity_fields(state))
                        return out
                except Exception:
                    pass

            force_schema = is_schema and not already_has_tool_result
            force_admin_sql = force_finanz_admin_sql and not already_has_tool_result
            force_read_sql = (
                is_table_content
                or is_latest_game
                or force_finanz_cuentas
                or force_finanz_deudas
                or force_finanz_presupuestos
            ) and not already_has_tool_result
            force_portfolio_first = is_portfolio and not already_has_tool_result
            force_portfolio_after_local_cuentas = (
                not telegram_context_summarize_directive
                and _finanz_should_force_ibkr_after_local_cuentas_read(
                    state.get("messages"),
                    logical_worker_id=str(_lid or ""),
                    has_ibkr=bool(has_ibkr),
                )
            )
            force_portfolio = force_portfolio_first or force_portfolio_after_local_cuentas
            is_dividends = _is_dividends_query(incoming)
            force_fmp = bool(
                is_dividends and not already_has_tool_result and (has_fmp_stock or has_fmp_calendar)
            )
            force_fmp_calendar = bool(
                force_fmp
                and has_fmp_calendar
                and any(
                    k in (incoming or "").strip().lower()
                    for k in ("próximos", "proximos", "calendario", "between", "entre")
                )
            )

            jh_fast_text: str | None = None
            if _spec_is_job_hunter() and not already_has_tool_result:
                try:
                    from duckclaw.graphs.manager_graph import (
                        _capabilities_fast_reply_text,
                        _greeting_fast_reply_text,
                        job_hunter_user_requests_job_search,
                    )
                    from duckclaw.graphs.on_the_fly_commands import _is_capabilities_smalltalk, _is_simple_greeting

                    if _is_capabilities_smalltalk(incoming):
                        jh_fast_text = _capabilities_fast_reply_text(spec.worker_id)
                    elif _is_simple_greeting(incoming):
                        jh_fast_text = _greeting_fast_reply_text(spec.worker_id)
                    force_tavily = bool(
                        has_tavily
                        and not jh_fast_text
                        and not _is_capabilities_smalltalk(incoming)
                        and not _is_simple_greeting(incoming)
                        and job_hunter_user_requests_job_search(incoming)
                    )
                except Exception:
                    force_tavily = False
            else:
                force_tavily = False

            _reddit_anchor_u: Optional[str] = None
            if _incoming_has_reddit_url(incoming):
                _reddit_anchor_u = _first_reddit_url_in_text(incoming)
            elif (_lid or "").strip().lower() == "finanz" and _finanz_followup_reddit_read_intent(incoming):
                _reddit_anchor_u = _most_recent_reddit_url_in_human_messages(state.get("messages") or [])
            incoming_for_reddit = incoming
            if _reddit_anchor_u and (_reddit_anchor_u not in (incoming or "")):
                incoming_for_reddit = f"{incoming}\n{_reddit_anchor_u}"

            _reddit_resolved_comments_url: Optional[str] = None
            if _reddit_anchor_u and _incoming_has_reddit_share_path(_reddit_anchor_u):
                _reddit_resolved_comments_url = _resolve_reddit_share_url_to_comments_url(_reddit_anchor_u)
            if _reddit_resolved_comments_url:
                incoming_for_reddit = (
                    f"{incoming_for_reddit}\nCanonical Reddit thread: {_reddit_resolved_comments_url}"
                )

            share_slug = _reddit_share_slug_from_incoming(incoming_for_reddit)
            reddit_search_tool_count = _count_tool_messages_named(state.get("messages") or [], "reddit_search_reddit")
            need_share_followup = bool(
                share_slug
                and already_has_tool_result
                and isinstance(last_msg, ToolMessage)
                and (last_msg.name or "") == "reddit_search_reddit"
                and share_slug not in str(last_msg.content or "")
                and reddit_search_tool_count < 2
            )
            # SUMMARIZE_NEW_CONTEXT con solo URL de Reddit debe poder forzar Reddit (fetch); STORED con URLs en
            # el volcado no debe robar el turno (sintetizar snapshot DuckDB).
            _allow_reddit_force = bool(
                _lid == "finanz"
                or (
                    _lid == "quant_trader"
                    and telegram_context_summarize_directive
                )
            )
            force_reddit = bool(
                _allow_reddit_force
                and has_reddit_tools
                and _reddit_anchor_u is not None
                and not summarize_stored_directive
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_portfolio
                    or force_fmp
                    or force_tavily
                )
                and (not already_has_tool_result or need_share_followup)
            )

            if not _worker_use_heuristic_first_tool(spec):
                force_schema = False
                force_admin_sql = False
                # No borrar read_sql si finanz exige ledger real (cuentas/deudas/presupuestos).
                if not (
                    force_finanz_cuentas
                    or force_finanz_deudas
                    or force_finanz_presupuestos
                ):
                    force_read_sql = False
                force_portfolio = False
                force_fmp = False
                force_fmp_calendar = False
                force_tavily = False
                force_reddit = False

            # Misma heurística OHLCV que Finanz: Quant Trader también expone fetch_market_data y la usa como
            # evidencia obligatoria antes de propose_trade_signal (quant_trader_bridge); forzar la tool evita
            # alucinaciones en pedidos explícitos de velas/descarga. No aplica a portfolio IBKR (force_portfolio).
            _lid_l = (_lid or "").strip().lower()
            _ibgw_url = (os.environ.get("IBKR_GATEWAY_OHLCV_URL") or "").strip()
            # Quant Trader: si hay URL dedicada al GET /api/market/ibkr/historical, forzar esa tool en lugar
            # de fetch_market_data (evita lake+HTTP genérico cuando el usuario configuró solo IB Gateway).
            force_fetch_ib_gateway = bool(
                _lid_l == "quant_trader"
                and has_fetch_ib_gateway
                and bool(_ibgw_url)
                and _finanz_user_requests_ohlcv_ingest(incoming)
                and not telegram_context_summarize_directive
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_portfolio
                    or force_tavily
                    or force_reddit
                )
                and not already_has_tool_result
            )
            if not _worker_use_heuristic_first_tool(spec):
                force_fetch_ib_gateway = False
            force_fetch_market_data = bool(
                _lid_l in ("finanz", "quant_trader")
                and has_fetch_market
                and _finanz_user_requests_ohlcv_ingest(incoming)
                and not force_fetch_ib_gateway
                and not telegram_context_summarize_directive
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_portfolio
                    or force_tavily
                    or force_reddit
                )
                and not already_has_tool_result
            )
            if not _worker_use_heuristic_first_tool(spec):
                force_fetch_market_data = False

            force_quant_propose_signal = False
            force_quant_signal_fetch_ib = False
            force_quant_signal_fetch_md = False
            force_quant_goals_evaluate_cfd = False
            if (
                _lid_l == "quant_trader"
                and _quant_user_requests_new_trade_signal(incoming)
                and not _quant_user_requests_execute_approved_signal(incoming)
                and _worker_use_heuristic_first_tool(spec)
            ):
                _has_eval_for_turn = _quant_tool_called_since(
                    state.get("messages") or [],
                    _quant_last_human_index(state.get("messages") or []),
                    "evaluate_cfd_state",
                )
                if (
                    not telegram_context_summarize_directive
                    and already_has_tool_result
                    and last_msg is not None
                    and (getattr(last_msg, "name", None) or "") in ("fetch_ib_gateway_ohlcv", "fetch_market_data")
                    and _quant_fetch_tool_message_looks_successful(last_msg)
                    and _has_eval_for_turn
                    and has_propose_trade_signal
                ):
                    force_quant_propose_signal = True
                elif (
                    not telegram_context_summarize_directive
                    and not already_has_tool_result
                    and not (
                        force_schema
                        or force_admin_sql
                        or force_read_sql
                        or force_portfolio
                        or force_fmp
                        or force_tavily
                        or force_reddit
                    )
                ):
                    if has_fetch_ib_gateway and bool(_ibgw_url):
                        force_quant_signal_fetch_ib = True
                    elif has_fetch_market:
                        force_quant_signal_fetch_md = True
            if (
                _lid_l == "quant_trader"
                and _is_goals_tick_msg
                and has_evaluate_cfd_state
                and _worker_use_heuristic_first_tool(spec)
                and not telegram_context_summarize_directive
                and not already_has_tool_result
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_portfolio
                    or force_fmp
                    or force_tavily
                    or force_reddit
                    or force_fetch_ib_gateway
                    or force_fetch_market_data
                    or force_quant_propose_signal
                    or force_quant_signal_fetch_ib
                    or force_quant_signal_fetch_md
                )
            ):
                force_quant_goals_evaluate_cfd = True

            _incoming_l = (incoming or "").lower()
            _is_graph_request = any(
                k in _incoming_l
                for k in (
                    "gráfica",
                    "grafica",
                    "gráfico",
                    "grafico",
                    "diagrama",
                    "plot",
                    "streamplot",
                    "subplot",
                    "matplotlib",
                    "seaborn",
                    "plotly",
                )
            )
            _is_plot_docs_request = any(
                k in _incoming_l
                for k in (
                    "matplotlib.org",
                    "seaborn.pydata.org",
                    "plotly.com/python",
                    "docs matplotlib",
                    "doc matplotlib",
                    "docs seaborn",
                    "doc seaborn",
                    "docs plotly",
                    "doc plotly",
                )
            )
            _plot_capable_worker = (_lid or "").strip().lower() in ("siata_analyst", "finanz")
            force_plot_docs = bool(
                has_tavily
                and _plot_capable_worker
                and _is_plot_docs_request
                and not telegram_context_summarize_directive
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_portfolio
                    or force_reddit
                    or force_fetch_market_data
                    or force_fetch_ib_gateway
                    or force_quant_propose_signal
                    or force_quant_signal_fetch_ib
                    or force_quant_signal_fetch_md
                )
                and not already_has_tool_result
            )
            force_run_sandbox = bool(
                _plot_capable_worker
                and has_run_sandbox
                and _is_graph_request
                and not telegram_context_summarize_directive
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_portfolio
                    or force_tavily
                    or force_plot_docs
                    or force_reddit
                    or force_fetch_market_data
                    or force_fetch_ib_gateway
                    or force_quant_propose_signal
                    or force_quant_signal_fetch_ib
                    or force_quant_signal_fetch_md
                )
                and not already_has_tool_result
            )
            if not _worker_use_heuristic_first_tool(spec):
                force_plot_docs = False
                force_run_sandbox = False
            if force_plot_docs:
                force_tavily = True

            if _worker_use_heuristic_first_tool(spec):
                _pa_esc = int(state.get("plan_attempt_index") or 0)
                if (
                    _pa_esc >= 1
                    and (_lid or "").strip().lower() == "finanz"
                    and has_read_sql
                    and not telegram_context_summarize_directive
                    and not already_has_tool_result
                ):
                    from duckclaw.graphs.agent_resilience import resilience_escalation_wants_read_sql

                    if resilience_escalation_wants_read_sql(incoming, _pa_esc):
                        force_read_sql = True

            if jh_fast_text is not None:
                resp = AIMessage(content=jh_fast_text)
                out = {**state, "messages": state["messages"] + [resp]}
                out.update(_identity_fields(state))
                return out

            force_pqrsd_fetch_canonical = bool(
                _lid_l == "pqrsd_assistant"
                and has_pqrsd_fetch
                and _worker_use_heuristic_first_tool(spec)
                and _pqrsd_substantive_forced_fetch(
                    incoming, summarize_directive=telegram_context_summarize_directive
                )
                and not already_has_tool_result
            )
            if not _worker_use_heuristic_first_tool(spec):
                force_pqrsd_fetch_canonical = False

            sandbox_enabled = _sandbox_enabled_for_state(state)
            _pqrsd_skipped_forced_fetch = False
            _p_force_pqrsd_before_datos_first = force_pqrsd_fetch_canonical
            if force_pqrsd_fetch_canonical and _pqrsd_datos_first_over_forced_fetch(incoming):
                force_pqrsd_fetch_canonical = False
                _pqrsd_skipped_forced_fetch = True
            if force_pqrsd_fetch_canonical and _pqrsd_contact_only_skip_forced_fetch(incoming):
                force_pqrsd_fetch_canonical = False
                _pqrsd_skipped_forced_fetch = True

            force_execute_approved_signal = bool(
                _lid_l == "quant_trader"
                and has_execute_approved_signal
                and _quant_user_requests_execute_approved_signal(incoming)
                and _worker_use_heuristic_first_tool(spec)
                and not telegram_context_summarize_directive
                and not already_has_tool_result
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_portfolio
                    or force_fmp
                    or force_tavily
                    or force_reddit
                    or force_fetch_ib_gateway
                    or force_fetch_market_data
                    or force_quant_propose_signal
                    or force_quant_signal_fetch_ib
                    or force_quant_signal_fetch_md
                    or force_plot_docs
                    or force_run_sandbox
                    or force_pqrsd_fetch_canonical
                )
            )
            if not _worker_use_heuristic_first_tool(spec):
                force_execute_approved_signal = False

            force_quant_autoexec_validation_read_sql = bool(
                _lid_l == "quant_trader"
                and has_read_sql
                and _quant_user_requests_autoexec_validation(incoming)
                and _worker_use_heuristic_first_tool(spec)
                and not telegram_context_summarize_directive
                and not already_has_tool_result
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_portfolio
                    or force_fmp
                    or force_tavily
                    or force_reddit
                    or force_fetch_ib_gateway
                    or force_fetch_market_data
                    or force_quant_propose_signal
                    or force_quant_signal_fetch_ib
                    or force_quant_signal_fetch_md
                    or force_plot_docs
                    or force_run_sandbox
                    or force_pqrsd_fetch_canonical
                    or force_execute_approved_signal
                )
            )
            if force_quant_autoexec_validation_read_sql:
                force_read_sql = True

            _quant_proceed_like = bool(_lid_l == "quant_trader" and _quant_is_proceed_like(incoming))
            _quant_deterministic_cycle = bool(
                _lid_l == "quant_trader"
                and _worker_use_heuristic_first_tool(spec)
                and not telegram_context_summarize_directive
                and (
                    _wants_new_signal
                    or _is_goals_tick_msg
                    or _quant_proceed_like
                )
            )
            _last_human_idx = _quant_last_human_index(state.get("messages") or [])
            _has_fetch_since_last_human = _quant_tool_called_since(
                state.get("messages") or [], _last_human_idx, "fetch_ib_gateway_ohlcv"
            ) or _quant_tool_called_since(state.get("messages") or [], _last_human_idx, "fetch_market_data")
            _has_portfolio_since_last_human = _quant_tool_called_since(
                state.get("messages") or [], _last_human_idx, "get_ibkr_portfolio"
            )
            _has_eval_since_last_human = _quant_tool_called_since(
                state.get("messages") or [], _last_human_idx, "evaluate_cfd_state"
            )
            _quant_tickers = _quant_extract_tickers(incoming)
            if not _quant_tickers:
                _ev_eval = _quant_latest_tool_json_since(
                    state.get("messages") or [], _last_human_idx, "evaluate_cfd_state"
                )
                _ev_res = _ev_eval.get("results")
                if isinstance(_ev_res, list):
                    for _r in _ev_res:
                        if isinstance(_r, dict) and str(_r.get("ticker") or "").strip():
                            _quant_tickers.append(str(_r.get("ticker")).strip().upper())
            if not _quant_tickers:
                _quant_tickers = ["SPY"]
            _quant_primary_ticker = _quant_tickers[0]
            _quant_session_uid = ""
            _ev_eval2 = _quant_latest_tool_json_since(
                state.get("messages") or [], _last_human_idx, "evaluate_cfd_state"
            )
            if isinstance(_ev_eval2, dict):
                _quant_session_uid = str(_ev_eval2.get("session_uid") or "").strip()
            if not _quant_session_uid:
                _m_uid = re.search(r'"session_uid"\s*:\s*"([^"]+)"', str(incoming or ""))
                if _m_uid:
                    _quant_session_uid = str(_m_uid.group(1) or "").strip()
            _quant_signal_id = _quant_extract_signal_id(incoming)
            if not _quant_signal_id and _quant_user_requests_execute_approved_signal(incoming):
                _m = state.get("messages") or []
                for _msg in reversed(_m):
                    if isinstance(_msg, ToolMessage) and str(getattr(_msg, "name", "") or "") == "propose_trade_signal":
                        _sid = _quant_extract_signal_id(str(getattr(_msg, "content", "") or ""))
                        if _sid:
                            _quant_signal_id = _sid
                            break
            _regime_macro_pgq = ""
            _m_rm = re.search(
                r"\b(REGIMEN_[A-Z0-9_]+)\b",
                str(incoming or ""),
                flags=re.IGNORECASE,
            )
            if _m_rm:
                _regime_macro_pgq = str(_m_rm.group(1) or "").strip().upper()
            if (
                _lid_l == "quant_trader"
                and has_inspect_macro_pgq
                and _quant_user_requests_inspect_macro_pgq(incoming)
                and _worker_use_heuristic_first_tool(spec)
                and not telegram_context_summarize_directive
                and not already_has_tool_result
            ):
                _forced_tid_im = f"call_inspect_macro_pgq_{int(time.time() * 1000)}"
                _forced_tc_im = [
                    {
                        "name": "inspect_macro_pgq",
                        "args": {"regime_focus": _regime_macro_pgq},
                        "id": _forced_tid_im,
                        "type": "tool_call",
                    }
                ]
                _log.info("[%s] quant deterministic inspect_macro_pgq regime=%r", _wl, _regime_macro_pgq)
                _forced_resp_im = AIMessage(content="", tool_calls=_forced_tc_im)
                _out_im = {**state, "messages": state["messages"] + [_forced_resp_im]}
                _out_im.update(_identity_fields(state))
                return _out_im
            _quant_can_force_pipeline_step = bool(
                _quant_deterministic_cycle
                and not already_has_tool_result
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_portfolio
                    or force_fmp
                    or force_tavily
                    or force_reddit
                    or force_plot_docs
                    or force_run_sandbox
                    or force_pqrsd_fetch_canonical
                    or force_execute_approved_signal
                )
            )
            if _quant_can_force_pipeline_step and (not _has_fetch_since_last_human):
                _fetch_name = "fetch_ib_gateway_ohlcv" if (has_fetch_ib_gateway and bool(_ibgw_url)) else "fetch_market_data"
                _fetch_args = {
                    "ticker": _quant_primary_ticker,
                    "timeframe": "1h",
                    "lookback_days": 20,
                }
                _forced_tid = f"call_quant_pipeline_fetch_{int(time.time() * 1000)}"
                _forced_tc = [{"name": _fetch_name, "args": _fetch_args, "id": _forced_tid, "type": "tool_call"}]
                _log.info("[%s] quant deterministic stage=fetch tool=%s ticker=%s", _wl, _fetch_name, _quant_primary_ticker)
                _forced_resp = AIMessage(content="", tool_calls=_forced_tc)
                _out_forced = {**state, "messages": state["messages"] + [_forced_resp]}
                _out_forced["quant_pipeline_context"] = {
                    "mode": "goals" if _is_goals_tick_msg else "signal",
                    "tickers": _quant_tickers,
                    "session_uid": _quant_session_uid,
                }
                _out_forced.update(_identity_fields(state))
                return _out_forced
            if _quant_can_force_pipeline_step and _has_fetch_since_last_human and not _has_portfolio_since_last_human and has_ibkr:
                _forced_tid = f"call_quant_pipeline_portfolio_{int(time.time() * 1000)}"
                _forced_tc = [{"name": "get_ibkr_portfolio", "args": {}, "id": _forced_tid, "type": "tool_call"}]
                _log.info("[%s] quant deterministic stage=portfolio", _wl)
                _forced_resp = AIMessage(content="", tool_calls=_forced_tc)
                _out_forced = {**state, "messages": state["messages"] + [_forced_resp]}
                _out_forced["quant_pipeline_context"] = {
                    "mode": "goals" if _is_goals_tick_msg else "signal",
                    "tickers": _quant_tickers,
                    "session_uid": _quant_session_uid,
                }
                _out_forced.update(_identity_fields(state))
                return _out_forced
            if _quant_can_force_pipeline_step and _has_fetch_since_last_human and (not _has_eval_since_last_human) and has_evaluate_cfd_state:
                _forced_tid = f"call_quant_pipeline_eval_{int(time.time() * 1000)}"
                _forced_tc = [
                    {
                        "name": "evaluate_cfd_state",
                        "args": {
                            "session_uid": _quant_session_uid,
                            "tickers": _quant_tickers,
                            "signal_threshold": "GAS",
                        },
                        "id": _forced_tid,
                        "type": "tool_call",
                    }
                ]
                _log.info("[%s] quant deterministic stage=evaluate_cfd tickers=%s", _wl, ",".join(_quant_tickers))
                _forced_resp = AIMessage(content="", tool_calls=_forced_tc)
                _out_forced = {**state, "messages": state["messages"] + [_forced_resp]}
                _out_forced["quant_pipeline_context"] = {
                    "mode": "goals" if _is_goals_tick_msg else "signal",
                    "tickers": _quant_tickers,
                    "session_uid": _quant_session_uid,
                }
                _out_forced.update(_identity_fields(state))
                return _out_forced
            if (
                _lid_l == "quant_trader"
                and _quant_user_requests_execute_approved_signal(incoming)
                and has_execute_approved_signal
                and _quant_signal_id
                and not already_has_tool_result
            ):
                _forced_tid = f"call_quant_execute_signal_{int(time.time() * 1000)}"
                _forced_tc = [
                    {
                        "name": "execute_approved_signal",
                        "args": {"signal_id": _quant_signal_id},
                        "id": _forced_tid,
                        "type": "tool_call",
                    }
                ]
                _log.info("[%s] quant deterministic stage=execute signal_id=%s", _wl, _quant_signal_id)
                _forced_resp = AIMessage(content="", tool_calls=_forced_tc)
                _out_forced = {**state, "messages": state["messages"] + [_forced_resp]}
                _out_forced["quant_pipeline_context"] = {
                    "mode": "execute",
                    "tickers": _quant_tickers,
                    "session_uid": _quant_session_uid,
                    "signal_id": _quant_signal_id,
                }
                _out_forced.update(_identity_fields(state))
                return _out_forced

            llm_with_tools = llm_with_tools_on if sandbox_enabled else llm_with_tools_off
            forced_name = (
                "pqrsd_fetch_canonical"
                if force_pqrsd_fetch_canonical
                else (
                    "admin_sql"
                if force_admin_sql
                else (
                    "read_sql"
                    if force_read_sql
                    else (
                        "inspect_schema"
                        if force_schema
                        else (
                            "get_ibkr_portfolio"
                            if force_portfolio
                            else (
                                "execute_approved_signal"
                                if force_execute_approved_signal
                                else (
                                "evaluate_cfd_state"
                                if force_quant_goals_evaluate_cfd
                                else (
                                "propose_trade_signal"
                                if force_quant_propose_signal
                                else (
                                    "get_fmp_dividends_calendar"
                                    if force_fmp and force_fmp_calendar
                                    else (
                                        "get_fmp_stock_dividends"
                                        if force_fmp
                                        else (
                                            "tavily_search"
                                            if force_tavily
                                            else (
                                                "reddit"
                                                if force_reddit
                                                else (
                                                    "fetch_ib_gateway_ohlcv"
                                                    if (
                                                        force_fetch_ib_gateway
                                                        or force_quant_signal_fetch_ib
                                                    )
                                                    else (
                                                        "fetch_market_data"
                                                        if (
                                                            force_fetch_market_data
                                                            or force_quant_signal_fetch_md
                                                        )
                                                        else (
                                                            "run_sandbox"
                                                            if force_run_sandbox
                                                            else "auto"
                                                        )
                                                    )
                                                )
                                            )
                                        )
                                    )
                                )
                                )
                                )
                            )
                        )
                    )
                )
                )
            )
            _log.info(
                "[%s] incoming=%r | is_schema=%s | is_table_content=%s | is_latest_game=%s | "
                "is_portfolio=%s | ibkr_after_cuentas=%s | forced_tool=%s",
                _wl,
                incoming[:80] + ("..." if len(incoming) > 80 else ""),
                is_schema,
                is_table_content,
                is_latest_game,
                is_portfolio,
                force_portfolio_after_local_cuentas,
                forced_name,
            )
            from duckclaw.utils.formatters import sanitize_reddit_tool_messages_for_llm

            _msg_list = sanitize_reddit_tool_messages_for_llm(list(state["messages"]))
            _pqrsd_inject_datos_first_directive = bool(
                (_lid or "").strip().lower() == "pqrsd_assistant"
                and not already_has_tool_result
                and _pqrsd_datos_first_over_forced_fetch(incoming)
            )
            if _pqrsd_inject_datos_first_directive:
                _msg_list = [
                    SystemMessage(
                        content=(
                            "[DIRECTIVA_TURNO_PQRSD_DATOS_PRIMERO] No invoques `pqrsd_fetch_canonical` "
                            "en este turno ni des como primer paso un enlace o tutorial largo al portal web. "
                            "1) Pregunta si autoriza el tratamiento de datos personales para guardar el perfil "
                            "mínimo de radicación en la bóveda DuckDB de esta sesión "
                            "(esquema pqrsd_assistant, tabla radicacion_perfil). Si responde que no, no "
                            "continúes con guardado en bóveda ni insistas. "
                            "2) Si autoriza, recopila modo (identificada/anónima), documento si aplica, "
                            "correo y confirmación iguales. "
                            "3) Con datos completos y consentimiento explícito, persiste en bóveda: "
                            "`admin_sql` (UPSERT en pqrsd_assistant.radicacion_perfil) + `read_sql` para "
                            "validar la fila, O `pqrsd_upsert_radicacion_perfil` + `read_sql`. No invoques "
                            "`pqrsd_run_identificacion_step1` ni `run_browser_sandbox` para el flujo de "
                            "identificación hasta haber guardado y verificado en DB (salvo que el usuario "
                            "rechace la bóveda). "
                            "4) Cuando tengas el relato del caso y datos mínimos (ubicación/fecha si aplican), "
                            "registra el caso en CRM interno con `pqrsd_registrar_radicacion_crm` "
                            "(radicado MDE-YYYYMMDD-NNNN en tabla radicacion_crm); prioriza esta herramienta "
                            "sobre INSERT manual con `admin_sql`. `read_sql`/`admin_sql` están disponibles "
                            "solo sobre tablas permitidas del manifest. "
                            "5) Plazos o texto del portal solo si el usuario lo pide o tras perfil/CRM."
                        )
                    )
                ] + _msg_list
            if not _worker_use_heuristic_first_tool(spec):
                _msg_list = [
                    SystemMessage(
                        content=(
                            "Elige la herramienta adecuada al plan o tarea en el mensaje del usuario y a los datos "
                            "disponibles; si necesitas una herramienta que no está en la lista, dilo en texto sin "
                            "inventar resultados."
                        )
                    )
                ] + _msg_list
            _quant_autoexec_validation_intent = bool(
                (_lid or "").strip().lower() == "quant_trader"
                and _quant_user_requests_autoexec_validation(incoming)
                and not telegram_context_summarize_directive
            )
            if _quant_autoexec_validation_intent:
                _msg_list = [
                    SystemMessage(
                        content=(
                            "[DIRECTIVA_EVIDENCIA_AUTOEXEC] Para validar auto-ejecución debes usar evidencia real en este turno: "
                            "1) `read_sql` sobre finance_worker.trade_signals (conteo/estado/ib_order_id de señales ejecutadas), "
                            "2) `get_ibkr_portfolio` para estado real de posiciones/cash. "
                            "Si falta alguna evidencia, responde explícitamente que no se puede validar todavía y NO infieras resultados."
                        )
                    )
                ] + _msg_list
            _qp_ctx = state.get("quant_pipeline_context")
            if (
                (_lid or "").strip().lower() == "quant_trader"
                and isinstance(_qp_ctx, dict)
                and _quant_deterministic_cycle
                and _has_fetch_since_last_human
                and _has_eval_since_last_human
            ):
                _msg_list = [
                    SystemMessage(
                        content=(
                            "[DIRECTIVA_QUANT_PIPELINE_DETERMINISTA] El backend ya ejecutó ingesta/evaluación "
                            "(fetch -> portfolio -> evaluate_cfd_state). En este turno NO repitas esas tools; "
                            "usa el contexto de resultados para: "
                            "1) proponer señal (propose_trade_signal) con argumentos completos, o "
                            "2) interpretar estado y próximos pasos si no procede señal."
                        )
                    )
                ] + _msg_list
            _groq_msgs = _apply_provider_input_budget(_msg_list, provider=provider)
            _invoked_llm: Any = llm_with_tools
            if force_admin_sql:
                _fa = llm_force_admin_sql_on if sandbox_enabled else llm_force_admin_sql_off
                _invoked_llm = _fa or llm_with_tools
            elif force_pqrsd_fetch_canonical:
                _pf = llm_force_pqrsd_fetch_on if sandbox_enabled else llm_force_pqrsd_fetch_off
                _invoked_llm = _pf or llm_with_tools
            elif force_schema and not force_read_sql:
                _invoked_llm = (
                    llm_force_schema_on if sandbox_enabled else llm_force_schema_off
                )
            elif force_read_sql:
                _invoked_llm = (
                    llm_force_read_sql_on if sandbox_enabled else llm_force_read_sql_off
                )
            elif force_portfolio:
                _forced_pf = llm_force_portfolio_on if sandbox_enabled else llm_force_portfolio_off
                _invoked_llm = _forced_pf or llm_with_tools
            elif force_execute_approved_signal:
                _fex = (
                    llm_force_execute_approved_signal_on
                    if sandbox_enabled
                    else llm_force_execute_approved_signal_off
                )
                _invoked_llm = _fex or llm_with_tools
            elif force_quant_goals_evaluate_cfd:
                _fec = (
                    llm_force_evaluate_cfd_state_on
                    if sandbox_enabled
                    else llm_force_evaluate_cfd_state_off
                )
                _invoked_llm = _fec or llm_with_tools
            elif force_fmp:
                _forced_fmp = (
                    llm_force_fmp_calendar_on if force_fmp_calendar else llm_force_fmp_stock_on
                ) if sandbox_enabled else (
                    llm_force_fmp_calendar_off if force_fmp_calendar else llm_force_fmp_stock_off
                )
                _invoked_llm = _forced_fmp or llm_with_tools
            elif force_tavily:
                _ft = llm_force_tavily_on if sandbox_enabled else llm_force_tavily_off
                _invoked_llm = _ft or llm_with_tools
            elif force_reddit:
                _fr = None
                if _reddit_resolved_comments_url and _incoming_looks_like_reddit_post_url(
                    _reddit_resolved_comments_url
                ):
                    _fr = llm_force_reddit_post_on if sandbox_enabled else llm_force_reddit_post_off
                elif _incoming_has_reddit_share_path(incoming_for_reddit):
                    _fr = llm_force_reddit_search_on if sandbox_enabled else llm_force_reddit_search_off
                elif _incoming_looks_like_reddit_post_url(incoming_for_reddit):
                    _fr = llm_force_reddit_post_on if sandbox_enabled else llm_force_reddit_post_off
                if _fr is None:
                    _fr = llm_force_reddit_search_on if sandbox_enabled else llm_force_reddit_search_off
                if _fr is None:
                    _fr = llm_force_reddit_fallback_on if sandbox_enabled else llm_force_reddit_fallback_off
                _invoked_llm = _fr or llm_with_tools
            elif force_quant_propose_signal:
                # En 8B, forzar propose_trade_signal termina a menudo en args vacíos ({}).
                # Dejamos selección libre con tools para que el modelo emita args completos.
                _invoked_llm = llm_with_tools
            elif force_fetch_ib_gateway or force_quant_signal_fetch_ib:
                _ffig = llm_force_fetch_ib_gateway_on if sandbox_enabled else llm_force_fetch_ib_gateway_off
                _invoked_llm = _ffig or llm_with_tools
            elif force_fetch_market_data or force_quant_signal_fetch_md:
                _ffmd = llm_force_fetch_market_on if sandbox_enabled else llm_force_fetch_market_off
                _invoked_llm = _ffmd or llm_with_tools
            elif force_run_sandbox:
                _frs = llm_force_run_sandbox_on if sandbox_enabled else llm_force_run_sandbox_off
                _invoked_llm = _frs or llm_with_tools
            _llm_invoke_exc: BaseException | None = None
            try:
                from duckclaw.integrations.llm_providers import invoke_chat_model_with_transient_retries

                resp = invoke_chat_model_with_transient_retries(_invoked_llm, _groq_msgs)
                _lid_lower_for_reddit_patch = (_lid or "").strip().lower()
                if (
                    _lid_lower_for_reddit_patch in ("finanz", "quant_trader")
                    and resp is not None
                    and getattr(resp, "tool_calls", None)
                ):
                    _ru_share = _first_reddit_url_in_text(incoming_for_reddit)
                    if (
                        _ru_share
                        and _incoming_has_reddit_share_path(_ru_share)
                        and not _reddit_resolved_comments_url
                    ):
                        resp = _patch_ai_reddit_share_tool_calls(resp, _ru_share)
                    elif _reddit_resolved_comments_url:
                        resp = _patch_reddit_get_post_args_from_canonical_url(
                            resp, _reddit_resolved_comments_url
                        )
            except Exception as exc:
                _llm_invoke_exc = exc
                _log.warning("[%s] LLM invoke failed in agent_node: %s", _wl, exc, exc_info=True)
                from duckclaw.integrations.llm_providers import failure_provider_label_for_llm_invoke

                _pl_fail = failure_provider_label_for_llm_invoke(_invoked_llm, provider)
                resp = AIMessage(content=_agent_node_llm_failure_user_message(exc, provider=_pl_fail))
            tool_calls = getattr(resp, "tool_calls", None) or []
            _is_goals_tick = (
                str(incoming or "").strip().startswith("[SYSTEM_EVENT:")
                and "Revisión periódica de /goals" in str(incoming or "")
            )
            if force_portfolio and has_ibkr and _is_goals_tick and not tool_calls:
                _forced_tid = f"call_forced_ibkr_{int(time.time() * 1000)}"
                forced_tc = [{"name": "get_ibkr_portfolio", "args": {}, "id": _forced_tid, "type": "tool_call"}]
                try:
                    resp = resp.model_copy(update={"tool_calls": forced_tc})
                except Exception:
                    resp = AIMessage(content=str(getattr(resp, "content", "") or ""), tool_calls=forced_tc)
                tool_calls = getattr(resp, "tool_calls", None) or forced_tc
            _is_quant_forced_without_tools = (
                (_lid_l == "quant_trader")
                and not tool_calls
                and (
                    force_quant_signal_fetch_ib
                    or force_quant_signal_fetch_md
                    or force_execute_approved_signal
                    or force_quant_goals_evaluate_cfd
                    or force_fetch_ib_gateway
                    or force_fetch_market_data
                )
            )
            if _is_quant_forced_without_tools:
                _fallback_tool_name = (
                    "execute_approved_signal"
                    if force_execute_approved_signal
                    else (
                        "evaluate_cfd_state"
                        if force_quant_goals_evaluate_cfd
                        else (
                            "fetch_ib_gateway_ohlcv"
                            if (force_quant_signal_fetch_ib or force_fetch_ib_gateway)
                            else (
                                "fetch_market_data"
                                if (force_quant_signal_fetch_md or force_fetch_market_data)
                                else ""
                            )
                        )
                    )
                )
                if _fallback_tool_name:
                    _forced_tid = f"call_forced_quant_{int(time.time() * 1000)}"
                    forced_tc = [
                        {
                            "name": _fallback_tool_name,
                            "args": {},
                            "id": _forced_tid,
                            "type": "tool_call",
                        }
                    ]
                    try:
                        resp = resp.model_copy(update={"tool_calls": forced_tc})
                    except Exception:
                        resp = AIMessage(content=str(getattr(resp, "content", "") or ""), tool_calls=forced_tc)
                    tool_calls = getattr(resp, "tool_calls", None) or forced_tc
            if (_lid_l == "quant_trader") and force_quant_propose_signal and not tool_calls:
                _fallback_tool_name = (
                    "run_quant_signal_cycle"
                    if ("run_quant_signal_cycle" in tools_by_name)
                    else "propose_trade_signal"
                )
                _fallback_args = (
                    {
                        "mandate_id": "",
                        "ticker": _quant_primary_ticker,
                        "weight": 5.0,
                        "rationale": "Deterministic pipeline fallback after CFD evaluation.",
                        "signal_type": "ENTRY",
                        "execute_now": False,
                    }
                    if _fallback_tool_name == "run_quant_signal_cycle"
                    else {
                        "mandate_id": "",
                        "ticker": _quant_primary_ticker,
                        "weight": 5.0,
                        "rationale": "Deterministic pipeline fallback after CFD evaluation.",
                        "signal_type": "ENTRY",
                    }
                )
                _forced_tid = f"call_forced_quant_propose_{int(time.time() * 1000)}"
                forced_tc = [
                    {
                        "name": _fallback_tool_name,
                        "args": _fallback_args,
                        "id": _forced_tid,
                        "type": "tool_call",
                    }
                ]
                try:
                    resp = resp.model_copy(update={"tool_calls": forced_tc})
                except Exception:
                    resp = AIMessage(content=str(getattr(resp, "content", "") or ""), tool_calls=forced_tc)
                tool_calls = getattr(resp, "tool_calls", None) or forced_tc
            if tool_calls:
                _tc_names: list[Any] = []
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        _tc_names.append(tc.get("name"))
                    else:
                        _tc_names.append(getattr(tc, "name", None))
                _log.info("[%s] LLM tool_calls=%s", _wl, _tc_names)
            _resp_content = str(getattr(resp, "content", "") or "").strip()
            if _is_goals_tick and not tool_calls:
                # Ticks proactivos con sesión rebalance_hrp / overnight_gap_squeeze (o ya hubo sandbox en el hilo): no sustituir
                # la respuesta del modelo por el resumen genérico de «PnL positivo».
                _incoming_s = str(incoming or "")
                _inc_lower = _incoming_s.lower()
                _goals_hrp_context = "rebalance_hrp" in _inc_lower or "objective=rebalance_hrp" in _inc_lower
                _goals_overnight_context = (
                    "overnight_gap_squeeze" in _inc_lower
                    or "objective=overnight_gap_squeeze" in _inc_lower
                    or "overnight gap squeeze" in _inc_lower
                )
                _goals_hrp_from_sql = False
                for _m in state.get("messages", []):
                    if isinstance(_m, ToolMessage) and str(getattr(_m, "name", "") or "") == "read_sql":
                        _c = str(getattr(_m, "content", "") or "").lower()
                        if "rebalance_hrp" in _c or "objective" in _c and "rebalance" in _c:
                            _goals_hrp_from_sql = True
                            break
                if _goals_hrp_context or _goals_hrp_from_sql:
                    if (_resp_content or "").strip():
                        pass  # conservar veredicto del LLM (HRP / alineación)
                    else:
                        _hrp_stub = (
                            "Revision /goals (proactiva): objetivo de sesion **rebalance_hrp**. "
                            "Usa en el hilo la salida de `get_ibkr_portfolio` y `execute_sandbox_script` "
                            "(pesos HRP vs cartera); no apliques el resumen automatico de meta «PnL positivo» a este tick."
                        )
                        try:
                            resp = resp.model_copy(update={"content": _hrp_stub})
                        except Exception:
                            resp = AIMessage(content=_hrp_stub)
                elif _goals_overnight_context:
                    if (_resp_content or "").strip():
                        pass  # conservar veredicto del LLM (prep / gap / MOC)
                    else:
                        _ov_stub = (
                            "Revision /goals (proactiva): objetivo de sesion **overnight_gap_squeeze**. "
                            "Prioriza alineacion prep/MOC y gap squeeze segun el SYSTEM_EVENT; "
                            "no apliques el resumen automatico de meta «PnL positivo» a este tick."
                        )
                        try:
                            resp = resp.model_copy(update={"content": _ov_stub})
                        except Exception:
                            resp = AIMessage(content=_ov_stub)
                else:
                    _portfolio_tool_text = ""
                    _portfolio_tool_text_prev = ""
                    _seen_ibkr = 0
                    for _m in reversed(state.get("messages", [])):
                        if isinstance(_m, ToolMessage) and str(getattr(_m, "name", "") or "") == "get_ibkr_portfolio":
                            _seen_ibkr += 1
                            if not _portfolio_tool_text:
                                _portfolio_tool_text = str(getattr(_m, "content", "") or "").strip()
                                continue
                            _portfolio_tool_text_prev = str(getattr(_m, "content", "") or "").strip()
                            break
                    _total_value = ""
                    _positions = ""
                    _unreal_prev_txt = ""
                    if _portfolio_tool_text:
                        _m_total = re.search(r"Valor total:\s*\$([0-9,]+(?:\.[0-9]+)?)", _portfolio_tool_text)
                        _m_pos = re.search(r"Posiciones:\s*([0-9]+)", _portfolio_tool_text)
                        _m_unreal = re.search(
                            r"PnL no realizado total \(snapshot\):\s*\$([\-0-9,]+(?:\.[0-9]+)?)",
                            _portfolio_tool_text,
                        )
                        _total_value = _m_total.group(1) if _m_total else ""
                        _positions = _m_pos.group(1) if _m_pos else ""
                        _unreal_txt = _m_unreal.group(1) if _m_unreal else ""
                        if _portfolio_tool_text_prev:
                            _m_unreal_prev = re.search(
                                r"PnL no realizado total \(snapshot\):\s*\$([\-0-9,]+(?:\.[0-9]+)?)",
                                _portfolio_tool_text_prev,
                            )
                            _unreal_prev_txt = _m_unreal_prev.group(1) if _m_unreal_prev else ""
                    else:
                        _unreal_txt = ""
                    if _portfolio_tool_text and (_total_value or _positions):
                        if _unreal_txt:
                            try:
                                _unreal_val = float(_unreal_txt.replace(",", ""))
                            except Exception:
                                _unreal_val = 0.0
                            _chat_key = str(state.get("chat_id") or state.get("session_id") or "").strip()
                            _prev_unreal_val = (
                                _GOALS_PREV_UNREALIZED_PNL_BY_CHAT.get(_chat_key) if _chat_key else None
                            )
                            _pct_change = None
                            if _prev_unreal_val is None and _unreal_prev_txt:
                                try:
                                    _prev_unreal_val = float(_unreal_prev_txt.replace(",", ""))
                                except Exception:
                                    _prev_unreal_val = None
                            if _prev_unreal_val is not None:
                                # Base de comparación: valor absoluto del PnL previo para evitar signo invertido.
                                _den = abs(_prev_unreal_val)
                                if _den > 1e-9:
                                    _pct_change = ((_unreal_val - _prev_unreal_val) / _den) * 100.0
                            _state = "ALIGNED" if _unreal_val >= 0 else "MISALIGNED"
                            _act = (
                                "mantener sesion y seguir monitoreo HITL."
                                if _unreal_val >= 0
                                else "activar reduccion de riesgo y evitar nuevas señales hasta recuperar PnL>=0."
                            )
                            _fallback_text = (
                                "Revision /goals (proactiva): "
                                f"snapshot IBKR OK (valor total=${_total_value or 'N/D'}, posiciones={_positions or 'N/D'}, "
                                f"PnL no realizado=${_unreal_val:,.2f}). "
                                f"Meta 'PnL positivo': {_state}. Accion sugerida: {_act}"
                            )
                            if _prev_unreal_val is not None:
                                _fallback_text += f" PnL anterior=${_prev_unreal_val:,.2f}."
                            else:
                                _fallback_text += " PnL anterior=N/D."
                            if _pct_change is not None:
                                _fallback_text += f" Cambio vs anterior={_pct_change:+.2f}%."
                            else:
                                _fallback_text += " Cambio vs anterior=N/D."
                            if _chat_key:
                                _GOALS_PREV_UNREALIZED_PNL_BY_CHAT[_chat_key] = _unreal_val
                        else:
                            _fallback_text = (
                                "Revision /goals (proactiva): "
                                f"snapshot IBKR OK (valor total=${_total_value or 'N/D'}, posiciones={_positions or 'N/D'}). "
                                "Meta 'PnL positivo': estado parcial por falta de PnL realizado/no realizado en este snapshot. "
                                "Accion sugerida: extraer PnL por posicion y activar reduccion de riesgo si el agregado pasa a negativo."
                            )
                    elif _portfolio_tool_text:
                        _fallback_text = (
                            "Revision /goals (proactiva): snapshot IBKR recibido. "
                            "Meta 'PnL positivo': se requiere desglose de PnL realizado/no realizado para validar alineacion. "
                            "Accion sugerida: extraer PnL por posicion y aplicar regla de reduccion de riesgo."
                        )
                    else:
                        _fallback_text = ""
                    if _fallback_text:
                        try:
                            resp = resp.model_copy(update={"content": _fallback_text})
                        except Exception:
                            resp = AIMessage(content=_fallback_text)
            out = {**state, "messages": state["messages"] + [resp]}
            if _llm_invoke_exc is not None:
                from duckclaw.integrations.llm_providers import is_transient_inference_connection_error

                out["_duckclaw_worker_llm_invoke_failed"] = True
                out["_duckclaw_worker_llm_transient"] = bool(
                    is_transient_inference_connection_error(_llm_invoke_exc)
                )
                out["_duckclaw_worker_llm_failure_kind"] = type(_llm_invoke_exc).__name__
            else:
                for _k in (
                    "_duckclaw_worker_llm_invoke_failed",
                    "_duckclaw_worker_llm_transient",
                    "_duckclaw_worker_llm_failure_kind",
                ):
                    out.pop(_k, None)
            out.update(_identity_fields(state))
            return out

    def tools_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        from duckclaw.graphs.chat_heartbeat import (
            format_tool_heartbeat,
            heartbeat_message_for_tool,
            schedule_chat_heartbeat_dm,
        )
        from duckclaw.utils.formatters import format_reddit_mcp_reply_if_applicable

        _chat_ctx = state.get("chat_id") or state.get("session_id") or "default"
        _tenant_ctx = (state.get("tenant_id") or "").strip() or "default"
        _log_chat = format_chat_log_identity(str(_chat_ctx).strip() or "default", state.get("username"))
        set_log_context(tenant_id=_tenant_ctx, worker_id=worker_id, chat_id=_log_chat)
        if (
            "execute_order" in tools_by_name
            or "execute_approved_signal" in tools_by_name
            or "propose_trade_signal" in tools_by_name
        ):
            from duckclaw.forge.skills.quant_tool_context import (
                bind_quant_market_evidence_chat,
                set_quant_tool_chat_id,
                set_quant_tool_db_path,
                set_quant_tool_tenant_id,
                set_quant_tool_user_id,
            )

            bind_quant_market_evidence_chat(str(_chat_ctx))
            set_quant_tool_chat_id(str(_chat_ctx))
            set_quant_tool_tenant_id(_tenant_ctx)
            _q_uid = str(state.get("user_id") or "").strip() or str(_chat_ctx)
            set_quant_tool_user_id(_q_uid)
            set_quant_tool_db_path(str(path))
        _wl = _worker_log_label(worker_id)
        messages = state["messages"]
        last = messages[-1]
        tool_calls = getattr(last, "tool_calls", None) or []
        _tool_round = int(state.get("_tool_round") or 0) + 1
        new_msgs = list(messages)
        sandbox_enabled = _sandbox_enabled_for_state(state)
        tool_lookup = tools_by_name if sandbox_enabled else tools_by_name_sandbox_off
        sandbox_b64: str | None = state.get("sandbox_photo_base64") if isinstance(state.get("sandbox_photo_base64"), str) else None
        _hb_head = (state.get("subagent_instance_label") or "").strip() or None
        _hb_uname = (state.get("username") or "").strip() or None
        _hb_plan = (state.get("heartbeat_plan_title") or "").strip() or None
        _hb_tok = (state.get("outbound_telegram_bot_token") or "").strip() or None

        _duck_exts = list(getattr(spec, "duckdb_extensions", None) or [])
        use_ephemeral_parallel = (
            read_pool.read_pool_active_for_worker(spec)
            and read_pool.should_parallelize_ephemeral_tool_calls(tool_calls)
        )

        def _schedule_tool_heartbeat(tool_name: str) -> None:
            _htid = (state.get("tenant_id") or "default").strip() or "default"
            _hcid = str(state.get("chat_id") or state.get("session_id") or "").strip()
            _huid = str(state.get("user_id") or "").strip() or _hcid
            _elapsed = _heartbeat_elapsed_sec(state)
            schedule_chat_heartbeat_dm(
                _htid,
                _hcid,
                _huid,
                format_tool_heartbeat(
                    _hb_head,
                    heartbeat_message_for_tool(tool_name),
                    plan_title=_hb_plan,
                    elapsed_sec=_elapsed,
                ),
                log_worker_id=_hb_head,
                log_username=_hb_uname,
                log_plan_title=_hb_plan,
                outbound_bot_token=_hb_tok,
                routing_worker_id=worker_id,
            )

        if use_ephemeral_parallel:
            _log.info("[%s] tools_node: ephemeral read-pool parallel (%d calls)", _wl, len(tool_calls))
            n_workers = min(len(tool_calls), read_pool.read_pool_max_concurrency())

            def _parallel_job(idx_tc: tuple[int, dict[str, Any]]) -> tuple[int, str, str, str]:
                idx, tc = idx_tc
                name = (tc.get("name") or "").strip()
                args = tc.get("args") or {}
                tid = tc.get("id") or ""
                _schedule_tool_heartbeat(name)
                try:
                    if name == "read_sql":
                        q = str(args.get("query", "")) if isinstance(args, dict) else ""
                        content = read_pool.run_ephemeral_read_sql(
                            spec, path, path, shared_resolved, _duck_exts, q
                        )
                    elif name == "inspect_schema":
                        content = read_pool.run_ephemeral_inspect_schema(
                            path, path, shared_resolved, _duck_exts
                        )
                    else:
                        content = json.dumps({"error": f"Herramienta inesperada en read-pool: {name}"})
                except Exception as e:
                    content = f"Error: {e}"
                    _log.warning("[%s] ephemeral tool=%s failed: %s", _wl, name, e)
                _log.info(
                    "[%s] tool=%s | ephemeral | result_len=%d | preview=%r",
                    _wl,
                    name,
                    len(content),
                    content[:120] + ("..." if len(content) > 120 else ""),
                )
                return idx, tid, name, content

            ordered_slots: list[tuple[str, str, str] | None] = [None] * len(tool_calls)
            with ThreadPoolExecutor(max_workers=max(1, n_workers)) as pool:
                futs = [pool.submit(_parallel_job, (i, tc)) for i, tc in enumerate(tool_calls)]
                for fut in as_completed(futs):
                    idx, tid, name, content = fut.result()
                    ordered_slots[idx] = (tid, name, content)
            for i in range(len(tool_calls)):
                slot = ordered_slots[i]
                if slot is None:
                    tc = tool_calls[i]
                    new_msgs.append(
                        ToolMessage(
                            content=json.dumps({"error": "read_pool: resultado faltante"}),
                            tool_call_id=tc.get("id") or "",
                            name=(tc.get("name") or "").strip(),
                        )
                    )
                    continue
                tid, name, content = slot
                new_msgs.append(ToolMessage(content=content, tool_call_id=tid, name=name))
        else:
            for tc in tool_calls:
                name = (tc.get("name") or "").strip()
                args = tc.get("args") or {}
                tid = tc.get("id") or ""
                tool = tool_lookup.get(name)
                if tool:
                    try:
                        invoke_args: Any = args
                        if isinstance(args, dict):
                            invoke_args = {**args}
                        if name in (
                            "run_sandbox",
                            "run_browser_sandbox",
                            "pqrsd_run_identificacion_step1",
                            "execute_sandbox_script",
                        ):
                            if not str(invoke_args.get("worker_id") or "").strip():
                                invoke_args["worker_id"] = worker_id
                            if name in ("run_browser_sandbox", "pqrsd_run_identificacion_step1"):
                                _cid = str(state.get("chat_id") or state.get("session_id") or "").strip()
                                if _cid and not str(invoke_args.get("session_id") or "").strip():
                                    from duckclaw.graphs.novnc_registry import sanitize_chat_to_session_id

                                    invoke_args["session_id"] = sanitize_chat_to_session_id(_cid)
                        if name in ("pqrsd_upsert_radicacion_perfil", "pqrsd_registrar_radicacion_crm"):
                            if not isinstance(invoke_args, dict):
                                invoke_args = {}
                            _cid = str(state.get("chat_id") or state.get("session_id") or "").strip()
                            if _cid and not str(invoke_args.get("telegram_chat_id") or "").strip():
                                invoke_args["telegram_chat_id"] = _cid
                        if name == "get_browser_session_url":
                            if not isinstance(invoke_args, dict):
                                invoke_args = {}
                            _cid = str(state.get("chat_id") or state.get("session_id") or "").strip()
                            if _cid and not str(invoke_args.get("chat_id") or "").strip():
                                invoke_args["chat_id"] = _cid
                        if name in ("run_browser_sandbox", "pqrsd_run_identificacion_step1"):
                            from duckclaw.graphs.sandbox import ensure_browser_novnc_session

                            _sid = str(invoke_args.get("session_id") or "").strip()
                            _vnc_pre = ensure_browser_novnc_session(worker_id, _sid) if _sid else None
                            _schedule_run_browser_novnc_tool_heartbeat(
                                state,
                                routing_worker_id=worker_id,
                                vnc_url=_vnc_pre,
                                novnc_session_id=_sid or "",
                            )
                        else:
                            _schedule_tool_heartbeat(name)
                        if (
                            name == "run_sandbox"
                            and _lid == "bi_analyst"
                            and _sandbox_heartbeat_allowed(spec)
                        ):
                            from duckclaw.graphs.chat_heartbeat import is_chat_heartbeat_enabled

                            _htid = (state.get("tenant_id") or "default").strip() or "default"
                            _hcid = str(state.get("chat_id") or state.get("session_id") or "").strip()
                            if not is_chat_heartbeat_enabled(_htid, _hcid):
                                _send_sandbox_heartbeat_telegram(state)
                        result = tool.invoke(invoke_args)
                        content = str(result) if result is not None else "OK"
                        if name in ("run_sandbox", "run_browser_sandbox", "pqrsd_run_identificacion_step1"):
                            try:
                                payload = json.loads(content)
                                if isinstance(payload, dict) and payload.get("exit_code") == 0:
                                    fb = payload.get("figure_base64")
                                    if isinstance(fb, str) and len(fb) > 32:
                                        sandbox_b64 = fb
                            except (json.JSONDecodeError, TypeError):
                                pass
                            if not use_cm:
                                content = _compact_run_sandbox_tool_content_for_llm(
                                    content, _RUN_SANDBOX_TOOL_LLM_MAX_CHARS
                                )
                        if name.startswith("reddit_"):
                            content = format_reddit_mcp_reply_if_applicable(content)
                        _prev = content[:120] + ("..." if len(content) > 120 else "")
                        if name in ("pqrsd_run_identificacion_step1", "pqrsd_upsert_radicacion_perfil"):
                            import re as _re_pqrs

                            _prev = _re_pqrs.sub(
                                r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}",
                                "[email]",
                                _prev,
                            )
                            _prev = _re_pqrs.sub(r"\b\d{6,14}\b", "[digits]", _prev)
                        _log.info(
                            "[%s] tool=%s | result_len=%d | preview=%r",
                            _wl,
                            name,
                            len(content),
                            _prev,
                        )
                    except Exception as e:
                        content = f"Error: {e}"
                        _log.warning("[%s] tool=%s failed: %s", _wl, name, e)
                else:
                    if not sandbox_enabled and name in (
                        "run_sandbox",
                        "run_browser_sandbox",
                        "get_browser_session_url",
                        "pqrsd_run_identificacion_step1",
                    ):
                        content = "Sandbox deshabilitado en esta sesión. Actívalo con /sandbox on."
                    else:
                        content = f"Herramienta desconocida: {name}"
                    _log.warning(
                        "[%s] unknown/unavailable tool: %s (sandbox_enabled=%s)",
                        _wl,
                        name,
                        sandbox_enabled,
                    )
                new_msgs.append(ToolMessage(content=content, tool_call_id=tid, name=name))
        out: dict[str, Any] = {**state, "messages": new_msgs, "_tool_round": _tool_round}
        if sandbox_b64:
            out["sandbox_photo_base64"] = sandbox_b64
        out.update(_identity_fields(state))
        return out

    def reflector_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        """Finanz: tras errores de tools, LLM escribe lección en agent_beliefs (sin DELETE)."""
        from langchain_core.messages import HumanMessage

        if llm is None or not finanz_field_reflection_enabled(spec):
            out = {**state}
            out.update(_identity_fields(state))
            return out
        digest = collect_tool_error_digest(state.get("messages") or [])
        if not digest:
            out = {**state}
            out.update(_identity_fields(state))
            return out
        incoming_r = (state.get("incoming") or "").strip()
        instr = (
            "Eres un analista de fallos de herramientas. Dado el error abajo, produce SOLO un JSON válido con:\n"
            '  "context_trigger": string corto (palabras clave: nombre de tool, código de error, ticker si aplica), '
            "máximo 500 caracteres\n"
            '  "lesson_text": lección operativa en español, máximo 4000 caracteres; no inventes datos que no '
            "aparezcan en el error\n"
            '  "confidence_score": número entre 0.5 y 3.0 (utilidad esperada de recordar esta lección)\n'
            "Sin markdown ni texto fuera del objeto JSON.\n\n"
            f"Contexto del usuario (truncado): {incoming_r[:800]}\n\n"
            f"Salidas erróneas de herramientas:\n{digest}"
        )
        try:
            resp = llm.invoke([HumanMessage(content=instr)])
            text = getattr(resp, "content", None) or str(resp)
            parsed = parse_reflection_json(text)
            if parsed:
                bk = lesson_belief_key(parsed["context_trigger"], parsed["lesson_text"])
                persist_field_lesson(
                    db,
                    spec.schema_name,
                    bk,
                    parsed["context_trigger"],
                    parsed["lesson_text"],
                    parsed["confidence_score"],
                )
        except Exception:
            _log.debug("reflector_node failed", exc_info=True)
        out = {**state}
        out.update(_identity_fields(state))
        return out

    def set_reply(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        from duckclaw.utils.formatters import format_reddit_mcp_reply_if_applicable
        from duckclaw.utils import format_tool_reply
        from duckclaw.forge.atoms.user_reply_nl_synthesis import (
            finanz_repair_ibkr_snapshot_disconnect_paraphrase,
            incoming_has_context_summarize_directive,
            maybe_synthesize_reply,
            repair_summarize_new_context_egress,
            replace_bare_summarize_image_on_vlm_gateway_down,
            replace_bare_wrong_summarize_stored_echo,
            rescind_trivial_context_summary_reply,
            state_evidence_for_context_summary_rescind,
        )
        from duckclaw.graphs.chat_heartbeat import format_tool_heartbeat, schedule_chat_heartbeat_dm
        from duckclaw.integrations.llm_providers import (
            lc_message_content_to_text,
            sanitize_worker_reply_phase1,
            sanitize_worker_reply_text,
        )

        def _notify_final_heartbeat() -> None:
            _tid = (state.get("tenant_id") or "default").strip() or "default"
            _cid = str(state.get("chat_id") or state.get("session_id") or "").strip()
            _uid = str(state.get("user_id") or "").strip() or _cid
            _head = (state.get("subagent_instance_label") or "").strip() or None
            _un = (state.get("username") or "").strip() or None
            _pt = (state.get("heartbeat_plan_title") or "").strip() or None
            _elapsed = _heartbeat_elapsed_sec(state)
            _tok_f = (state.get("outbound_telegram_bot_token") or "").strip() or None
            schedule_chat_heartbeat_dm(
                _tid,
                _cid,
                _uid,
                format_tool_heartbeat(
                    _head,
                    "✅ Terminé los pasos con herramientas; te resumo el resultado en el siguiente mensaje.",
                    plan_title=_pt,
                    elapsed_sec=_elapsed,
                ),
                log_worker_id=_head,
                log_username=_un,
                log_plan_title=_pt,
                outbound_bot_token=_tok_f,
                routing_worker_id=str(getattr(spec, "worker_id", "") or "").strip() or None,
            )

        msgs = state.get("messages") or []
        last = msgs[-1] if msgs else None
        reply = lc_message_content_to_text(last) if last else ""
        reply = sanitize_worker_reply_phase1(reply)
        _inc_for_ctx = (state.get("incoming") or state.get("input") or "").strip()
        reply = replace_bare_wrong_summarize_stored_echo(reply, incoming=_inc_for_ctx)
        reply = replace_bare_summarize_image_on_vlm_gateway_down(reply, incoming=_inc_for_ctx)
        reply = repair_summarize_new_context_egress(reply, incoming=_inc_for_ctx)
        if (getattr(spec, "worker_id", "") or "").strip().lower() == "finanz":
            from duckclaw.forge.skills.quant_market_bridge import (
                finanz_reconcile_reply_with_fetch_market_tool,
            )

            reply = finanz_reconcile_reply_with_fetch_market_tool(msgs, reply)
        reply = format_reddit_mcp_reply_if_applicable(reply)
        suppress_egress = bool(state.get("suppress_subagent_egress"))

        def _nl_user_ask() -> str:
            inc = state.get("incoming") or state.get("input") or ""
            return (inc.strip() if isinstance(inc, str) else str(inc or "")).strip()

        def _apply_nl_synthesis(candidate: str) -> str:
            return maybe_synthesize_reply(llm, spec=spec, user_ask=_nl_user_ask(), reply_candidate=candidate)

        def _repair_finanz_ibkr_egress(candidate: str) -> str:
            return finanz_repair_ibkr_snapshot_disconnect_paraphrase(
                msgs,
                candidate,
                worker_id=str(getattr(spec, "worker_id", "") or ""),
            )

        if not msgs:
            out_empty = {**state, "reply": "Sin respuesta generada."}
            out_empty.update(_identity_fields(state))
            return out_empty
        _embedded_invokes = extract_embedded_json_tool_invokes(reply)
        if _embedded_invokes:
            from duckclaw.utils import format_tool_reply

            # read_sql (cuentas locales) antes que broker, alineado con el system prompt Finanz.
            _embed_order = {"read_sql": 0, "get_ibkr_portfolio": 1}
            _embedded_invokes = sorted(
                _embedded_invokes, key=lambda t: (_embed_order.get(t[0], 99), t[0])
            )
            sandbox_enabled = _sandbox_enabled_for_state(state)
            tool_lookup = tools_by_name if sandbox_enabled else tools_by_name_sandbox_off
            for name, _params in _embedded_invokes:
                if name not in tool_lookup:
                    _log.warning(
                        "[%s] assistant JSON tool not in registry: %s (sandbox_tools=%s)",
                        getattr(spec, "worker_id", "?"),
                        name,
                        sandbox_enabled,
                    )
                    err = json.dumps(
                        {"error": f"Herramienta no disponible en este modo: {name}"},
                        ensure_ascii=False,
                    )
                    _eb = sanitize_worker_reply_text(_apply_nl_synthesis(format_tool_reply(err)))
                    out_bad = {**state, "reply": _eb, "messages": msgs}
                    out_bad.update(_identity_fields(state))
                    return out_bad
            try:
                _parts: list[str] = []
                for name, params in _embedded_invokes:
                    result = tool_lookup[name].invoke(params)
                    _parts.append(f"### {name}\n{format_tool_reply(result)}")
                _combined = "\n\n".join(_parts)
                _notify_final_heartbeat()
                _formatted = sanitize_worker_reply_text(
                    _repair_finanz_ibkr_egress(_apply_nl_synthesis(_combined))
                )
                out_tool = {**state, "reply": _formatted, "internal_reply": _formatted, "messages": msgs}
                out_tool.update(_identity_fields(state))
                return out_tool
            except Exception as e:
                _log.warning(
                    "[%s] JSON tool invoke failed (embedded multi/single): %s",
                    getattr(spec, "worker_id", "?"),
                    e,
                    exc_info=True,
                )
                err = json.dumps(
                    {
                        "error": str(e),
                        "hint": "Si el error menciona lock de DuckDB, cierra otras conexiones (CLI, IDE) a ese .duckdb.",
                    },
                    ensure_ascii=False,
                )
                _ee = sanitize_worker_reply_text(_apply_nl_synthesis(format_tool_reply(err)))
                out_err = {**state, "reply": _ee, "messages": msgs}
                out_err.update(_identity_fields(state))
                return out_err
        reply = _repair_finanz_ibkr_egress(_apply_nl_synthesis(reply or ""))
        _rescind_incoming = state_evidence_for_context_summary_rescind(state)
        reply = rescind_trivial_context_summary_reply(
            llm, spec, incoming=_rescind_incoming, reply_candidate=reply or ""
        )
        reply = format_reddit_mcp_reply_if_applicable(reply or "")
        if not suppress_egress:
            _notify_final_heartbeat()
        try:
            from duckclaw.forge.atoms.job_hunter_output_validator import (
                job_hunter_blocked_reply_message,
                job_hunter_reply_should_block,
                spec_is_job_hunter as _jh_spec_check,
            )

            if reply and _jh_spec_check(spec):
                blocked, _reason = job_hunter_reply_should_block(reply)
                if blocked and _reason:
                    _log.warning(
                        "Job-Hunter egress blocked (worker_id=%s): %s",
                        getattr(spec, "worker_id", "?"),
                        _reason,
                    )
                    reply = job_hunter_blocked_reply_message(_reason)
        except Exception:
            pass
        try:
            from duckclaw.forge.atoms.quant_price_validator import quant_reply_price_audit
            from duckclaw.forge.atoms.quant_price_validator import enforce_visual_evidence_rule

            # Turnos /context (SUMMARIZE_*): sin auditorías cuánticas/VLM que puedan sustituir el resumen.
            if reply and not incoming_has_context_summarize_directive(_rescind_incoming):
                new_v, vreason = enforce_visual_evidence_rule(
                    incoming=(state.get("incoming") or ""),
                    messages=msgs,
                    reply=reply,
                    db=db,
                    spec=spec,
                )
                if vreason:
                    _log.warning("Finanz visual evidence audit: %s", vreason)
                    reply = new_v
                new_r, qreason = quant_reply_price_audit(db, spec, reply, messages=msgs)
                if qreason:
                    _log.warning("Finanz quant price audit: %s", qreason)
                    reply = new_r
        except Exception:
            pass
        try:
            from duckclaw.forge.atoms.job_hunter_output_validator import spec_is_job_hunter as _jh_spec_check

            _inc_text = (state.get("incoming") or state.get("input") or "").strip().lower()
            if reply and _jh_spec_check(spec) and "job_opportunity_tracking" in _inc_text and "a2a" in reply.lower():
                reply = re.sub(r"\bA2A\b\s*", "", reply, flags=re.IGNORECASE)
            if reply and _jh_spec_check(spec) and "job_opportunity_tracking" in _inc_text:
                reply = re.sub(
                    r"#\s*📊\s*MISIÓN\s+JOB_OPPORTUNITY_TRACKING\s*-\s*COMPLETADA",
                    "# 📊 SEGUIMIENTO DE VACANTE - COMPLETADO",
                    reply,
                    flags=re.IGNORECASE,
                )
                reply = re.sub(
                    r"\bMisión completada exitosamente\.\b",
                    "Registro completado exitosamente.",
                    reply,
                    flags=re.IGNORECASE,
                )
        except Exception:
            pass
        try:
            if (getattr(spec, "worker_id", "") or "").strip() == "PQRSD-Assistant" and reply:
                from duckclaw.forge.atoms.pqrsd_registration_egress_guard import (
                    pqrsd_guard_registration_egress,
                )
                from duckclaw.graphs.manager_graph import _worker_tool_names_from_messages

                _tn = _worker_tool_names_from_messages(list(msgs) if msgs else None)
                reply = pqrsd_guard_registration_egress(
                    reply,
                    _tn,
                    session_id=str(state.get("session_id") or state.get("chat_id") or ""),
                )
        except Exception:
            pass
        reply = sanitize_worker_reply_text(reply or "")
        if (not reply or reply.strip().lower() in ("sin respuesta.", "sin respuesta")) and msgs:
            from langchain_core.messages import ToolMessage

            for _m in reversed(msgs):
                if isinstance(_m, ToolMessage):
                    _fallback = sanitize_worker_reply_text(format_tool_reply(_m.content))
                    if _fallback:
                        reply = _fallback
                        break
        try:
            from duckclaw.graphs.conversation_traces import sync_final_assistant_egress_in_langchain_messages

            sync_final_assistant_egress_in_langchain_messages(msgs, reply or "")
        except Exception:
            pass
        if suppress_egress:
            out = {**state, "reply": "", "internal_reply": (reply or ""), "messages": msgs}
        else:
            out = {**state, "reply": reply or "", "internal_reply": (reply or ""), "messages": msgs}
        sb = (state.get("sandbox_photo_base64") or "").strip()
        if sb:
            out["sandbox_photo_base64"] = sb
        out.update(_identity_fields(state))
        return out

    def should_continue(state: dict) -> str:
        last = state["messages"][-1]
        _has_tools = bool(getattr(last, "tool_calls", None))
        return "tools" if _has_tools else "end"

    # Context-Guard (FactChecker + SelfCorrection) para workers con catalog_retriever
    context_guard_config = getattr(spec, "context_guard_config", None) or {}
    context_guard_enabled = (
        bool(context_guard_config.get("enabled", False))
        and "catalog_retriever" in (spec.skills_list or [])
    )
    max_retries = int(context_guard_config.get("max_retries", 2))

    def fact_check_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        from duckclaw.forge.atoms.validators import fact_checker_node as _fc
        return _fc(state, llm, max_retries=max_retries)

    def self_correction_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        from duckclaw.forge.atoms.validators import self_correction_node as _sc
        return _sc(state, llm)

    def handoff_reply_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        from duckclaw.forge.atoms.validators import handoff_reply_node as _hr
        return _hr(state)

    def route_after_fact_check(state: dict) -> str:
        return state.get("context_guard_route", "approved")

    def homeostasis_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        """HomeostasisNode: Percepción-Sorpresa-Restauración-Actualización. Fase 1: pass-through (tabla ya creada en run_schema).
        IMPORTANTE: retornar state para preservar input/incoming; retornar {} vacío hace que LangGraph pierda el estado."""
        return state

    graph = StateGraph(dict)
    graph.add_node("prepare", prepare_node)
    if use_cm:
        graph.add_node("context_monitor", context_monitor_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    if finanz_field_reflection_enabled(spec) and llm is not None:
        graph.add_node("reflector", reflector_node)
    graph.add_node("set_reply", set_reply)
    if context_guard_enabled:
        graph.add_node("fact_check", fact_check_node)
        graph.add_node("self_correction", self_correction_node)
        graph.add_node("handoff_reply", handoff_reply_node)
    if getattr(spec, "homeostasis_config", None):
        graph.add_node("homeostasis", homeostasis_node)
        graph.set_entry_point("homeostasis")
        graph.add_edge("homeostasis", "prepare")
    else:
        graph.set_entry_point("prepare")
    if use_cm:
        graph.add_edge("prepare", "context_monitor")
        graph.add_edge("context_monitor", "agent")
    else:
        graph.add_edge("prepare", "agent")
    if context_guard_enabled:
        graph.add_conditional_edges(
            "agent", should_continue,
            {"tools": "tools", "end": "fact_check"},
        )
        graph.add_conditional_edges(
            "fact_check", route_after_fact_check,
            {"approved": "set_reply", "correct": "self_correction", "handoff": "handoff_reply"},
        )
        graph.add_edge("self_correction", "fact_check")
        graph.add_edge("handoff_reply", END)
    else:
        graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": "set_reply"})
    _tools_dest = "context_monitor" if use_cm else "agent"
    _fr_graph = finanz_field_reflection_enabled(spec) and llm is not None

    def route_after_tools(state: dict) -> str:
        if _fr_graph and last_tool_batch_has_error(state.get("messages") or []):
            return "reflector"
        return "continue"

    if _fr_graph:
        graph.add_conditional_edges(
            "tools",
            route_after_tools,
            {"reflector": "reflector", "continue": _tools_dest},
        )
        graph.add_edge("reflector", _tools_dest)
    elif use_cm:
        graph.add_edge("tools", "context_monitor")
    else:
        graph.add_edge("tools", "agent")
    graph.add_edge("set_reply", END)

    compiled = graph.compile()
    compiled._worker_spec = spec
    compiled._worker_db = db
    return compiled


def list_workers(templates_root: Optional[Path] = None) -> list[str]:
    """Return worker_id for each template in templates/workers/."""
    if templates_root is not None:
        workers_dir = templates_root / "templates" / "workers"
    else:
        try:
            from duckclaw.forge import WORKERS_TEMPLATES_DIR
            workers_dir = WORKERS_TEMPLATES_DIR
        except ImportError:
            # packages/agents/src/duckclaw/workers -> packages/agents
            root = Path(__file__).resolve().parent.parent.parent.parent
            workers_dir = root / "templates" / "workers"
    if not workers_dir.is_dir():
        return []
    return [d.name for d in workers_dir.iterdir() if d.is_dir() and (d / "manifest.yaml").is_file()]
