"""DB intent policy for worker routing.

This module owns text heuristics that decide whether a user is asking about
DuckDB schema/table data. WorkerFactory imports these decisions instead of
embedding DB intent policy in graph assembly code.
"""

from __future__ import annotations

import re

NO_TASK_PATTERN = re.compile(
    r"^(hola|hi|hey|buenos?\s*d[ií]as?|buenas?\s*tardes?|buenas?\s*noches?|"
    r"qu[eé]\s*tal|qu[eé]\s*hay|saludos?|hello|ciao|adios?|chao)\s*[!.]?$",
    re.IGNORECASE,
)
LONE_HTTP_URL_ONLY_LINE = re.compile(r"^\s*https?://[^\s]+\s*$", re.I)
TABLE_CONTENT_PHRASE = re.compile(
    r"\b(que\s+hay\s+en\s+la\s+tabla|qué\s+hay\s+en\s+la\s+tabla|"
    r"hay\s+algo\s+en\s+(la\s+)?tabla|hay\s+datos\s+en\s+(la\s+)?tabla|"
    r"contenido\s+de\s+la\s+tabla|muestr(a|ame)\s+la\s+tabla|ver\s+datos\s+de\s+la\s+tabla|"
    r"registros?\s+de\s+la\s+tabla|filas?\s+de\s+la\s+tabla|select\s+\*\s+from|select\s+.+\s+from)\b",
    re.IGNORECASE,
)
SCHEMA_EXPLICIT_PHRASE = re.compile(
    r"\b(listar\s+tablas|tablas\s+disponibles|qu[ée]\s+tablas|que\s+tablas|"
    r"tablas\s+de\s+la\s+base|tablas\s+en\s+(la\s+)?(base|duckdb)|"
    r"show\s+tables|information_schema\.tables|"
    r"esquema\s+de\s+la\s+base|schema\s+de\s+la\s+base|estructura\s+de\s+la\s+base|"
    r"listar\s+(el\s+)?esquema|ver\s+(el\s+)?esquema|mostrar\s+(el\s+)?esquema|"
    r"nombre\s+de\s+la\s+db|nombre\s+db)\b",
    re.IGNORECASE,
)
SCHEMA_TABLE_NEAR_DB = re.compile(
    r"\b(tablas?|tables?)\b.{0,50}\b(duckdb|base\s+de\s+datos|information_schema)\b|"
    r"\b(duckdb|base\s+de\s+datos|information_schema)\b.{0,50}\b(tablas?|tables?)\b",
    re.IGNORECASE | re.DOTALL,
)
CONCRETE_TASK_KEYWORDS = re.compile(
    r"\b(db|database|base\s+de\s+datos|tablas?|tables?|esquema|schema|nombre\s+de\s+la\s+db|"
    r"qu[eé]\s+tablas|estructura|get_db_path|read_sql|admin_sql|consultar|registros?|datos\s+locales)\b",
    re.IGNORECASE,
)
PLANNED_TASK_PREFIX = (
    "TAREA:",
    "TAREA ",
    "Ejecuta la herramienta",
    "Ejecuta read_sql",
    "Ejecuta admin_sql",
    "Usa read_sql",
    "Usa admin_sql",
    "usa get_db_path",
)


def incoming_is_lone_http_url(text: str) -> bool:
    return bool(LONE_HTTP_URL_ONLY_LINE.match((text or "").strip()))


def incoming_is_manager_planned_guardrail_task(text: str) -> bool:
    raw = (text or "").strip()
    if not raw.lower().startswith("tarea:"):
        return False
    low = raw.lower()
    return "information_schema" in low or "show tables" in low or "lista de tablas" in low


def explicit_duckdb_schema_request(text: str) -> bool:
    raw = (text or "").strip()
    if not raw:
        return False
    if SCHEMA_EXPLICIT_PHRASE.search(raw):
        return True
    return bool(SCHEMA_TABLE_NEAR_DB.search(raw))


def explicit_duckdb_storage_request(text: str) -> bool:
    """True when the user explicitly wants DuckDB tools (schema, named tools, or SELECT).

    Used as the escape hatch when RAG inventory is injected into the turn: without this,
    ``read_sql`` / ``inspect_schema`` stay hidden even if the user asks for them by name.
    """
    if explicit_duckdb_schema_request(text):
        return True
    raw = (text or "").strip().lower()
    if not raw:
        return False
    if re.search(r"\b(read_sql|inspect_schema|admin_sql|get_db_path)\b", raw):
        return True
    if re.search(r"\bselect\s+\d+\b", raw) or re.search(r"\bselect\s+.+\s+as\b", raw):
        return True
    if re.search(r"\bcu[aá]ntas?\s+tablas?\b", raw):
        return True
    return False


def incoming_is_schema_query_heuristic(text: str) -> bool:
    if not text or not text.strip():
        return False
    if incoming_is_manager_planned_guardrail_task(text):
        return False
    if incoming_is_lone_http_url(text):
        return False
    t = text.strip().lower()
    if "read_sql" in t and "job_opportunities" in t:
        return False
    if re.search(r"\btabla\s+o\s+lista\b", t):
        return False
    if TABLE_CONTENT_PHRASE.search(t):
        return False
    return explicit_duckdb_schema_request(text)


def incoming_is_table_content_query(text: str) -> bool:
    if not text or not text.strip():
        return False
    t = text.strip().lower()
    if "read_sql" in t and "job_opportunities" in t:
        return True
    return bool(TABLE_CONTENT_PHRASE.search(t))


def is_no_task(incoming: str) -> bool:
    text = (incoming or "").strip()
    if not text:
        return True
    if len(text) < 4:
        return True
    if any(text.startswith(p) or p in text for p in PLANNED_TASK_PREFIX):
        return False
    if CONCRETE_TASK_KEYWORDS.search(text):
        return False
    return bool(NO_TASK_PATTERN.match(text))
