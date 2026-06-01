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
from urllib.parse import parse_qs, urlparse

_log = logging.getLogger(__name__)

from pathlib import Path
from typing import Any, Literal, Optional

from duckclaw.db_write_queue import enqueue_duckdb_write_sync, poll_task_status_sync
try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore[misc, assignment]

from duckclaw.integrations.telegram import effective_telegram_bot_token_outbound
from duckclaw.utils.logger import format_chat_log_identity, log_tool_execution_sync, set_log_context
from duckclaw.utils.telegram_markdown_v2 import llm_markdown_to_telegram_html
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.guardrails.loader import load_guardrail
from duckclaw.workers import read_pool
from duckclaw.graphs.proactive_review_markers import proactive_review_event_phrase_in_text
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

from duckclaw.workers.worker_ids import (
    MARKET_WORKERS,
    PLOT_CAPABLE_WORKERS,
    WORKER_FINANZ,
    WORKER_PQRSD_ASSISTANT,
    WORKER_QUANT_TRADER,
    is_finanz,
    is_market_worker,
    is_pqrsd_assistant,
    is_quant_trader,
    normalize_worker_id,
)

_NO_TASK_PATTERN = re.compile(
    r"^(hola|hi|hey|buenos?\s*d[ií]as?|buenas?\s*tardes?|buenas?\s*noches?|"
    r"qu[eé]\s*tal|qu[eé]\s*hay|saludos?|hello|ciao|adios?|chao)\s*[!.]?$",
    re.IGNORECASE,
)

# Debe coincidir con duckclaw.graphs.manager_graph._LONE_HTTP_URL_ONLY_LINE.
_LONE_HTTP_URL_ONLY_LINE = re.compile(r"^\s*https?://[^\s]+\s*$", re.I)


def quant_trader_lone_reddit_url_message(logical_worker_id: str, incoming: str, reddit_anchor_url: Optional[str]) -> bool:
    """
    Quant pegó sólo una URL de Reddit sin directiva SUMMARIZE_*: permite force_reddit
    (evita respuesta texto sin reddit_*).
    """
    if not is_quant_trader(logical_worker_id):
        return False
    if not reddit_anchor_url:
        return False
    return bool(_LONE_HTTP_URL_ONLY_LINE.match((incoming or "").strip()))

# Preguntas por filas/contenido (no catálogo). Incluye «hay algo en la tabla X» (evita confundir con listar tablas).
_TABLE_CONTENT_PHRASE = re.compile(
    r"\b(que\s+hay\s+en\s+la\s+tabla|qué\s+hay\s+en\s+la\s+tabla|"
    r"hay\s+algo\s+en\s+(la\s+)?tabla|hay\s+datos\s+en\s+(la\s+)?tabla|"
    r"contenido\s+de\s+la\s+tabla|muestr(a|ame)\s+la\s+tabla|ver\s+datos\s+de\s+la\s+tabla|"
    r"registros?\s+de\s+la\s+tabla|filas?\s+de\s+la\s+tabla|select\s+\*\s+from|select\s+.+\s+from)\b",
    re.IGNORECASE,
)


def incoming_is_schema_query_heuristic(text: str) -> bool:
    """
    ¿Forzar inspect_schema? No si el usuario pegó sólo una URL HTTP(S): el path puede
    contener palabras como «estructura» sin relacionarse con DuckDB.
    Exportado para tests.
    """
    if not text or not text.strip():
        return False
    if bool(_LONE_HTTP_URL_ONLY_LINE.match(text.strip())):
        return False
    t = text.strip().lower()
    if "read_sql" in t and "job_opportunities" in t:
        return False
    if re.search(r"\btabla\s+o\s+lista\b", t):
        return False
    if _TABLE_CONTENT_PHRASE.search(t):
        return False
    return any(
        k in t
        for k in ("tablas", "tabla", "duckdb", "esquema", "schema", "estructura", "qué tablas", "que tablas")
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

# Cache en memoria por chat para comparar PnL entre ticks consecutivos de /crons.
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


_FINANZ_LOCAL_ACCOUNT_NAMES = (
    "bancolombia",
    "nequi",
    "davivienda",
    "efectivo",
    "global 66",
    "global66",
    "scotiabank",
    "cívica",
    "civica",
    "tarjeta cívica",
    "tarjeta civica",
    "nu",
)


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
    # p. ej. «Actualiza el efectivo a 46400 COP» (sin palabra «saldo» ni «cuenta»)
    if any(name in t for name in _FINANZ_LOCAL_ACCOUNT_NAMES) and (
        "cop" in t or "peso" in t or re.search(r"\b\d[\d.,]*\b", t)
    ):
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


def _finanz_hallucinated_balance_write_reply(incoming: str, content: str) -> bool:
    """True si el modelo afirmó actualizar saldo sin evidencia de admin_sql en el turno."""
    if not _is_finanz_local_account_write_query(incoming):
        return False
    body = (content or "").strip().lower()
    if not body:
        return False
    markers = ("✅", "actualizad", "actualizado", "quedó en", "quedo en", "nuevo saldo")
    return any(m in body for m in markers)


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
            r"mis\s+cuentas\s+bancarias|cuentas\s+bancarias|estado\s+actual\s+de\s+mis\s+cuentas|"
            r"estatus\s+de\s+mis\s+cuentas)\b",
            t,
        )
    )


def _finanz_should_force_current_time(text: str) -> bool:
    """
    Finanz: ancla reloj COT al inicio del turno (antes de read_sql / admin_sql).
    Solo turnos de ledger (deudas, cuentas, presupuestos, vencimientos); no VLM/URLs/noticias.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    low = raw.lower()
    if "[system_directive:" in low:
        return False
    if low.startswith("[system_event:"):
        return False
    if re.match(r"^(gracias|muchas\s+gracias|ok\.?|vale\.?|listo\.?|perfecto\.?|entendido\.?)\s*!?$", low):
        return False
    if re.search(
        r"\b(ejecuta|corre|run|script|c[oó]digo|python|bash|programa|sandbox)\b",
        low,
    ):
        return False
    if "[vlm_context" in low or "contexto visual adjunto:" in low:
        return False
    if re.search(r"https?://", low) or "reddit.com" in low:
        return False
    if _is_finanz_debts_query(raw):
        return True
    if _is_finanz_local_accounts_query(raw):
        return True
    if _is_finanz_budgets_query(raw):
        return True
    if re.search(
        r"\b("
        r"pasar\s+(la\s+)?deuda|"
        r"mover\s+(la\s+)?(deuda|cuota)|"
        r"de\s+mayo\s+a\s+junio|"
        r"vencimient|"
        r"cuota\s+(de|del)"
        r")\b",
        low,
    ):
        return True
    return False


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


def _is_finanz_validate_db_intent(text: str) -> bool:
    """
    Usuario exige comprobar estado real en DuckDB (evidencia 2026-05-12: modelo responde sin tool_calls
    o contradice read_sql). Obliga read_sql en el primer turno.
    """
    if not text or not text.strip():
        return False
    t = text.strip().lower()
    if "[system_directive:" in t:
        return False
    if any(
        p in t
        for p in (
            "no estás usando tools",
            "no usas tools",
            "no usa tools",
            "sin herramientas",
            "sin tools",
            "usa read_sql",
            "usar read_sql",
            "usa las herramientas",
            "debes usar tools",
        )
    ):
        return True
    if re.search(r"\b(valida|verifica|comprueba|confirma)\b", t) and any(
        k in t for k in ("db", "duckdb", "base de datos", "en la base", "valores en")
    ):
        return True
    if "consulta" in t and any(k in t for k in ("duckdb", "base de datos", "en la db")):
        return True
    return False


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


def _quant_trader_vlm_incoming_suggests_market_figure(text: str) -> bool:
    """
    True si el turno trae payload VLM con decimal tipo cotización (p. ej. 465.00 en captura Bloomberg).
    Evidencia pm2: tools usadas=ninguna + Regla de Evidencia Única pese a plan con read_sql.
    Excluye metadatos [VLM_CONTEXT … confidence=0.85] para no forzar read_sql en noticias sin precio.
    """
    raw = text or ""
    if "[VLM_CONTEXT" not in raw and "contexto visual adjunto:" not in raw.lower():
        return False
    body = re.sub(r"\[VLM_CONTEXT[^\]]*\]", "", raw, flags=re.IGNORECASE)
    return bool(re.search(r"(?:\$\s*)?\b\d{1,6}\.\d{2,6}\b", body))


def _duckclaw_env_truthy(name: str) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _quant_ohlcv_context_summary_forced_fetch_enabled() -> bool:
    """Opt-in: forzar ingesta OHLCV en turnos SUMMARIZE_* cuando el texto pide velas explícitas."""
    return _duckclaw_env_truthy("DUCKCLAW_QUANT_OHLCV_ON_CONTEXT_SUMMARY")


def _quant_summarize_allows_forced_ohlcv_fetch(incoming: str, worker_lid: str) -> bool:
    """SUMMARIZE_* no bloquea fetch_market_data si Quant + env + heurística OHLCV del usuario."""
    if not _quant_ohlcv_context_summary_forced_fetch_enabled():
        return False
    if not is_quant_trader(worker_lid):
        return False
    return _finanz_user_requests_ohlcv_ingest(incoming)


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
    if "/execute-signal" in low or "/execute_signal" in low:
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


def _quant_trader_should_force_current_time(text: str) -> bool:
    """
    Quant: ancla reloj COT post-LLM solo en turnos operativos (señales, portfolio, intradía).
    No VLM/URLs/noticias puras; el encabezado con HH:MM se cubre vía _response_mentions_wall_clock.
    """
    raw = (text or "").strip()
    if not raw:
        return False
    low = raw.lower()
    if "[system_directive:" in low:
        return False
    if low.startswith("[system_event:"):
        return False
    if re.match(r"^(gracias|muchas\s+gracias|ok\.?|vale\.?|listo\.?|perfecto\.?|entendido\.?)\s*!?$", low):
        return False
    if "[vlm_context" in low or "contexto visual adjunto:" in low:
        return False
    if re.search(r"https?://", low) or "reddit.com" in low:
        return False
    if _quant_user_requests_new_trade_signal(raw):
        return True
    if _quant_user_requests_execute_approved_signal(raw):
        return True
    if _quant_user_requests_autoexec_validation(raw):
        return True
    if _quant_is_proceed_like(raw):
        return True
    if re.search(
        r"\b(portfolio|ibkr|posiciones|get_ibkr_portfolio|cuenta\s+paper|cuenta\s+live)\b",
        low,
    ):
        return True
    if re.search(
        r"\b(apertura|intrad[ií]a|moc|overnight|gap[\s-]?down|gap[\s-]?up|precio\s+intrad[ií]a)\b",
        low,
    ):
        return True
    if _finanz_user_requests_ohlcv_ingest(raw):
        return True
    if _quant_extract_tickers(raw) and re.search(
        r"\b(precio|cierre|snapshot|ohlcv|cotizaci[oó]n|velas?)\b",
        low,
    ):
        return True
    return False


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


def _incoming_has_vlm_context(text: str) -> bool:
    low = (text or "").lower()
    return "[vlm_context" in low or "contexto visual adjunto:" in low


def _spec_logical_worker_id(spec: Any) -> str:
    return (getattr(spec, "logical_worker_id", None) or getattr(spec, "worker_id", "") or "").strip()


def _quant_gct_only_vlm_turn(
    messages: list[Any],
    incoming: str,
    *,
    last_human_idx: int,
    already_has_tool_result: bool,
) -> bool:
    if not _incoming_has_vlm_context(incoming):
        return False
    if not already_has_tool_result:
        return False
    if not _quant_tool_called_since(messages, last_human_idx, "get_current_time"):
        return False
    from langchain_core.messages import ToolMessage

    tools_since = [
        str(getattr(m, "name", "") or "")
        for m in messages[max(0, last_human_idx + 1) :]
        if isinstance(m, ToolMessage)
    ]
    return bool(tools_since) and all(t == "get_current_time" for t in tools_since)


def _parse_get_current_time_json(text: str) -> dict[str, Any] | None:
    raw = (text or "").strip()
    if not raw.startswith("{"):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if not {"iso_8601", "day_of_week", "date", "time"}.issubset(set(data.keys())):
        return None
    return data


def _reply_is_get_current_time_json_only(text: str) -> bool:
    return _parse_get_current_time_json(text or "") is not None


def _reply_is_fetch_market_data_json_only(text: str) -> bool:
    raw = (text or "").strip()
    if not raw.startswith("{"):
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, dict):
        return False
    return data.get("status") == "ok" and isinstance(data.get("ticker"), str)


def _strip_tool_label_prefix(text: str) -> str:
    """Quita prefijos tipo ``read_sql:`` que el LLM a veces pega antes del JSON crudo."""
    raw = (text or "").strip()
    m = re.match(r"^[a-z][a-z0-9_]*:\s*", raw, re.IGNORECASE)
    if m:
        return raw[m.end() :].strip()
    return raw


def _looks_like_finanz_ledger_json_rows(data: list[Any]) -> bool:
    if not data or not isinstance(data[0], dict):
        return False
    keys = set(data[0].keys())
    if "timestamp" in keys and "close" in keys:
        return True
    if {"id", "amount"} <= keys or {"description", "creditor"} <= keys:
        return True
    if {"balance", "currency"} <= keys or {"name", "balance"} <= keys:
        return True
    return False


def _reply_is_read_sql_json_only(text: str) -> bool:
    """True when egress is a raw read_sql JSON array (OHLCV o ledger Finanz), not prose."""
    raw = _strip_tool_label_prefix(text or "")
    if not raw.startswith("["):
        return False
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False
    if not isinstance(data, list) or not data:
        return False
    return _looks_like_finanz_ledger_json_rows(data)


def _reply_is_tool_label_json_echo(text: str) -> bool:
    """Eco ``tool_name: [{...`` sin síntesis (común en Finanz tras read_sql)."""
    raw = (text or "").strip()
    return bool(re.match(r"^[a-z][a-z0-9_]*:\s*[\[{]", raw, re.IGNORECASE))


def _reply_is_quant_tool_json_echo(text: str) -> bool:
    return (
        _reply_is_get_current_time_json_only(text)
        or _reply_is_fetch_market_data_json_only(text)
        or _reply_is_read_sql_json_only(text)
        or _reply_is_tool_label_json_echo(text)
    )


def _market_worker_egress_brand(worker_id: str | None) -> str:
    lid = normalize_worker_id(worker_id)
    if lid == WORKER_FINANZ:
        return "Finanz"
    if lid == WORKER_QUANT_TRADER:
        return "Quant-Trader"
    return (worker_id or "Worker").strip() or "Worker"


_QUANT_EGRESS_SYNTHESIS_TOOLS = frozenset(
    {
        "tavily_search",
        "run_browser_sandbox",
        "reddit_get_post",
        "fetch_market_data",
        "read_sql",
        "get_ibkr_portfolio",
        "inspect_macro_pgq",
        "inspect_schema",
    }
)


def _incoming_is_lone_http_url(text: str) -> bool:
    return bool(_LONE_HTTP_URL_ONLY_LINE.match((text or "").strip()))


def _incoming_is_portfolio_query(text: str) -> bool:
    """Consulta de portfolio IBKR (no cuentas bancarias locales Finanz)."""
    if not text or not text.strip():
        return False
    t = text.strip().lower()
    if any(k in t for k in ("transacciones", "gastos", "compras", "presupuesto")):
        return False
    if any(k in t for k in ("tablas", "tabla", "duckdb", "esquema", "schema", "estructura", "qué tablas", "que tablas")):
        return False
    if any(k in t for k in ("cuenta de ", "cuenta bancolombia", "bancolombia", "en bancolombia", "saldo en mi cuenta")):
        return False
    if any(k in t for k in ("portfolio total", "en total", "resumen de todo", "cuánto tengo en total", "cuanto tengo en total")):
        return False
    if _is_finanz_local_accounts_query(text):
        return False
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


def _user_explicitly_requests_ibkr_portfolio(text: str) -> bool:
    low = (text or "").strip().lower()
    if not low:
        return False
    if re.search(r"\bget_ibkr_portfolio\b", low):
        return True
    return bool(re.search(r"\b(usa|usar|ejecuta|llama)\s+(ibkr|get_ibkr_portfolio)\b", low))


def _ibkr_disabled_chat_hint() -> str:
    return (
        "IBKR está desactivado en este chat (`/ibkr off`). "
        "Para snapshot del VPS, envía `/ibkr on --mode paper` o `/ibkr on --mode live` y repite la consulta."
    )


def _quant_vlm_post_tools_synthesis(
    messages: list[Any] | None,
    incoming: str,
    *,
    last_human_idx: int,
    already_has_tool_result: bool,
) -> bool:
    """Cualquier tool sustantiva (≠ get_current_time) → síntesis en prosa por defecto, no JSON crudo."""
    if not already_has_tool_result:
        return False
    from langchain_core.messages import ToolMessage

    tools_since = [
        str(getattr(m, "name", "") or "")
        for m in (messages or [])[max(0, last_human_idx + 1) :]
        if isinstance(m, ToolMessage)
    ]
    if not tools_since:
        return False
    substantive = [t for t in tools_since if t != "get_current_time"]
    if substantive:
        return True
    has_vlm = _incoming_has_vlm_context(incoming)
    has_lone_url = _incoming_is_lone_http_url(incoming)
    if not (has_vlm or has_lone_url):
        return False
    if has_lone_url and not has_vlm:
        return any(t in _QUANT_EGRESS_SYNTHESIS_TOOLS for t in tools_since)
    return True


def _market_worker_gct_only_lone_url_no_repair(
    incoming: str,
    messages: list[Any] | None,
    *,
    last_human_idx: int,
) -> bool:
    """Lone URL + solo get_current_time: no síntesis ni egress repair (Infobae sin fetch)."""
    if not _incoming_is_lone_http_url(incoming) or _incoming_has_vlm_context(incoming):
        return False
    from langchain_core.messages import ToolMessage

    tools_since = [
        str(getattr(m, "name", "") or "")
        for m in (messages or [])[max(0, last_human_idx + 1) :]
        if isinstance(m, ToolMessage)
    ]
    return tools_since == ["get_current_time"]


def _market_worker_needs_egress_repair(
    messages: list[Any] | None,
    incoming: str,
    reply: str,
    *,
    last_human_idx: int,
    worker_id: str | None,
) -> bool:
    """Finanz/Quant: reparar vacío o eco JSON; excepto lone URL + solo get_current_time."""
    if not is_market_worker(worker_id or ""):
        return False
    if _market_worker_gct_only_lone_url_no_repair(
        incoming, messages, last_human_idx=last_human_idx
    ):
        return False
    if _reply_is_quant_tool_json_echo(reply or ""):
        return True
    if not (reply or "").strip():
        from langchain_core.messages import ToolMessage

        tools_since = [
            str(getattr(m, "name", "") or "")
            for m in (messages or [])[max(0, last_human_idx + 1) :]
            if isinstance(m, ToolMessage)
        ]
        return bool(tools_since)
    return False


def _parse_read_sql_tool_rows(raw: str) -> list[dict] | None:
    """Parse read_sql ToolMessage: JSON array, ``deudas_filas`` wrapper, or truncated ``preview``."""
    stripped = _strip_tool_label_prefix(raw or "")
    if not stripped:
        return None
    try:
        parsed = json.loads(stripped)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(parsed, list):
        rows = [r for r in parsed if isinstance(r, dict)]
        return rows or None
    if isinstance(parsed, dict):
        filas = parsed.get("deudas_filas")
        if isinstance(filas, list):
            rows = [r for r in filas if isinstance(r, dict)]
            return rows or None
        preview = parsed.get("preview")
        if isinstance(preview, str) and preview.strip():
            return _parse_read_sql_tool_rows(preview)
    return None


def _format_finanz_deudas_rows_prose(rows: list[dict]) -> str | None:
    """NL summary for Finanz read_sql deudas or cuentas rows."""
    if not rows or not isinstance(rows[0], dict):
        return None
    keys = set(rows[0].keys())
    if {"description", "creditor", "amount"} <= keys or {"id", "amount"} <= keys:
        lines: list[str] = []
        total = 0.0
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                amt = float(row.get("amount") or 0)
            except (TypeError, ValueError):
                amt = 0.0
            total += amt
            desc = str(row.get("description") or row.get("id") or "?").strip()
            cred = str(row.get("creditor") or "").strip()
            due = str(row.get("due_date") or "")[:10]
            chunk = f"- {desc}: ${amt:,.0f}"
            if cred:
                chunk += f" ({cred})"
            if due:
                chunk += f", vence {due}"
            lines.append(chunk)
        if lines:
            return (
                f"Deudas ({len(lines)} filas), total ${total:,.0f} COP:\n" + "\n".join(lines)
            )
        return None
    if {"balance", "currency"} <= keys or {"name", "balance"} <= keys:
        lines = []
        totals: dict[str, float] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            try:
                bal = float(row.get("balance") or 0)
            except (TypeError, ValueError):
                bal = 0.0
            cur = str(row.get("currency") or "COP").strip() or "COP"
            totals[cur] = totals.get(cur, 0.0) + bal
            nm = str(row.get("name") or row.get("id") or "?").strip()
            lines.append(f"- {nm}: ${bal:,.0f} {cur}")
        if lines:
            sub = ", ".join(f"${v:,.0f} {k}" for k, v in sorted(totals.items()))
            return f"Cuentas ({len(lines)}):\n" + "\n".join(lines) + f"\nTotal: {sub}"
    return None


def _deterministic_market_worker_tool_summary(
    messages: list[Any],
    last_human_idx: int,
    worker_id: str,
    incoming: str,
) -> str:
    """Resumen NL breve a partir de ToolMessages, sin LLM (fallback cuando la síntesis falla)."""
    from langchain_core.messages import ToolMessage

    _ = incoming  # reservado para futuros filtros por intención
    brand = _market_worker_egress_brand(worker_id)
    gct_data = _quant_latest_tool_json_since(messages, last_human_idx, "get_current_time") or {}
    hdr = ""
    if gct_data:
        day = str(gct_data.get("day_of_week") or gct_data.get("date") or "").strip()
        tm = str(gct_data.get("time") or "")[:5]
        hdr = f"{brand} · {day} {tm} COT".strip()

    summaries: list[str] = []
    for m in messages[max(0, last_human_idx + 1) :]:
        if not isinstance(m, ToolMessage):
            continue
        tn = str(getattr(m, "name", "") or "")
        tc = str(getattr(m, "content", "") or "").strip()
        if not tc or tn == "get_current_time":
            continue
        if tn in ("fetch_ib_gateway_ohlcv", "fetch_market_data", "fetch_lake_ohlcv"):
            try:
                d = json.loads(tc)
            except (json.JSONDecodeError, TypeError):
                d = None
            if isinstance(d, dict):
                if d.get("error"):
                    tkr = str(d.get("ticker") or "?")
                    err = str(d.get("message") or d.get("error") or "error")
                    summaries.append(f"{tkr}: {err}")
                elif d.get("status") == "ok":
                    tkr = str(d.get("ticker") or "?")
                    rows = d.get("rows_upserted") or d.get("bar_count") or d.get("bars_received")
                    tf = str(d.get("timeframe") or "").strip()
                    lc = d.get("last_close")
                    chunk = tkr
                    if tf:
                        chunk += f" ({tf})"
                    if rows is not None:
                        chunk += f": {rows} velas"
                    if lc is not None:
                        try:
                            chunk += f", último cierre ${float(lc):,.2f}"
                        except (TypeError, ValueError):
                            pass
                    summaries.append(chunk)
                continue
        if tn == "get_ibkr_portfolio":
            m_total = re.search(r"Valor total:\s*\$([0-9,]+(?:\.[0-9]+)?)", tc)
            m_pos = re.search(r"Posiciones:\s*([0-9]+)", tc)
            if m_total:
                chunk = f"Portfolio IBKR ${m_total.group(1)}"
                if m_pos:
                    chunk += f", {m_pos.group(1)} posiciones"
                summaries.append(chunk)
            else:
                summaries.append("Portfolio IBKR consultado.")
            continue
        if tn == "read_sql":
            rows = _parse_read_sql_tool_rows(tc)
            if rows:
                prose = _format_finanz_deudas_rows_prose(rows)
                if prose:
                    summaries.append(prose)
                    continue
        preview = tc.split("\n", 1)[0].strip()[:120]
        if preview:
            summaries.append(f"{tn}: {preview}")

    if not summaries:
        return ""
    body = ". ".join(summaries)
    if not body.endswith("."):
        body += "."
    if hdr:
        return f"{hdr}\n\n{body}"
    return body


def _repair_quant_vlm_tool_egress_reply(
    llm: Any,
    spec: Any,
    incoming: str,
    reply: str,
    messages: list[Any],
    *,
    skip_llm_synthesis: bool = False,
) -> str:
    """Síntesis de respaldo cuando Quant devuelve vacío o JSON crudo tras VLM + tools."""
    from duckclaw.forge.atoms.user_reply_nl_synthesis import synthesize_user_visible_reply
    from langchain_core.messages import ToolMessage

    lh = _quant_last_human_index(messages)
    tool_parts: list[str] = []
    gct_data = _parse_get_current_time_json(reply) or {}
    for m in messages[max(0, lh + 1) :]:
        if isinstance(m, ToolMessage):
            tn = str(getattr(m, "name", "") or "")
            tc = str(getattr(m, "content", "") or "").strip()
            if tc:
                tool_parts.append(f"### {tn}\n{tc}")
            if tn == "get_current_time" and not gct_data:
                gct_data = _quant_latest_tool_json_since(messages, lh, "get_current_time") or {}

    hdr = ""
    if gct_data:
        day = str(gct_data.get("day_of_week") or gct_data.get("date") or "").strip()
        tm = str(gct_data.get("time") or "")[:5]
        brand = _market_worker_egress_brand(
            str(getattr(spec, "logical_worker_id", None) or getattr(spec, "worker_id", "") or "")
        )
        hdr = f"{brand} · {day} {tm} COT".strip()

    evidence_parts: list[str] = []
    if hdr:
        evidence_parts.append(hdr)
    if tool_parts:
        evidence_parts.append("Resultados de herramientas:\n" + "\n\n".join(tool_parts))
    if (reply or "").strip() and _reply_is_quant_tool_json_echo(reply):
        evidence_parts.append(f"Respuesta cruda rechazada:\n{reply.strip()}")
    evidence_parts.append(f"Contexto del usuario:\n{(incoming or '').strip()}")
    evidence = "\n\n".join(evidence_parts)

    wid = str(getattr(spec, "worker_id", "") or "").strip() or WORKER_QUANT_TRADER
    _lh = _quant_last_human_index(messages)
    _lid = str(getattr(spec, "logical_worker_id", None) or getattr(spec, "worker_id", "") or "")

    def _deterministic_fallback() -> str:
        return _deterministic_market_worker_tool_summary(messages, _lh, _lid, incoming)

    if skip_llm_synthesis:
        det = _deterministic_fallback()
        return det if det else reply
    if llm is None:
        det = _deterministic_fallback()
        return det if det else reply
    syn = synthesize_user_visible_reply(
        llm,
        user_ask=(incoming or "").strip(),
        raw_evidence=evidence,
        worker_id=wid,
    )
    syn_st = (syn or "").strip()
    if syn_st and not _reply_is_quant_tool_json_echo(syn_st):
        return syn_st
    det = _deterministic_fallback()
    return det if det else reply


def _repair_quant_gct_json_echo_reply(
    llm: Any,
    spec: Any,
    incoming: str,
    reply: str,
    messages: list[Any],
) -> str:
    """Compat: delega en síntesis VLM+tools (get_current_time es un caso)."""
    return _repair_quant_vlm_tool_egress_reply(llm, spec, incoming, reply, messages)


def _response_mentions_wall_clock(text: str) -> bool:
    """True si la respuesta del modelo declara hora/fecha de pared (encabezado Quant, COT, etc.)."""
    if _reply_is_get_current_time_json_only(text):
        return False
    t = (text or "").strip().lower()
    if not t:
        return False
    if "cot" in t or "bogot" in t or "america/bogota" in t:
        return True
    if re.search(r"\b\d{1,2}:\d{2}\b", t):
        return True
    if re.search(r"quant-trader\s+\d+\s*·", t):
        return True
    if "mercado cerrado" in t or "mercado abierto" in t:
        return True
    for d in (
        "lunes",
        "martes",
        "miércoles",
        "miercoles",
        "jueves",
        "viernes",
        "sábado",
        "sabado",
        "domingo",
    ):
        if d in t:
            return True
    return False


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

    if not has_ibkr or not is_finanz(logical_worker_id):
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


_TASK_AWARENESS_PROMPT = load_guardrail("prompts", "task_awareness_default")
_AXIS_COORDINATOR_TASK_AWARENESS_PROMPT = load_guardrail("prompts", "task_awareness_axis")


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
        return str(p.expanduser().resolve())
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


def reddit_share_shortlink_fallback_query(share_url: str) -> str:
    """
    reddit_search_reddit con ``query=<URL /s/…>`` rompe el servidor MCP (`children`).
    Preferir texto ``r/<subreddit> shortlink <slug>`` (alineado con la spec Reddit MCP).
    """
    raw = (share_url or "").strip()
    m = re.search(r"/r/([\w_]+)/s/([a-zA-Z0-9]+)", raw, re.IGNORECASE)
    if m:
        return f"r/{m.group(1)} shortlink {m.group(2)}"
    return raw


def reddit_share_search_query_for_attempt(share_url: str, attempt_index: int) -> str:
    """
    Evidencia gateway: ``r/<sub> shortlink <slug>`` devolvió hilos irrelevantes (p. ej. r/all).
    Segundo intento: query más corta ``<sub> <slug>``; siguientes: sólo ``<slug>``.
    ``attempt_index`` = nº de ToolMessage ``reddit_search_reddit`` ya en el historial antes de esta llamada.
    """
    raw = (share_url or "").strip()
    slug_m = re.search(r"/s/([a-zA-Z0-9]+)", raw, re.IGNORECASE)
    slug = slug_m.group(1) if slug_m else ""
    sub_m = re.search(r"/r/([\w_]+)/s/", raw, re.IGNORECASE)
    sub = sub_m.group(1) if sub_m else ""
    if attempt_index <= 0:
        return reddit_share_shortlink_fallback_query(raw)
    if slug and sub:
        if attempt_index == 1:
            return f"{sub} {slug}"
        return slug
    return reddit_share_shortlink_fallback_query(raw)


def _reddit_trust_share_tracking_redirect() -> bool:
    """
    Reddit puede 301 /r/*/s/<slug> hacia .../comments/<id>/?share_id=&utm_=android_app
    donde <id> no coincide con lo que enlazaba el cliente. Default: **no confiar**.
    Override: ``DUCKCLAW_REDDIT_TRUST_SHARE_TRACKING_REDIRECT=1``.
    """
    return (os.environ.get("DUCKCLAW_REDDIT_TRUST_SHARE_TRACKING_REDIRECT") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _reddit_tools_paused() -> bool:
    """Opt-in: omitir invocaciones reddit_* (p. ej. API 403 / OAuth roto). ``DUCKCLAW_REDDIT_PAUSED=1``."""
    return (os.environ.get("DUCKCLAW_REDDIT_PAUSED") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _reddit_comments_url_has_share_tracking(canonical_comments_url: str) -> bool:
    """
    Redirects intermedios típicos de «compartir desde app»: utm_medium=android_app + share_id=…
    (evidencia runtime: mismo slug /s/Fu… redirige vía servidor a otro submission).
    """
    try:
        q = parse_qs(urlparse(canonical_comments_url).query or "")
        if q.get("share_id"):
            return True
        utm_src = [str(x).lower() for x in q.get("utm_source", [])]
        utm_med = [str(x).lower() for x in q.get("utm_medium", [])]
        if "share" in utm_src:
            return True
        if any(x in {"android_app", "iphone_app", "mobile_app"} for x in utm_med):
            return True
        return False
    except Exception:
        return False


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
    t0 = time.perf_counter()
    try:
        req = _urllib_request.Request(raw, headers={"User-Agent": ua, "Accept": "text/html"})
        with _urllib_request.urlopen(req, timeout=timeout) as resp:
            raw_final = resp.geturl()
        if not isinstance(raw_final, str):
            _log.info(
                "reddit share resolve: sin URL final en %.2fs url=%r",
                time.perf_counter() - t0,
                raw[:80],
            )
            return None
        if not _reddit_trust_share_tracking_redirect() and _reddit_comments_url_has_share_tracking(
            raw_final
        ):
            _log.info(
                "reddit share resolve: redirect con tracking rechazado en %.2fs → reddit_search",
                time.perf_counter() - t0,
            )
            return None
        final = raw_final.split("#")[0].split("?")[0].rstrip("/")
        if not _REDDIT_COMMENTS_IN_URL_RE.search(final):
            _log.info(
                "reddit share resolve: sin /comments/ en %.2fs final=%r",
                time.perf_counter() - t0,
                raw_final[:96],
            )
            return None
        if not final.lower().startswith("http"):
            final = f"https://{final}"
        _log.info(
            "reddit share resolve: ok en %.2fs → %r",
            time.perf_counter() - t0,
            final[:96],
        )
        return final
    except Exception as exc:
        _log.info(
            "reddit share resolve: falló en %.2fs url=%r err=%s",
            time.perf_counter() - t0,
            raw[:80],
            exc,
        )
        return None


def _fetch_reddit_post_via_public_json(comments_url: str, *, timeout: float = 15.0) -> Optional[str]:
    """
    Obtiene un post vía API pública .json de Reddit (sin MCP).
    Devuelve JSON compacto compatible con format_reddit_mcp_reply_if_applicable.
    """
    sub, pid = _subreddit_and_post_id_from_reddit_comments_url(comments_url)
    if not sub or not pid:
        return None
    ua = (os.environ.get("REDDIT_USER_AGENT") or "duckclaw:public-json/0.1 (by duckclaw)").strip()
    api_url = f"https://www.reddit.com/r/{sub}/comments/{pid}/.json?raw_json=1"
    try:
        req = _urllib_request.Request(
            api_url,
            headers={"User-Agent": ua, "Accept": "application/json"},
        )
        with _urllib_request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(body)
        if not isinstance(data, list) or not data:
            return None
        listing = data[0] if isinstance(data[0], dict) else {}
        children = (listing.get("data") or {}).get("children") or []
        if not children or not isinstance(children[0], dict):
            return None
        post_data = children[0].get("data") or {}
        if not isinstance(post_data, dict):
            return None
        payload = {
            "success": True,
            "subreddit": sub,
            "posts": [
                {
                    "id": pid,
                    "title": post_data.get("title") or "",
                    "score": post_data.get("score"),
                    "permalink": post_data.get("permalink") or "",
                    "selftext": post_data.get("selftext") or "",
                    "is_self": bool(post_data.get("is_self")),
                    "url": post_data.get("url") or "",
                }
            ],
        }
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        _log.info(
            "reddit public json fetch failed url=%r err=%s",
            (comments_url or "")[:80],
            exc,
        )
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


def _latest_human_index_with_reddit_share_url(messages: list[Any]) -> Optional[int]:
    """Índice (en `messages`, 0-based) del Human más reciente cuya URL Reddit es /r/…/s/… share."""
    from langchain_core.messages import HumanMessage

    from duckclaw.integrations.llm_providers import lc_message_content_to_text

    for i in range(len(messages or []) - 1, -1, -1):
        m = messages[i]
        if not isinstance(m, HumanMessage):
            continue
        txt = lc_message_content_to_text(m)
        u = _extract_first_reddit_url(txt)
        if u and _REDDIT_SHARE_PATH_RE.search(u):
            return i
    return None


def _latest_human_index_with_vlm_visual_markers(messages: list[Any]) -> Optional[int]:
    """Human más reciente con payload VLM (mismo marcador que el gateway al Multimodal)."""
    from langchain_core.messages import HumanMessage

    from duckclaw.integrations.llm_providers import lc_message_content_to_text

    for i in range(len(messages or []) - 1, -1, -1):
        m = messages[i]
        if not isinstance(m, HumanMessage):
            continue
        txt = lc_message_content_to_text(m) or ""
        if "[VLM_CONTEXT" in txt or "Contexto visual adjunto:" in txt:
            return i
    return None


def _quant_trader_reddit_history_anchor_intent(incoming: str, messages: list[Any]) -> bool:
    """
    Mensaje corto tipo reintento sin URL en el turno actual, pero el último Human con Reddit
    pegó un enlace /r/.../s/... — misma situación que /context --add (el share sigue en el payload).
    """
    inc = (incoming or "").strip()
    if len(inc) > 220:
        return False
    if _extract_first_reddit_url(inc):
        return False
    u = _most_recent_reddit_url_in_human_messages(messages or [])
    if not u or not _REDDIT_SHARE_PATH_RE.search(u):
        return False
    # No robar "reintento" genérico tras análisis visual: el share queda en historial pero el
    # usuario siguió con foto/VLM (evidencia pm2: vuelve a intentar → forced_tool=reddit + megathread).
    _sh_i = _latest_human_index_with_reddit_share_url(messages or [])
    _vlm_i = _latest_human_index_with_vlm_visual_markers(messages or [])
    if _sh_i is not None and _vlm_i is not None and _vlm_i > _sh_i:
        return False
    if not inc:
        return False
    low = inc.lower()
    if re.search(
        r"\b(reintent|reintenta|vuelv\w*\s+a|intent\w*|de\s+nuevo|otra\s+vez|retry|try\s+again)\b",
        low,
    ):
        return True
    return any(
        k in low
        for k in (
            "reddit",
            "enlace",
            "link",
            "post",
            "url",
            "acort",
            "shortlink",
            "variable",
            "entorno",
            "mismo enlace",
            "misma url",
        )
    )


def _quant_visual_tool_succeeded_in_turn(messages: list[Any]) -> bool:
    """True si generate_visual_asset devolvió ok:true en el turno actual (desde último HumanMessage)."""
    try:
        from langchain_core.messages import HumanMessage, ToolMessage
    except ImportError:
        HumanMessage = ToolMessage = ()  # type: ignore[assignment, misc]
    last_u = -1
    for i in range(len(messages) - 1, -1, -1):
        m = messages[i]
        if HumanMessage and isinstance(m, HumanMessage):
            last_u = i
            break
    for msg in messages[last_u + 1 :]:
        if isinstance(msg, ToolMessage) and (getattr(msg, "name", "") or "") == "generate_visual_asset":
            return '"ok":true' in str(msg.content or "").replace(" ", "")
    return False


def _visual_asset_calls_since_last_human(messages: list[Any]) -> int:
    """Cuántas veces se invocó generate_visual_asset desde el último HumanMessage."""
    from langchain_core.messages import HumanMessage, ToolMessage

    count = 0
    for msg in reversed(messages or []):
        if isinstance(msg, HumanMessage):
            break
        if isinstance(msg, ToolMessage) and (getattr(msg, "name", "") or "") == "generate_visual_asset":
            count += 1
    return count


def _quant_trader_visual_generation_intent(incoming: str) -> bool:
    """Pedido explícito de imagen (txt2img) en Quant-Trader."""
    s = (incoming or "").strip()
    if not s or len(s) > 2000:
        return False
    low = s.lower()
    if re.search(
        r"(?:\b(?:genera|generar|crea|crear|dibuja|dibujar|haz(?:me)?|hacer|pinta|pintar)\b.{0,50}\b(?:imagen(?:es)?|foto(?:s)?|ilustraci[oó]n(?:es)?|caricatura(?:s)?|avatar(?:es)?|picture|image(?:s)?)\b)",
        low,
        re.IGNORECASE | re.DOTALL,
    ):
        return True
    return bool(
        re.search(
            r"\b(?:txt2img|text-to-image|stable\s*diffusion|comfyui)\b",
            low,
            re.IGNORECASE,
        )
    )


_GENERIC_VISUAL_TAIL_RE = re.compile(
    r"^(?:como lo ves|así lo ves|visualmente|de forma visual)\s*\.?$",
    re.IGNORECASE,
)


def _quant_visual_prompt_from_incoming(incoming: str) -> str:
    """Extrae el subject visual del mensaje del usuario para ComfyUI."""
    s = (incoming or "").strip()
    m = re.search(
        r"(?:\b(?:genera|generar|crea|crear|dibuja|dibujar|haz(?:me)?|hacer|pinta|pintar)\b"
        r".{0,60}?\b(?:imagen(?:es)?|foto(?:s)?|ilustraci[oó]n(?:es)?|caricatura(?:s)?|avatar(?:es)?)\b"
        r"(?:\s+de)?\s+(.+))",
        s,
        re.IGNORECASE | re.DOTALL,
    )
    if m:
        tail = m.group(1).strip().rstrip(".")
        if len(tail) >= 24 and not _GENERIC_VISUAL_TAIL_RE.match(tail):
            return tail[:500]
    if re.search(r"contexto\s+macro|macroecon[oó]m", s, re.IGNORECASE):
        return s[:500]
    return s[:500]




def _agent_node_llm_failure_user_message(exc: BaseException, *, provider: str) -> str:
    """Mensaje Telegram cuando falla invoke del LLM en agent_node (sin culpar a MLX si el proveedor es Groq)."""
    pl = (provider or "").strip().lower()
    raw = str(exc)
    low = raw.lower()
    mlx_hint = load_guardrail("errors", "llm_failure_mlx")
    groq_tokens_hint = load_guardrail("errors", "llm_failure_groq_tpm")
    is_groq_size_or_tpm = (
        "413" in raw
        or "rate_limit_exceeded" in low
        or "tokens per minute" in low
        or "request too large" in low
        or "too large for model" in low
    )
    if pl == "groq" and is_groq_size_or_tpm:
        return groq_tokens_hint
    detail = raw[:380] + ("…" if len(raw) > 380 else "")
    if pl == "groq":
        return load_guardrail("errors", "llm_failure_groq_generic").format(detail=detail)
    if pl == "deepseek":
        return load_guardrail("errors", "llm_failure_deepseek").format(detail=detail)
    if pl == "openai":
        return load_guardrail("errors", "llm_failure_openai").format(detail=detail)
    if pl == "openrouter" and ("402" in raw or "payment required" in low or "more credits" in low):
        return (
            "OpenRouter rechazó la petición (créditos insuficientes o `max_tokens` demasiado alto). "
            "Opciones: añade créditos en openrouter.ai/settings/credits, usa DeepSeek/Groq en el selector, "
            "o baja `DUCKCLAW_OPENROUTER_MAX_OUTPUT_TOKENS` (p. ej. 2048). "
            f"Detalle: {detail}"
        )
    if pl in ("mlx", "iotcorelabs"):
        return mlx_hint
    return load_guardrail("errors", "llm_failure_generic").format(detail=detail)


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
    return bool(effective_telegram_bot_token_outbound())


def _heartbeat_elapsed_sec(state: dict) -> float | None:
    t0 = state.get("subagent_turn_started_monotonic")
    if not isinstance(t0, (int, float)):
        return None
    return max(0.0, time.monotonic() - float(t0))


def _send_sandbox_heartbeat_telegram(state: dict) -> None:
    from duckclaw.graphs.chat_heartbeat import (
        format_tool_heartbeat,
        is_admin_ui_chat_session,
        normalize_telegram_chat_id_for_outbound,
    )

    cid_raw = str(state.get("chat_id") or state.get("session_id") or "").strip()
    if is_admin_ui_chat_session(cid_raw):
        return
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
    _log.debug("sandbox heartbeat: sin token Bot API para chat_id=%r", cid)


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
        is_admin_ui_chat_session,
        is_chat_heartbeat_enabled,
        schedule_chat_heartbeat_dm,
    )

    _hcid = str(state.get("chat_id") or state.get("session_id") or "").strip()
    if is_admin_ui_chat_session(_hcid):
        # Admin SSE: publish_admin_tool_event (vía _schedule_tool_heartbeat) ya cubre start/done.
        return

    _hb_head = (state.get("subagent_instance_label") or "").strip() or None
    _hb_uname = (state.get("username") or "").strip() or None
    _hb_plan = (state.get("heartbeat_plan_title") or "").strip() or None
    _hb_tok = (state.get("outbound_telegram_bot_token") or "").strip() or None
    _htid = (state.get("tenant_id") or "default").strip() or "default"
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
    if not is_finanz(_lid):
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
        Example: FROM my_table -> FROM main.my_table
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


def filter_tools_for_ibkr(tools: list[Any], enabled: bool) -> list[Any]:
    """Si IBKR está OFF para el chat, elimina ``get_ibkr_portfolio`` del bind al LLM."""
    if enabled:
        return list(tools)
    return [t for t in tools if getattr(t, "name", "") != "get_ibkr_portfolio"]


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
    tool_surface: Literal["full", "context_synthesis", "visual_generation", "url_research"] = "full",
    incoming_hint: str | None = None,
    open_vault_read_only: bool = False,
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

    ``tool_surface=visual_generation``: txt2img en Quant-Trader; omite GitHub, Trends y Reddit
    (cold start ~2 min) y delega en ``generate_visual_asset`` vía tool call determinista.

    ``tool_surface=url_research``: mensaje solo URL (admin playground / Quant); omite GitHub y Google Trends.
    Reddit MCP solo si ``incoming_hint`` contiene ``reddit.com`` (lazy por dominio, no cold start ~3 min).

    ``open_vault_read_only``: para ``SUMMARIZE_NEW_CONTEXT`` / ``SUMMARIZE_STORED_CONTEXT`` el worker no debe
    escribir en la bóveda (spec Context Injection). Abrir RW compite con el **db-writer** cuando éste inserta
    contexto vía cola en el mismo ``.duckdb``; DuckDB permite **solo lectura** concurrente con otro proceso en RW.
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
        and not open_vault_read_only
    )
    effective_vault_ro = bool(spec.read_only) or bool(open_vault_read_only)
    if skip_private:
        db = reuse_db
        _log.debug("build_worker_graph: reuse DuckClaw (same file, no shared, skip private ATTACH) path=%s", path)
    else:
        # RW: manifest quant_core / señales. RO: manifest read_only o turnos SUMMARIZE_* (sin INSERT en vault).
        # Motor Python para RW en archivo: el manager ya abrió RO con duckdb Python; mezclar bridge C++ (auto)
        # + Python en el mismo .duckdb en un PID provoca «different configuration» (misma causa que fly en api-gateway).
        _engine: Literal["auto", "python"] = (
            "python"
            if not effective_vault_ro and (path or "").strip() not in ("", ":memory:")
            else "auto"
        )
        db = DuckClaw(path, read_only=effective_vault_ro, engine=_engine)
    # La conexión DuckClaw ya es al archivo de la bóveda; ATTACH del mismo path como `private`
    # abre otra vista del mismo archivo y en DuckDB suele disparar «different configuration».
    db_open_path = str(getattr(db, "_path", "") or path or "").strip()
    vault_path_for_attach = str(path or "").strip()
    skip_private_attach = bool(skip_private) or _same_duckdb_file(
        db_open_path, vault_path_for_attach
    )
    _apply_forge_attaches(
        db,
        path,
        shared_resolved,
        private_attach_read_only=effective_vault_ro,
        shared_attach_read_only=True,
        skip_private_attach=skip_private_attach,
    )

    system_prompt = load_system_prompt(spec)
    tools = _build_worker_tools(db, spec)
    _hint_low = (incoming_hint or "").strip().lower()
    _register_github = tool_surface == "full"
    _register_trends = tool_surface == "full"
    # Reddit MCP (npx cold start ~2–3 min): solo cuando el turno lo necesita, no en cada full.
    _register_reddit = bool(getattr(spec, "reddit_config", None)) and (
        tool_surface == "context_synthesis"
        or (tool_surface == "url_research" and "reddit.com" in _hint_low)
        or (tool_surface == "full" and "reddit.com" in _hint_low)
    )
    if _register_github and getattr(spec, "github_config", None):
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
    if _register_trends and getattr(spec, "google_trends_config", None) is not None:
        try:
            from duckclaw.forge.skills.google_trends_bridge import register_google_trends_skill

            register_google_trends_skill(tools, spec.google_trends_config)
        except Exception:
            pass
    # Reddit: SUMMARIZE_NEW_CONTEXT con URL /r/.../s/...; url_research solo si dominio reddit.com.
    if _register_reddit and getattr(spec, "reddit_config", None):
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
            from duckclaw.forge.skills.ibkr_bridge import (
                register_ibkr_skill,
                replace_get_ibkr_portfolio_with_finanz_live_variant,
            )

            register_ibkr_skill(tools, spec.ibkr_config)
            _lid_ibkr = (getattr(spec, "logical_worker_id", None) or spec.worker_id or "").strip().lower()
            if is_finanz(_lid_ibkr):
                replace_get_ibkr_portfolio_with_finanz_live_variant(tools, str(path))
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

    if getattr(spec, "comfyui_config", None) is not None:
        try:
            from duckclaw.forge.skills.comfyui_bridge import register_comfyui_skill

            register_comfyui_skill(tools, spec.comfyui_config, duckclaw_db=db)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            _log.debug("comfyui skills registration skipped", exc_info=True)

    _qcfg = getattr(spec, "quant_config", None)
    _lid_q = (getattr(spec, "logical_worker_id", None) or spec.worker_id or "").strip().lower()
    if isinstance(_qcfg, dict) and _qcfg.get("enabled") and is_finanz(_lid_q):
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
    elif isinstance(_qcfg, dict) and _qcfg.get("enabled") and is_quant_trader(_lid_q) and llm is not None:
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
    _wid_for_task = (getattr(spec, "worker_id", None) or "").strip()
    _is_axis_coordinator = _wid_for_task in ("AXIS-Maestro", "maestro")
    if not _is_axis_coordinator:
        try:
            from duckclaw.workers.orchestrator import load_orchestrator_config

            _is_axis_coordinator = load_orchestrator_config(_wid_for_task) is not None
        except Exception:
            pass
    if _is_axis_coordinator:
        _task_block = (
            _TASK_AWARENESS_PROMPT.strip() + "\n" + _AXIS_COORDINATOR_TASK_AWARENESS_PROMPT.strip()
        )
    else:
        _task_block = _TASK_AWARENESS_PROMPT.strip()
    _system_prompt_only = (system_prompt or "").strip()
    _task_block_resolved = _task_block
    effective_prompt = _system_prompt_only + "\n\n" + _task_block_resolved
    # Cierre de dominio = última instrucción al modelo (domain_closure.md del worker).
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
        elif is_finanz(_lid) and finanz_field_reflection_enabled(spec):
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
        if is_quant_trader(_lid):
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
        """Sandbox flag per chat/session (defaults OFF; ON for admin UI si no hay override)."""
        from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session
        from duckclaw.graphs.on_the_fly_commands import get_chat_state

        chat_id = state.get("chat_id") or state.get("session_id") or "default"
        raw = get_chat_state(db, chat_id, "sandbox_enabled")
        v = (raw or "").strip().lower()
        if not v and is_admin_ui_chat_session(str(chat_id)):
            return True
        return v in ("true", "1", "on", "sí", "si")

    def _ibkr_enabled_for_state(state: dict) -> bool:
        """IBKR portfolio por chat (``/ibkr on``). Finanz: default OFF; Quant: default ON."""
        from duckclaw.graphs.on_the_fly_commands import get_chat_state

        chat_id = state.get("chat_id") or state.get("session_id") or "default"
        raw = (get_chat_state(db, chat_id, "ibkr_enabled") or "").strip().lower()
        if raw in ("true", "1", "on", "sí", "si"):
            return True
        if raw in ("false", "0", "off"):
            return False
        return is_quant_trader(_lid)

    tools_sandbox_off = filter_tools_for_sandbox(tools, enabled=False)
    tools_by_name_sandbox_off = {t.name: t for t in tools_sandbox_off}

    _groq_bind = (provider or "").strip().lower() == "groq"
    _tools_for_llm_bind = _groq_tools_without_reddit_for_bind(tools) if _groq_bind else tools
    _tools_sandbox_off_bind = (
        _groq_tools_without_reddit_for_bind(tools_sandbox_off) if _groq_bind else tools_sandbox_off
    )
    _tools_ibkr_off_bind = filter_tools_for_ibkr(_tools_for_llm_bind, enabled=False)
    _tools_sandbox_ibkr_off_bind = filter_tools_for_ibkr(_tools_sandbox_off_bind, enabled=False)
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
        llm_with_tools_ibkr_off = _bind_tools(llm, _tools_ibkr_off_bind)
        llm_with_tools_sandbox_ibkr_off = _bind_tools(llm, _tools_sandbox_ibkr_off_bind)

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

        has_generate_visual = "generate_visual_asset" in tools_by_name
        tool_choice_generate_visual = {
            "type": "function",
            "function": {"name": "generate_visual_asset"},
        }
        llm_force_generate_visual_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_generate_visual)
            if has_generate_visual
            else None
        )
        llm_force_generate_visual_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_generate_visual)
            if "generate_visual_asset" in tools_by_name_sandbox_off
            else None
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

        def _patch_ai_reddit_share_tool_calls(resp: Any, share_url: str, *, attempt_index: int = 0) -> Any:
            """
            Fallback si no hubo resolución HTTP a URL /comments/ en agent_node: el slug /s/ no es post_id.
            Reescribe get_post (o search con query=URL) → reddit_search_reddit con query shortlink.
            El camino preferido sigue siendo _resolve_reddit_share_url_to_comments_url + reddit_get_post.
            """
            if not share_url or not _incoming_has_reddit_share_path(share_url):
                return resp
            tcs = list(getattr(resp, "tool_calls", None) or [])
            if not tcs:
                return resp
            _q_safe = reddit_share_search_query_for_attempt(share_url, attempt_index)
            patched: list[Any] = []
            changed = False
            for tc in tcs:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                tid = (tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)) or ""
                if name == "reddit_get_post":
                    patched.append(
                        {"name": "reddit_search_reddit", "args": {"query": _q_safe}, "id": tid}
                    )
                    changed = True
                    continue
                if name == "reddit_search_reddit":
                    if isinstance(tc, dict):
                        args = _tc_args_as_dict(tc)
                        args["query"] = _q_safe
                        new_tc = {**tc, "args": args}
                        new_tc.pop("arguments", None)
                        patched.append(new_tc)
                        changed = True
                        continue
                    try:
                        base = getattr(tc, "args", None)
                        args = dict(base) if isinstance(base, dict) else {}
                        args["query"] = _q_safe
                        patched.append(tc.model_copy(update={"args": args}))
                        changed = True
                    except Exception:
                        patched.append(tc)
                    continue
                patched.append(tc)
            if not changed:
                return resp
            return resp.model_copy(update={"tool_calls": patched})

        def _spec_is_job_hunter() -> bool:
            a = re.sub(r"[^a-z0-9]", "", (spec.worker_id or "").lower())
            b = re.sub(r"[^a-z0-9]", "", (getattr(spec, "logical_worker_id", None) or "").lower())
            return a == "jobhunter" or b == "jobhunter"

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
            return incoming_is_schema_query_heuristic(text)

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
            ibkr_session_on = has_ibkr and _ibkr_enabled_for_state(state)
            _ev_msgs = state.get("messages") or []
            _ev_last = _ev_msgs[-1] if _ev_msgs else None
            if is_quant_trader(_lid):
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
            _summarize_ok_for_forced_ohlcv = (
                not telegram_context_summarize_directive
                or _quant_summarize_allows_forced_ohlcv_fetch(incoming, str(_lid or ""))
            )
            summarize_stored_directive = "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]" in (incoming or "")
            _is_goals_tick_msg = (
                str(incoming or "").strip().startswith("[SYSTEM_EVENT:")
                and proactive_review_event_phrase_in_text(str(incoming or ""))
            )
            is_schema = _is_schema_query(incoming)
            is_table_content = _is_table_content_query(incoming)
            is_latest_game = _is_latest_game_query(incoming)
            _is_portfolio_kw = _incoming_is_portfolio_query(incoming) or _user_explicitly_requests_ibkr_portfolio(
                incoming
            )
            _is_portfolio_quant_retry = (
                is_quant_trader(_lid)
                and _quant_retry_or_probe_needs_ibkr_portfolio(_ev_msgs, incoming)
            )
            _wants_new_signal = bool(
                is_quant_trader(_lid)
                and _quant_user_requests_new_trade_signal(incoming)
            )
            _is_quant_operational_directive = bool(
                is_quant_trader(_lid)
                and str(incoming or "").strip().lower().startswith(
                    "tarea: intención operativa cuant detectada".lower()
                )
            )
            _is_exec_bug_probe = (
                is_quant_trader(_lid)
                and _quant_execution_bug_probe_needs_ibkr_portfolio(incoming)
            )
            _q_reddit_hist = (
                is_quant_trader(_lid)
                and _quant_trader_reddit_history_anchor_intent(incoming, _ev_msgs)
            )
            is_portfolio = ibkr_session_on and (
                _is_portfolio_kw or _is_portfolio_quant_retry or _is_exec_bug_probe
            )
            if is_quant_trader(_lid) and _wants_new_signal:
                # En comandos operativos de nueva señal no forzar `get_ibkr_portfolio` first.
                # Con Groq esto puede inducir tool_use_failed al mezclar tool_call + texto.
                is_portfolio = False
            if is_quant_trader(_lid) and _is_quant_operational_directive:
                # TAREA sintética del manager incluye texto tipo "fetch+portfolio+..."; no forzar IBKR.
                is_portfolio = False
            if is_quant_trader(_lid) and _is_goals_tick_msg:
                # En ticks /crons no forzar "solo portfolio": primero debe correr el ciclo CFD/HRP.
                is_portfolio = False
            if is_quant_trader(_lid) and _q_reddit_hist:
                # Reintento sin re-pegar URL: misma lógica que SUMMARIZE (share en contexto); no adelantar IBKR.
                is_portfolio = False
            force_finanz_cuentas = (
                is_finanz(_lid)
                and has_read_sql
                and _is_finanz_local_accounts_query(incoming)
                and "[SYSTEM_DIRECTIVE:" not in (incoming or "")
            )
            force_finanz_deudas = (
                is_finanz(_lid)
                and has_read_sql
                and _is_finanz_debts_query(incoming)
                and "[SYSTEM_DIRECTIVE:" not in (incoming or "")
            )
            force_finanz_presupuestos = (
                is_finanz(_lid)
                and has_read_sql
                and _is_finanz_budgets_query(incoming)
                and "[SYSTEM_DIRECTIVE:" not in (incoming or "")
            )
            force_finanz_db_validation = (
                is_finanz(_lid)
                and has_read_sql
                and _is_finanz_validate_db_intent(incoming)
                and "[SYSTEM_DIRECTIVE:" not in (incoming or "")
            )
            force_finanz_admin_sql = (
                is_finanz(_lid)
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
                force_finanz_db_validation = False
                force_finanz_admin_sql = False
            # No forzar herramienta si el último mensaje ya es ToolMessage (ya ejecutamos la tool):
            # así el LLM puede responder con texto y no entrar en bucle (inspect_schema -> agent -> inspect_schema).
            last_msg = (state.get("messages") or [])[-1] if state.get("messages") else None
            already_has_tool_result = last_msg is not None and isinstance(last_msg, ToolMessage)

            _orch = None
            _orch_forced: str | None = None
            try:
                from duckclaw.workers.tool_orchestration import (
                    parse_tool_orchestration,
                    resolve_forced_tool,
                )

                _orch = parse_tool_orchestration(spec)
                if _orch and not telegram_context_summarize_directive:
                    _orch_forced = resolve_forced_tool(
                        _orch,
                        incoming,
                        state.get("messages") or [],
                        tools_by_name,
                    )
            except Exception:
                _orch = None
                _orch_forced = None

            if _orch:
                force_finanz_cuentas = False
                force_finanz_deudas = False
                force_finanz_presupuestos = False
                force_finanz_db_validation = False
                force_finanz_admin_sql = False

            if (
                _orch_forced == "get_current_time"
                and "get_current_time" in tools_by_name
                and not telegram_context_summarize_directive
            ):
                _lh_orch_gct = _quant_last_human_index(state.get("messages") or [])
                if not _quant_tool_called_since(
                    state.get("messages") or [], _lh_orch_gct, "get_current_time"
                ):
                    _forced_tid_orch_gct = f"call_orch_get_current_time_{int(time.time() * 1000)}"
                    _forced_tc_orch_gct = [
                        {
                            "name": "get_current_time",
                            "args": {},
                            "id": _forced_tid_orch_gct,
                            "type": "tool_call",
                        }
                    ]
                    _log.info("[%s] tool_orchestration → get_current_time", _wl)
                    _out_orch_gct = {
                        **state,
                        "messages": state["messages"]
                        + [AIMessage(content="", tool_calls=_forced_tc_orch_gct)],
                    }
                    _out_orch_gct.update(_identity_fields(state))
                    return _out_orch_gct

            if (
                is_quant_trader(_lid)
                and has_ibkr
                and not ibkr_session_on
                and not already_has_tool_result
                and (
                    _is_portfolio_kw
                    or _user_explicitly_requests_ibkr_portfolio(incoming)
                )
            ):
                _ibkr_off = AIMessage(content=_ibkr_disabled_chat_hint())
                _out_ibkr = {**state, "messages": state["messages"] + [_ibkr_off]}
                _out_ibkr.update(_identity_fields(state))
                return _out_ibkr

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
            force_admin_sql = bool(
                _orch_forced == "admin_sql"
                or (force_finanz_admin_sql and not already_has_tool_result)
            )
            force_read_sql = bool(
                _orch_forced == "read_sql"
                or (
                    (
                        is_table_content
                        or is_latest_game
                        or force_finanz_cuentas
                        or force_finanz_deudas
                        or force_finanz_presupuestos
                        or force_finanz_db_validation
                    )
                    and not already_has_tool_result
                )
            )
            force_portfolio_first = is_portfolio and not already_has_tool_result
            force_portfolio_after_local_cuentas = (
                not telegram_context_summarize_directive
                and _finanz_should_force_ibkr_after_local_cuentas_read(
                    state.get("messages"),
                    logical_worker_id=str(_lid or ""),
                    has_ibkr=bool(ibkr_session_on),
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
            elif is_finanz(_lid) and _finanz_followup_reddit_read_intent(incoming):
                _reddit_anchor_u = _most_recent_reddit_url_in_human_messages(state.get("messages") or [])
            elif is_quant_trader(_lid) and _q_reddit_hist:
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
                and not _reddit_tool_message_no_data(last_msg)
            )
            # SUMMARIZE_NEW_CONTEXT con solo URL de Reddit debe poder forzar Reddit (fetch); STORED con URLs en
            # el volcado no debe robar el turno (sintetizar snapshot DuckDB).
            # Quant: enlace Reddit pegado solo (sin directiva) también debe forzar reddit_* (evita alucinación).
            _quant_lone_reddit_only = quant_trader_lone_reddit_url_message(
                str(_lid or ""), incoming, _reddit_anchor_u
            )
            if (
                _reddit_tools_paused()
                and _reddit_anchor_u
                and (_quant_lone_reddit_only or _incoming_has_reddit_url(incoming))
                and not already_has_tool_result
            ):
                _paused_ai = AIMessage(
                    content=(
                        "🔴 Reddit pausado (`DUCKCLAW_REDDIT_PAUSED=1`). "
                        "No se invocaron herramientas reddit_* en este turno."
                    )
                )
                _out_rp = {**state, "messages": state["messages"] + [_paused_ai]}
                _out_rp.update(_identity_fields(state))
                return _out_rp
            _visual_calls_this_turn = _visual_asset_calls_since_last_human(state.get("messages") or [])
            _visual_tool_already_ok = bool(
                already_has_tool_result
                and isinstance(last_msg, ToolMessage)
                and (last_msg.name or "") == "generate_visual_asset"
                and '"ok":true' in str(last_msg.content or "").replace(" ", "")
            )
            force_visual = bool(
                is_quant_trader(_lid)
                and has_generate_visual
                and _quant_trader_visual_generation_intent(incoming)
                and not telegram_context_summarize_directive
                and not summarize_stored_directive
                and _visual_calls_this_turn == 0
                and not already_has_tool_result
                and not _visual_tool_already_ok
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_portfolio
                    or force_fmp
                    or force_tavily
                )
            )
            _visual_tool_failed = bool(
                is_quant_trader(_lid)
                and already_has_tool_result
                and isinstance(last_msg, ToolMessage)
                and (last_msg.name or "") == "generate_visual_asset"
                and '"ok":false' in str(last_msg.content or "").replace(" ", "")
                and _quant_trader_visual_generation_intent(incoming)
            )
            if _visual_tool_failed:
                err_msg = "No pude generar la imagen."
                try:
                    payload = json.loads(str(last_msg.content or ""))
                    if isinstance(payload, dict) and payload.get("error"):
                        err_msg = str(payload["error"])
                except (json.JSONDecodeError, TypeError):
                    pass
                if "cancelad" in err_msg.lower():
                    err_msg = (
                        f"{err_msg} Si enviaste otro mensaje mientras generaba, "
                        "espera a que termine ComfyUI (~3 min en Mac) antes de escribir de nuevo."
                    )
                _fail_ai = AIMessage(content=f"⚠️ {err_msg}")
                _out_fail = {**state, "messages": state["messages"] + [_fail_ai]}
                _out_fail.update(_identity_fields(state))
                return _out_fail

            if (
                _visual_tool_already_ok
                and is_quant_trader(_lid)
                and _quant_trader_visual_generation_intent(incoming)
            ):
                caption = "Imagen generada."
                try:
                    payload = json.loads(str(last_msg.content or ""))
                    if isinstance(payload, dict):
                        caption = str(payload.get("message") or caption).strip() or caption
                except (json.JSONDecodeError, TypeError):
                    pass
                _ok_ai = AIMessage(content=caption)
                _out_ok = {**state, "messages": state["messages"] + [_ok_ai]}
                _out_ok.update(_identity_fields(state))
                return _out_ok

            _allow_reddit_force = bool(
                is_finanz(_lid)
                or (
                    is_quant_trader(_lid)
                    and (
                        telegram_context_summarize_directive
                        or _quant_lone_reddit_only
                        or _q_reddit_hist
                    )
                )
            )
            force_reddit = bool(
                not force_visual
                and not _reddit_tools_paused()
                and
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
            # Tras 2× reddit_search_reddit en /s/… el MCP suele seguir sin el hilo correcto; si no cortamos,
            # el LLM re-invoca reddit_search en bucle (evidencia: pm2 logs 13:52, forced_tool=auto).
            _reddit_share_mcp_exhausted = bool(
                _worker_use_heuristic_first_tool(spec)
                and _allow_reddit_force
                and bool(share_slug)
                and bool(_reddit_anchor_u)
                and _incoming_has_reddit_share_path(str(_reddit_anchor_u))
                and reddit_search_tool_count >= 2
            )

            if not _worker_use_heuristic_first_tool(spec):
                force_schema = False
                force_admin_sql = False
                # No borrar read_sql si finanz exige ledger real (cuentas/deudas/presupuestos).
                if not (
                    force_finanz_cuentas
                    or force_finanz_deudas
                    or force_finanz_presupuestos
                    or force_finanz_db_validation
                ):
                    force_read_sql = False
                force_portfolio = False
                force_fmp = False
                force_fmp_calendar = False
                force_tavily = False
                force_reddit = False
                force_visual = False

            _summarize_reddit_empty_tavily = bool(
                is_quant_trader(_lid)
                and telegram_context_summarize_directive
                and has_tavily
                and _incoming_has_reddit_url(incoming)
                and already_has_tool_result
                and isinstance(last_msg, ToolMessage)
                and _reddit_tool_message_no_data(last_msg)
            )
            force_tavily = bool(force_tavily or _summarize_reddit_empty_tavily)

            # Misma heurística OHLCV que Finanz: Quant Trader también expone fetch_market_data y la usa como
            # evidencia obligatoria antes de propose_trade_signal (quant_trader_bridge); forzar la tool evita
            # alucinaciones en pedidos explícitos de velas/descarga. No aplica a portfolio IBKR (force_portfolio).
            _lid_l = (_lid or "").strip().lower()
            _ibgw_url = (os.environ.get("IBKR_GATEWAY_OHLCV_URL") or "").strip()
            # Quant Trader: si hay URL dedicada al GET /api/market/ibkr/historical, forzar esa tool en lugar
            # de fetch_market_data (evita lake+HTTP genérico cuando el usuario configuró solo IB Gateway).
            force_fetch_ib_gateway = bool(
                _lid_l == WORKER_QUANT_TRADER
                and has_fetch_ib_gateway
                and bool(_ibgw_url)
                and _finanz_user_requests_ohlcv_ingest(incoming)
                and _summarize_ok_for_forced_ohlcv
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
                _lid_l in MARKET_WORKERS
                and has_fetch_market
                and _finanz_user_requests_ohlcv_ingest(incoming)
                and not force_fetch_ib_gateway
                and _summarize_ok_for_forced_ohlcv
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
                _lid_l == WORKER_QUANT_TRADER
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
                _lid_l == WORKER_QUANT_TRADER
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
            _quant_explicit_evaluate_request = bool(
                _lid_l == WORKER_QUANT_TRADER
                and has_evaluate_cfd_state
                and (
                    "evaluate_cfd_state" in _incoming_l
                    or (
                        re.search(r"\b(eval(úa|ua|uar|uacion|uación)|evaluat(e|ion))\b", _incoming_l)
                        and re.search(r"\bcfd\b", _incoming_l)
                    )
                )
            )
            if (
                _quant_explicit_evaluate_request
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

            _quant_explicit_backtest_sandbox_request = bool(
                _lid_l == WORKER_QUANT_TRADER
                and (
                    "backtest" in _incoming_l
                    or "backtesting" in _incoming_l
                    or "retrotest" in _incoming_l
                    or "sandbox" in _incoming_l
                )
            )
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
            _plot_capable_worker = normalize_worker_id(_lid) in PLOT_CAPABLE_WORKERS
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
            _quant_explicit_sandbox_first_tool = bool(
                _lid_l == WORKER_QUANT_TRADER
                and has_run_sandbox
                and _quant_explicit_backtest_sandbox_request
            )
            force_run_sandbox = bool(
                has_run_sandbox
                and (
                    (_plot_capable_worker and _is_graph_request)
                    or _quant_explicit_sandbox_first_tool
                )
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
                    and is_finanz(_lid)
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

            if (
                not _orch
                and is_finanz(_lid)
                and "get_current_time" in tools_by_name
                and _finanz_should_force_current_time(incoming)
                and not telegram_context_summarize_directive
                and not already_has_tool_result
            ):
                _lh_finanz_gct = _quant_last_human_index(state.get("messages") or [])
                if not _quant_tool_called_since(
                    state.get("messages") or [], _lh_finanz_gct, "get_current_time"
                ):
                    _forced_tid_finanz_gct = f"call_finanz_get_current_time_{int(time.time() * 1000)}"
                    _forced_tc_finanz_gct = [
                        {
                            "name": "get_current_time",
                            "args": {},
                            "id": _forced_tid_finanz_gct,
                            "type": "tool_call",
                        }
                    ]
                    _log.info("[%s] finanz deterministic → get_current_time", _wl)
                    _out_finanz_gct = {
                        **state,
                        "messages": state["messages"]
                        + [AIMessage(content="", tool_calls=_forced_tc_finanz_gct)],
                    }
                    _out_finanz_gct.update(_identity_fields(state))
                    return _out_finanz_gct

            force_pqrsd_fetch_canonical = bool(
                _lid_l == WORKER_PQRSD_ASSISTANT
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
                _lid_l == WORKER_QUANT_TRADER
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
                _lid_l == WORKER_QUANT_TRADER
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

            _quant_proceed_like = bool(_lid_l == WORKER_QUANT_TRADER and _quant_is_proceed_like(incoming))
            _quant_deterministic_cycle = bool(
                _lid_l == WORKER_QUANT_TRADER
                and _worker_use_heuristic_first_tool(spec)
                and not telegram_context_summarize_directive
                and (
                    _wants_new_signal
                    or _is_goals_tick_msg
                    or _quant_proceed_like
                )
            )
            _quant_vlm_read_sql_evidence = bool(
                _lid_l == WORKER_QUANT_TRADER
                and has_read_sql
                and _worker_use_heuristic_first_tool(spec)
                and not telegram_context_summarize_directive
                and not summarize_stored_directive
                and not already_has_tool_result
                and not _quant_deterministic_cycle
                and _quant_trader_vlm_incoming_suggests_market_figure(incoming)
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
            if _quant_vlm_read_sql_evidence:
                force_read_sql = True
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
                _lid_l == WORKER_QUANT_TRADER
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
            if (
                _quant_can_force_pipeline_step
                and _has_fetch_since_last_human
                and not _has_portfolio_since_last_human
                and ibkr_session_on
            ):
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
                _lid_l == WORKER_QUANT_TRADER
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

            _reddit_comments_for_http: Optional[str] = None
            if _reddit_resolved_comments_url:
                _reddit_comments_for_http = _reddit_resolved_comments_url
            elif _reddit_anchor_u and _REDDIT_COMMENTS_IN_URL_RE.search(_reddit_anchor_u):
                _reddit_comments_for_http = _reddit_anchor_u.split("#")[0].split("?")[0].rstrip("/")
            _quant_reddit_http_fast = bool(
                (_lid_l == WORKER_QUANT_TRADER or is_quant_trader(_lid))
                and (_quant_lone_reddit_only or _q_reddit_hist)
                and not has_reddit_tools
                and _reddit_comments_for_http
                and not already_has_tool_result
                and not force_visual
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_portfolio
                    or force_fmp
                    or force_tavily
                )
            )
            _reddit_http_prefetch_ctx: Optional[str] = None
            if _quant_reddit_http_fast:
                _raw_reddit_json = _fetch_reddit_post_via_public_json(_reddit_comments_for_http)
                if _raw_reddit_json:
                    from duckclaw.utils.formatters import build_reddit_llm_context_block

                    _reddit_http_prefetch_ctx = build_reddit_llm_context_block(_raw_reddit_json)
                    _log.info(
                        "[%s] quant reddit HTTP prefetch → LLM context (no reddit_* tools) lone=%s hist=%s",
                        _wl,
                        _quant_lone_reddit_only,
                        _q_reddit_hist,
                    )

            _has_run_browser = "run_browser_sandbox" in tools_by_name
            _has_tavily_mql5 = "tavily_search" in tools_by_name
            _quant_lone_mql5_url = bool(
                _lid_l == WORKER_QUANT_TRADER
                and _LONE_HTTP_URL_ONLY_LINE.match((incoming or "").strip())
                and "mql5.com" in (incoming or "").lower()
            )
            if _quant_lone_mql5_url and not already_has_tool_result and not force_visual:
                from duckclaw.graphs.sandbox import browser_image_available

                _mql5_url = (incoming or "").strip()
                _forced_tid_m = f"call_mql5_{int(time.time() * 1000)}"
                _use_browser = bool(
                    sandbox_enabled and _has_run_browser and browser_image_available()
                )
                if _use_browser:
                    _tool_name_m = "run_browser_sandbox"
                    _tool_args_m: dict[str, Any] = {"url": _mql5_url}
                    _route = "browser"
                elif _has_tavily_mql5:
                    _tool_name_m = "tavily_search"
                    _tool_args_m = {"query": _mql5_url}
                    _route = "tavily_fallback"
                else:
                    _tool_name_m = ""
                    _tool_args_m = {}
                    _route = "unavailable"
                if _tool_name_m:
                    _forced_tc_m = [
                        {
                            "name": _tool_name_m,
                            "args": _tool_args_m,
                            "id": _forced_tid_m,
                            "type": "tool_call",
                        }
                    ]
                    _log.info(
                        "[%s] quant deterministic mql5 → %s url=%r",
                        _wl,
                        _route,
                        _mql5_url[:120],
                    )
                    _forced_resp_m = AIMessage(content="", tool_calls=_forced_tc_m)
                    _out_m = {**state, "messages": state["messages"] + [_forced_resp_m]}
                    _out_m.update(_identity_fields(state))
                    return _out_m

            if (
                _lid_l == WORKER_QUANT_TRADER
                and _LONE_HTTP_URL_ONLY_LINE.match((incoming or "").strip())
                and already_has_tool_result
                and isinstance(last_msg, ToolMessage)
                and len(str(last_msg.content or "")) > 80
            ):
                _tname = (last_msg.name or "").strip()
                _tool_body = str(last_msg.content or "").strip()
                _fast_reply: str | None = None
                if _tname.startswith("reddit_"):
                    # Reddit: segunda pasada del LLM con ToolMessage en historial (no solo tarjeta).
                    pass
                elif _tname in ("tavily_search", "run_browser_sandbox") and "mql5.com" in (
                    (incoming or "").lower()
                ):
                    _fast_reply = _tool_body[:3500] + ("…" if len(_tool_body) > 3500 else "")
                if _fast_reply:
                    _url_reply = AIMessage(content=_fast_reply)
                    _log.info("[%s] quant lone-url fast exit after tool=%s", _wl, _tname)
                    _out_url = {
                        **state,
                        "messages": state["messages"] + [_url_reply],
                    }
                    _out_url.update(_identity_fields(state))
                    return _out_url

            if (
                force_visual
                and has_generate_visual
                and not already_has_tool_result
                and not _visual_tool_already_ok
            ):
                _vis_prompt = _quant_visual_prompt_from_incoming(incoming)
                _forced_tid = f"call_generate_visual_{int(time.time() * 1000)}"
                _forced_tc = [
                    {
                        "name": "generate_visual_asset",
                        "args": {
                            "prompt": _vis_prompt,
                            "negative_prompt": "",
                            "aspect_ratio": "1:1",
                        },
                        "id": _forced_tid,
                        "type": "tool_call",
                    }
                ]
                _log.info(
                    "[%s] quant deterministic visual → generate_visual_asset prompt=%r",
                    _wl,
                    _vis_prompt[:120],
                )
                _forced_resp = AIMessage(content="", tool_calls=_forced_tc)
                _out_vis = {**state, "messages": state["messages"] + [_forced_resp]}
                _out_vis.update(_identity_fields(state))
                return _out_vis

            if sandbox_enabled:
                llm_with_tools = llm_with_tools_on if ibkr_session_on else llm_with_tools_ibkr_off
            else:
                llm_with_tools = (
                    llm_with_tools_off if ibkr_session_on else llm_with_tools_sandbox_ibkr_off
                )
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
                                            "generate_visual_asset"
                                            if force_visual
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
                is_pqrsd_assistant(_lid)
                and not already_has_tool_result
                and _pqrsd_datos_first_over_forced_fetch(incoming)
            )
            if _pqrsd_inject_datos_first_directive:
                _msg_list = [
                    SystemMessage(content=load_guardrail("directives", "pqrsd_datos_primero"))
                ] + _msg_list
            if not _worker_use_heuristic_first_tool(spec):
                _msg_list = [
                    SystemMessage(content=load_guardrail("directives", "tool_choice_generic"))
                ] + _msg_list
            _quant_autoexec_validation_intent = bool(
                is_quant_trader(_lid)
                and _quant_user_requests_autoexec_validation(incoming)
                and not telegram_context_summarize_directive
            )
            if _quant_autoexec_validation_intent:
                _msg_list = [
                    SystemMessage(content=load_guardrail("directives", "quant_autoexec"))
                ] + _msg_list
            if (
                is_quant_trader(_lid)
                and telegram_context_summarize_directive
            ):
                _msg_list = [
                    SystemMessage(content=load_guardrail("directives", "quant_ohlcv_moc"))
                ] + _msg_list
            _qp_ctx = state.get("quant_pipeline_context")
            if (
                is_quant_trader(_lid)
                and isinstance(_qp_ctx, dict)
                and _quant_deterministic_cycle
                and _has_fetch_since_last_human
                and _has_eval_since_last_human
            ):
                _msg_list = [
                    SystemMessage(
                        content=load_guardrail("directives", "quant_pipeline_deterministic")
                    )
                ] + _msg_list
            if _reddit_share_mcp_exhausted:
                _msg_list = [
                    SystemMessage(content=load_guardrail("directives", "reddit_share_exhausted"))
                ] + _msg_list
            if is_quant_trader(_lid) and _visual_tool_already_ok:
                _msg_list = [
                    SystemMessage(
                        content=(
                            "La imagen ya fue generada con generate_visual_asset en este turno. "
                            "Responde al usuario con la ruta/artefacto; NO vuelvas a llamar "
                            "generate_visual_asset ni edit_visual_asset."
                        )
                    )
                ] + _msg_list
            _reddit_ctx_block: Optional[str] = None
            if _reddit_http_prefetch_ctx and not already_has_tool_result:
                _reddit_ctx_block = _reddit_http_prefetch_ctx
            if not _reddit_ctx_block:
                for _rm in reversed(_msg_list):
                    if isinstance(_rm, ToolMessage) and str(getattr(_rm, "name", "") or "").startswith(
                        "reddit_"
                    ):
                        from duckclaw.utils.formatters import build_reddit_llm_context_block

                        _reddit_ctx_block = build_reddit_llm_context_block(str(_rm.content or ""))
                        break
            if _reddit_ctx_block:
                _msg_list = [SystemMessage(content=_reddit_ctx_block)] + _msg_list
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
            elif force_visual:
                _fgv = llm_force_generate_visual_on if sandbox_enabled else llm_force_generate_visual_off
                _invoked_llm = _fgv or llm_with_tools
            elif force_reddit:
                _fr = None
                if _reddit_resolved_comments_url and _incoming_looks_like_reddit_post_url(
                    _reddit_resolved_comments_url
                ):
                    _fr = llm_force_reddit_post_on if sandbox_enabled else llm_force_reddit_post_off
                elif _incoming_has_reddit_share_path(incoming_for_reddit):
                    # Enlace /s/ sin URL canónica resuelta: forzar reddit_get_post; el parche posterior
                    # sustituye por reddit_search_reddit(query=r/<sub> shortlink <slug>). Forzar search
                    # directo empujaba query=URL y el MCP fallaba (evidencia: children undefined).
                    _fr = llm_force_reddit_post_on if sandbox_enabled else llm_force_reddit_post_off
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
            if _reddit_share_mcp_exhausted and _invoked_llm is llm_with_tools:
                _bind_base_ex = _tools_for_llm_bind if sandbox_enabled else _tools_sandbox_off_bind
                _nr_ex = [
                    t
                    for t in _bind_base_ex
                    if not str(getattr(t, "name", "") or "").startswith("reddit_")
                ]
                _invoked_llm = _bind_tools(llm, _nr_ex)
            _llm_invoke_exc: BaseException | None = None
            try:
                from duckclaw.integrations.llm_providers import invoke_chat_model_with_transient_retries

                resp = invoke_chat_model_with_transient_retries(_invoked_llm, _groq_msgs)
                _lid_lower_for_reddit_patch = (_lid or "").strip().lower()
                if (
                    normalize_worker_id(_lid_lower_for_reddit_patch) in MARKET_WORKERS
                    and resp is not None
                    and getattr(resp, "tool_calls", None)
                ):
                    _ru_share = _first_reddit_url_in_text(incoming_for_reddit)
                    if (
                        _ru_share
                        and _incoming_has_reddit_share_path(_ru_share)
                        and not _reddit_resolved_comments_url
                    ):
                        resp = _patch_ai_reddit_share_tool_calls(
                            resp, _ru_share, attempt_index=reddit_search_tool_count
                        )
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
            if (
                (_lid_l == WORKER_FINANZ)
                and force_finanz_admin_sql
                and not tool_calls
                and _llm_invoke_exc is None
                and not already_has_tool_result
                and _finanz_hallucinated_balance_write_reply(incoming, str(getattr(resp, "content", "") or ""))
            ):
                resp = AIMessage(
                    content=(
                        "No ejecuté `admin_sql` en este turno; el saldo en DuckDB **no** cambió. "
                        "Reintenta el mensaje (p. ej. «Actualiza el saldo de Efectivo a 46400 COP»)."
                    )
                )
                tool_calls = []
            _is_goals_tick = (
                str(incoming or "").strip().startswith("[SYSTEM_EVENT:")
                and proactive_review_event_phrase_in_text(str(incoming or ""))
            )
            if force_portfolio and ibkr_session_on and _is_goals_tick and not tool_calls:
                _forced_tid = f"call_forced_ibkr_{int(time.time() * 1000)}"
                forced_tc = [{"name": "get_ibkr_portfolio", "args": {}, "id": _forced_tid, "type": "tool_call"}]
                try:
                    resp = resp.model_copy(update={"tool_calls": forced_tc})
                except Exception:
                    resp = AIMessage(content=str(getattr(resp, "content", "") or ""), tool_calls=forced_tc)
                tool_calls = getattr(resp, "tool_calls", None) or forced_tc
            _is_quant_forced_without_tools = (
                (_lid_l == WORKER_QUANT_TRADER)
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
            if (_lid_l == WORKER_QUANT_TRADER) and force_quant_propose_signal and not tool_calls:
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
            _resp_content = ""
            try:
                from duckclaw.integrations.llm_providers import lc_message_content_to_text

                _resp_content = (lc_message_content_to_text(resp) or "").strip()
            except Exception:
                _resp_content = str(getattr(resp, "content", "") or "").strip()
            _lh_gct_fix = _quant_last_human_index(state.get("messages") or [])
            _quant_vlm_post_tools = _quant_vlm_post_tools_synthesis(
                state.get("messages") or [],
                incoming,
                last_human_idx=_lh_gct_fix,
                already_has_tool_result=already_has_tool_result,
            )
            _json_echo = _reply_is_quant_tool_json_echo(_resp_content)
            _gct_lone_url_skip = _market_worker_gct_only_lone_url_no_repair(
                incoming,
                state.get("messages") or [],
                last_human_idx=_lh_gct_fix,
            )
            _inline_repair_gate = _quant_vlm_post_tools or (
                _json_echo and not _gct_lone_url_skip
            )
            _inline_will_synth = bool(
                not tool_calls
                and _llm_invoke_exc is None
                and is_market_worker(_lid)
                and _inline_repair_gate
                and (not _resp_content or _json_echo)
            )
            _market_inline_synth_attempted = False
            if (
                not tool_calls
                and _llm_invoke_exc is None
                and is_market_worker(_lid)
                and _inline_repair_gate
                and (
                    not _resp_content
                    or _reply_is_quant_tool_json_echo(_resp_content)
                )
            ):
                _market_inline_synth_attempted = True
                _gct_data = (
                    _parse_get_current_time_json(_resp_content)
                    or _quant_latest_tool_json_since(
                        state.get("messages") or [], _lh_gct_fix, "get_current_time"
                    )
                    or {}
                )
                _day = str(_gct_data.get("day_of_week") or "")
                _tm = str(_gct_data.get("time") or "")[:5]
                _clock_hint = f"{_day} {_tm} COT".strip() if (_day or _tm) else ""
                _brand = _market_worker_egress_brand(_lid)
                _tools_ran = [
                    str(getattr(m, "name", "") or "")
                    for m in (state.get("messages") or [])[max(0, _lh_gct_fix + 1) :]
                    if isinstance(m, ToolMessage)
                ]
                _tools_hint = ", ".join(dict.fromkeys(_tools_ran)) if _tools_ran else "herramientas"
                _follow_sys = SystemMessage(
                    content=(
                        f"Ya ejecutaste {_tools_hint} en este turno. "
                        + (f"Encabezado {_brand} con {_clock_hint}. " if _clock_hint else "")
                        + "Redacta el análisis macro/financiero completo en español integrando el contexto visual "
                        "y los resultados de herramientas. PROHIBIDO pegar JSON crudo de herramientas."
                    )
                )
                try:
                    resp = invoke_chat_model_with_transient_retries(
                        _invoked_llm, list(_groq_msgs) + [_follow_sys]
                    )
                    try:
                        from duckclaw.integrations.llm_providers import lc_message_content_to_text

                        _resp_content = (lc_message_content_to_text(resp) or "").strip()
                    except Exception:
                        _resp_content = str(getattr(resp, "content", "") or "").strip()
                    tool_calls = getattr(resp, "tool_calls", None) or []
                except Exception as exc:
                    _log.warning("[%s] quant vlm post-tools synthesis retry failed: %s", _wl, exc)
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
                            "Revision /crons (proactiva): objetivo de sesion **rebalance_hrp**. "
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
                            "Revision /crons (proactiva): objetivo de sesion **overnight_gap_squeeze**. "
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
                                "Revision /crons (proactiva): "
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
                                "Revision /crons (proactiva): "
                                f"snapshot IBKR OK (valor total=${_total_value or 'N/D'}, posiciones={_positions or 'N/D'}). "
                                "Meta 'PnL positivo': estado parcial por falta de PnL realizado/no realizado en este snapshot. "
                                "Accion sugerida: extraer PnL por posicion y activar reduccion de riesgo si el agregado pasa a negativo."
                            )
                    elif _portfolio_tool_text:
                        _fallback_text = (
                            "Revision /crons (proactiva): snapshot IBKR recibido. "
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
            if (
                not tool_calls
                and "get_current_time" in tools_by_name
            ):
                _lh_idx_gct = _quant_last_human_index(state.get("messages") or [])
                _msgs_gct = state.get("messages") or []
                _needs_gct = not _quant_tool_called_since(
                    _msgs_gct, _lh_idx_gct, "get_current_time"
                ) and (
                    (
                        is_quant_trader(_lid)
                        and _quant_trader_should_force_current_time(incoming)
                    )
                    or (
                        (_lid_l == WORKER_FINANZ)
                        and _finanz_should_force_current_time(incoming)
                    )
                    or _response_mentions_wall_clock(_resp_content)
                )
                if _needs_gct:
                    _forced_tid_gct = f"call_forced_get_current_time_{int(time.time() * 1000)}"
                    forced_tc_gct = [
                        {
                            "name": "get_current_time",
                            "args": {},
                            "id": _forced_tid_gct,
                            "type": "tool_call",
                        }
                    ]
                    try:
                        resp = resp.model_copy(
                            update={"tool_calls": forced_tc_gct, "content": ""}
                        )
                    except Exception:
                        resp = AIMessage(content="", tool_calls=forced_tc_gct)
                    tool_calls = forced_tc_gct
            out = {**state, "messages": state["messages"] + [resp]}
            if _market_inline_synth_attempted:
                out["market_inline_synthesis_attempted"] = True
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
        ibkr_session_on = has_ibkr and _ibkr_enabled_for_state(state)
        tool_lookup = tools_by_name if sandbox_enabled else tools_by_name_sandbox_off
        if not ibkr_session_on:
            tool_lookup = {k: v for k, v in tool_lookup.items() if k != "get_ibkr_portfolio"}
        sandbox_b64: str | None = state.get("sandbox_photo_base64") if isinstance(state.get("sandbox_photo_base64"), str) else None
        visual_artifact_id: str | None = (
            str(state.get("visual_artifact_id") or "").strip() or None
        )
        _hb_head = (state.get("subagent_instance_label") or "").strip() or None
        _hb_uname = (state.get("username") or "").strip() or None
        _hb_plan = (state.get("heartbeat_plan_title") or "").strip() or None
        _hb_tok = (state.get("outbound_telegram_bot_token") or "").strip() or None

        _duck_exts = list(getattr(spec, "duckdb_extensions", None) or [])
        # DuckDB mismo PID: sesión principal RW (read_only=False) + connect RO efímero al mismo archivo →
        # "different configuration than existing" (pm2 finanz 2026-05-12). Quant-Trader RO sigue pudiendo
        # desactivar pool vía manifest por contención con db-writer.
        use_ephemeral_parallel = (
            read_pool.read_pool_active_for_worker(spec)
            and read_pool.should_parallelize_ephemeral_tool_calls(tool_calls)
            and bool(getattr(spec, "read_only", False))
        )

        def _notify_admin_tool_phase(
            tool_name: str,
            phase: str,
            detail: str = "",
            *,
            elapsed_ms: float | None = None,
        ) -> None:
            _hcid = str(state.get("chat_id") or state.get("session_id") or "").strip()
            if not _hcid:
                return
            try:
                from duckclaw.graphs.chat_heartbeat import (
                    is_admin_ui_chat_session,
                    publish_admin_tool_event,
                )

                if not is_admin_ui_chat_session(_hcid):
                    return
                publish_admin_tool_event(
                    _hcid,
                    tool_name,
                    phase,
                    worker_id=(_hb_head or worker_id or "").strip() or None,
                    detail=detail,
                    elapsed_ms=elapsed_ms,
                )
            except Exception:
                pass

        def _schedule_tool_heartbeat(tool_name: str) -> None:
            _htid = (state.get("tenant_id") or "default").strip() or "default"
            _hcid = str(state.get("chat_id") or state.get("session_id") or "").strip()
            _huid = str(state.get("user_id") or "").strip() or _hcid
            try:
                from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

                _admin_ui = is_admin_ui_chat_session(_hcid)
            except Exception:
                _admin_ui = False
            if _admin_ui:
                _notify_admin_tool_phase(tool_name, "start")
                return
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
                _tool_t0 = time.perf_counter()
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
                    _notify_admin_tool_phase(
                        name,
                        "error",
                        str(e)[:240],
                        elapsed_ms=(time.perf_counter() - _tool_t0) * 1000,
                    )
                else:
                    _notify_admin_tool_phase(
                        name,
                        "done",
                        "",
                        elapsed_ms=(time.perf_counter() - _tool_t0) * 1000,
                    )
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
                    _tool_t0: float | None = None
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
                            _cid_sb = str(state.get("chat_id") or state.get("session_id") or "").strip()
                            if _cid_sb and not str(invoke_args.get("chat_id") or "").strip():
                                invoke_args["chat_id"] = _cid_sb
                            if _cid_sb and not str(invoke_args.get("session_id") or "").strip():
                                from duckclaw.graphs.novnc_registry import sanitize_chat_to_session_id

                                invoke_args["session_id"] = sanitize_chat_to_session_id(_cid_sb)
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
                            _cid_sb = str(invoke_args.get("chat_id") or state.get("chat_id") or "").strip()
                            _vnc_pre = (
                                ensure_browser_novnc_session(
                                    worker_id,
                                    _sid,
                                    db=db,
                                    chat_id=_cid_sb or None,
                                )
                                if _sid
                                else None
                            )
                            _schedule_run_browser_novnc_tool_heartbeat(
                                state,
                                routing_worker_id=worker_id,
                                vnc_url=_vnc_pre,
                                novnc_session_id=_sid or "",
                            )
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
                        _tool_t0 = time.perf_counter()
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
                        if name in ("generate_visual_asset", "edit_visual_asset"):
                            try:
                                payload = json.loads(content)
                                if isinstance(payload, dict) and payload.get("ok"):
                                    aid = str(payload.get("artifact_id") or "").strip()
                                    if aid:
                                        visual_artifact_id = aid
                                        try:
                                            from duckclaw.graphs.chat_heartbeat import (
                                                is_admin_ui_chat_session,
                                                publish_admin_chat_heartbeat,
                                            )
                                            from duckclaw.forge.skills.quant_tool_context import (
                                                get_quant_tool_tenant_id,
                                            )

                                            _cid = str(state.get("chat_id") or "").strip()
                                            if _cid and is_admin_ui_chat_session(_cid):
                                                _hb_tid = get_quant_tool_tenant_id()
                                                publish_admin_chat_heartbeat(
                                                    _cid,
                                                    "Imagen generada (ComfyUI)",
                                                    kind="visual",
                                                    artifact_id=aid,
                                                    artifact_tenant_id=_hb_tid,
                                                )
                                        except Exception:
                                            pass
                                    fb = payload.get("figure_base64")
                                    if isinstance(fb, str) and len(fb) > 32:
                                        sandbox_b64 = fb
                                    elif payload.get("artifacts"):
                                        from duckclaw.forge.skills.comfyui_bridge import (
                                            read_artifact_image_as_b64,
                                        )
                                        from duckclaw.forge.skills.quant_tool_context import (
                                            get_quant_tool_tenant_id,
                                        )

                                        arts = payload.get("artifacts")
                                        if isinstance(arts, list) and arts:
                                            first = str(arts[0] or "").strip()
                                            if first:
                                                b64_art = read_artifact_image_as_b64(
                                                    first,
                                                    get_quant_tool_tenant_id(),
                                                )
                                                if b64_art:
                                                    sandbox_b64 = b64_art
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
                        _admin_detail = _prev
                        if name in ("read_sql", "admin_sql", "inspect_schema", "get_schema_info"):
                            _admin_detail = ""
                        elif name == "run_browser_sandbox":
                            try:
                                _bp = json.loads(content)
                                if isinstance(_bp, dict) and _bp.get("browser_image_missing"):
                                    _admin_detail = str(_bp.get("hint") or _admin_detail)[:240]
                            except (json.JSONDecodeError, TypeError):
                                pass
                        _notify_admin_tool_phase(
                            name,
                            "done",
                            _admin_detail,
                            elapsed_ms=(time.perf_counter() - _tool_t0) * 1000,
                        )
                    except Exception as e:
                        content = f"Error: {e}"
                        _log.warning("[%s] tool=%s failed: %s", _wl, name, e)
                        _notify_admin_tool_phase(
                            name,
                            "error",
                            str(e)[:240],
                            elapsed_ms=(
                                (time.perf_counter() - _tool_t0) * 1000 if _tool_t0 is not None else None
                            ),
                        )
                else:
                    if name == "get_ibkr_portfolio" and has_ibkr and not ibkr_session_on:
                        content = _ibkr_disabled_chat_hint()
                    elif not sandbox_enabled and name in (
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
        if visual_artifact_id:
            out["visual_artifact_id"] = visual_artifact_id
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
            finanz_repair_ibkr_tool_live_vs_reply_paper,
            finanz_strip_ibkr_block_without_tool_in_turn,
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
        from langchain_core.messages import ToolMessage

        def _notify_final_heartbeat() -> None:
            from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

            _cid_hb = str(state.get("chat_id") or state.get("session_id") or "").strip()
            if is_admin_ui_chat_session(_cid_hb):
                return
            _tid = (state.get("tenant_id") or "default").strip() or "default"
            _cid = _cid_hb
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
        if is_finanz(getattr(spec, "worker_id", "")):
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
        _visual_only_turn = bool(
            is_quant_trader(_spec_logical_worker_id(spec))
            and _quant_visual_tool_succeeded_in_turn(list(msgs) if msgs else [])
            and (
                (state.get("sandbox_photo_base64") or "").strip()
                or (state.get("visual_artifact_id") or "").strip()
            )
        )
        if _visual_only_turn:
            _short = (reply or "").strip()
            if not _short or len(_short) > 240:
                _short = "Imagen generada."
            reply = _short
        else:
            _spec_lid = _spec_logical_worker_id(spec)
            _lh_repair = _quant_last_human_index(list(msgs) if msgs else [])
            _egress_needs_repair = _market_worker_needs_egress_repair(
                list(msgs) if msgs else [],
                _inc_for_ctx,
                reply or "",
                last_human_idx=_lh_repair,
                worker_id=_spec_lid,
            )
            if _egress_needs_repair:
                _inline_synth_done = bool(state.get("market_inline_synthesis_attempted"))
                _skip_llm_synth = _inline_synth_done and bool((reply or "").strip())
                reply = _repair_quant_vlm_tool_egress_reply(
                    llm,
                    spec,
                    _inc_for_ctx,
                    reply or "",
                    msgs,
                    skip_llm_synthesis=_skip_llm_synth,
                )
                if _reply_is_quant_tool_json_echo(reply or ""):
                    _det_egress = _deterministic_market_worker_tool_summary(
                        list(msgs), _lh_repair, _spec_lid, _inc_for_ctx
                    )
                    if _det_egress and not _reply_is_quant_tool_json_echo(_det_egress):
                        reply = _det_egress
            reply = _repair_finanz_ibkr_egress(_apply_nl_synthesis(reply or ""))
        _wid_fin = str(getattr(spec, "worker_id", "") or "")
        reply = finanz_repair_ibkr_tool_live_vs_reply_paper(msgs, reply, worker_id=_wid_fin)
        reply = finanz_strip_ibkr_block_without_tool_in_turn(
            msgs,
            reply,
            worker_id=_wid_fin,
            user_ask=_inc_for_ctx,
        )
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
            _spec_lid_fb = _spec_logical_worker_id(spec)
            _lh_fb = _quant_last_human_index(list(msgs))
            if (not reply or reply.strip().lower() in ("sin respuesta.", "sin respuesta")):
                _det = _deterministic_market_worker_tool_summary(
                    list(msgs), _lh_fb, _spec_lid_fb, _inc_for_ctx
                )
                if _det:
                    reply = sanitize_worker_reply_text(_det)
                else:
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
        aid = (state.get("visual_artifact_id") or "").strip()
        if aid:
            out["visual_artifact_id"] = aid
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
