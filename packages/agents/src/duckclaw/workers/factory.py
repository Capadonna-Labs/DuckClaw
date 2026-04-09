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
from typing import Any, Optional

from duckclaw.db_write_queue import enqueue_duckdb_write_sync, poll_task_status_sync

try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore[misc, assignment]

from duckclaw.integrations.telegram import effective_telegram_bot_token_outbound
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
    # Gasto / presupuesto / efectivo local (DuckDB): no requiere verbos tipo "actualizar".
    if re.search(r"\b(registra|registrar)\b", t) and "gasto" in t:
        return True
    if re.search(r"\b(resta|restar|restás|reste|disminuye|disminuir|rebaja|rebajar)\b", t) and (
        "presupuesto" in t or "efectivo" in t or "categor" in t
    ):
        return True
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


def _finanz_local_mutation_anchor_message(incoming: str) -> str:
    """
    Directiva reinyectada en cada paso del agente cuando hay intención de mutación local,
    para evitar que el modelo sustituya montos/descripciones/cuenta por ejemplos del historial o del pre-entrenamiento.
    """
    raw = (incoming or "").strip()
    if not raw:
        return ""
    body = raw[:900]
    return (
        "[FINANZ_LOCAL_MUTATION_ANCHOR] La tarea activa debe cumplirse con los datos del usuario de abajo; "
        "cada INSERT/UPDATE debe ser coherente con ese texto.\n"
        "- Monto: usa solo el importe que indique el usuario (p. ej. «6k» → 6000 en COP si no dice otra moneda). "
        "Prohibido usar otros montos de memoria o ejemplos (p. ej. 50000, 20000).\n"
        "- Descripción: refleja el concepto que dio el usuario (p. ej. «weed»), no inventes otro gasto («internet», «servicios») "
        "si no aparece en su mensaje.\n"
        "- Si nombra **efectivo** / «cuenta de efectivo», el ajuste de saldo es sobre la fila de `finance_worker.cuentas` "
        "cuyo `name` coincide con Efectivo (`ILIKE '%Efectivo%'`), no Bancolombia u otro banco salvo que el usuario lo haya dicho.\n"
        "- «Presupuesto de recreación» / recreación: categoría **Recreacion** (obtén `category_id` con **una** llamada a "
        "`list_categories` o con `read_sql`/`admin_sql`); no Internet/Spotify u otra si el usuario no la mencionó.\n"
        "- **No repitas** `list_categories` si ya recibiste la lista o el id en este hilo; el siguiente paso es "
        "`insert_transaction` y luego los `UPDATE` de cuenta/presupuesto.\n"
        "- Presupuesto mensual: año y mes **actuales** (EXTRACT(YEAR|MONTH FROM CURRENT_DATE)) salvo que el usuario fije otra fecha explícitamente.\n"
        "Texto del usuario:\n"
        f"{body}"
    )


def _insert_system_after_leading_systems(messages: list[Any], system_extra: Any) -> list[Any]:
    """Inserta un SystemMessage tras el bloque inicial de SystemMessage(s), antes de Human/AI/Tool (contrato tool-use)."""
    from langchain_core.messages import SystemMessage

    if system_extra is None:
        return list(messages)
    if not messages:
        return [system_extra]
    i = 0
    while i < len(messages) and isinstance(messages[i], SystemMessage):
        i += 1
    return list(messages[:i]) + [system_extra] + list(messages[i:])


def _finanz_parse_local_expense_intent(text: str) -> Optional[dict[str, Any]]:
    """
    Extrae monto COP (p. ej. 6k → 6000) y pistas de descripción / recreación desde el mensaje del usuario.
    Solo para overrides determinísticos cuando el LLM repite plantillas (50k internet).
    """
    if not text or not str(text).strip():
        return None
    raw = str(text).strip()
    tl = raw.lower()
    if not _is_finanz_local_account_write_query(raw):
        return None
    amount_cop: Optional[int] = None
    mk = re.search(r"\b(\d+)\s*k\b", tl, re.IGNORECASE)
    if mk:
        amount_cop = int(mk.group(1)) * 1000
    if amount_cop is None:
        mc = re.search(r"\b(\d[\d\.,]*)\s*(?:cop|pesos?)\b", tl, re.IGNORECASE)
        if mc:
            raw_num = mc.group(1).replace(".", "").replace(",", "")
            if raw_num.isdigit():
                amount_cop = int(raw_num)
    if amount_cop is None:
        mdn = re.search(r"\bgast[oa]\s+de\s+(\d[\d\.,]*)\b", tl, re.IGNORECASE)
        if mdn:
            raw_num = mdn.group(1).replace(".", "").replace(",", "")
            if raw_num.isdigit():
                amount_cop = int(raw_num)
    if amount_cop is None:
        return None
    desc: Optional[str] = None
    md = re.search(
        r"\ben\s+([a-záéíóúñ0-9][a-záéíóúñ0-9\s]{1,80}?)(?:[.,;]|$)",
        tl,
        re.IGNORECASE,
    )
    if md:
        desc = re.sub(r"\s+", " ", md.group(1)).strip()
        for cut in (" y de la ", " y del ", " y ", " del presupuesto", " de la cuenta", " del saldo"):
            if cut in desc:
                desc = desc.split(cut, 1)[0].strip()
        desc = desc[:120]
    recreation = ("recreación" in raw.lower()) or ("recreacion" in tl) or ("recreaci" in tl)
    return {
        "amount_cop": amount_cop,
        "description": desc,
        "recreation_budget": recreation,
    }


def _finanz_resolve_recreation_category_id(db: Any, schema: str) -> Optional[int]:
    """Id numérico de la categoría cuyo nombre contiene 'recreac' (p. ej. Recreacion)."""
    try:
        q = (
            f"SELECT id FROM {schema}.categories WHERE lower(name) ILIKE '%recreac%' "
            "ORDER BY id LIMIT 1"
        )
        r = db.query(q)
        rows = json.loads(r) if isinstance(r, str) else (r or [])
        if rows and isinstance(rows[0], dict) and rows[0].get("id") is not None:
            return int(rows[0]["id"])
    except Exception:
        return None
    return None


def _finanz_patch_admin_sql_for_user_expense(
    sql: str,
    *,
    amount: int,
    recreation_category_id: Optional[int],
    recreation_budget: bool,
) -> str:
    """Corrige montos/categoría/fecha típicos alucinados en UPDATE locales."""
    s = sql or ""
    if not s.strip():
        return s
    low = s.lower()
    # Montos: sustituir 50000 (plantilla frecuente) por el monto del usuario
    if amount and "50000" in s:
        s = re.sub(r"\b50000\b", str(int(amount)), s)
    if recreation_budget and "presupuestos" in low:
        # Si el UPDATE no encuentra fila del mes, ON CONFLICT garantiza aplicar el descuento igual.
        if "update finance_worker.presupuestos" in low:
            # region agent log
            try:
                _payload = {
                    "sessionId": "c964f7",
                    "hypothesisId": "H-BUDGET-UPSERT",
                    "location": "factory.py:_finanz_patch_admin_sql_for_user_expense",
                    "message": "rewrite_update_presupuesto_to_upsert",
                    "data": {"amount_cop": int(amount), "recreation_category_id": recreation_category_id},
                    "timestamp": int(time.time() * 1000),
                }
                with open(
                    "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
                    "a",
                    encoding="utf-8",
                ) as _df:
                    _df.write(json.dumps(_payload, ensure_ascii=False) + "\n")
            except Exception:
                pass
            # endregion
            _cat_expr = (
                str(int(recreation_category_id))
                if recreation_category_id is not None
                else "(SELECT id FROM finance_worker.categories WHERE lower(name) ILIKE '%recreac%' ORDER BY id LIMIT 1)"
            )
            return (
                "INSERT INTO finance_worker.presupuestos (category_id, amount, year, month)\n"
                f"VALUES ({_cat_expr}, {-int(amount)}, "
                "CAST(strftime('%Y', CURRENT_DATE) AS INTEGER), CAST(strftime('%m', CURRENT_DATE) AS INTEGER))\n"
                "ON CONFLICT(category_id, year, month)\n"
                f"DO UPDATE SET amount = finance_worker.presupuestos.amount - {int(amount)}"
            )
        if recreation_category_id is not None:
            s = re.sub(
                r"category_id\s*=\s*8\b",
                f"category_id = {int(recreation_category_id)}",
                s,
                flags=re.IGNORECASE,
            )
        s = re.sub(
            r"year\s*=\s*\d+\s+AND\s+month\s*=\s*\d+",
            "year = CAST(strftime('%Y', CURRENT_DATE) AS INTEGER) "
            "AND month = CAST(strftime('%m', CURRENT_DATE) AS INTEGER)",
            s,
            flags=re.IGNORECASE,
        )
    return s


def _finanz_override_local_expense_tool_args(
    *,
    tool_name: str,
    args: dict[str, Any],
    incoming: str,
    db: Any,
    schema: str,
) -> dict[str, Any]:
    """Aplica montos/descripción/categoría del mensaje del usuario a insert_transaction / admin_sql."""
    parsed = _finanz_parse_local_expense_intent(incoming)
    if not parsed:
        return args
    amt = int(parsed["amount_cop"])
    neg = -abs(amt)
    rec_id = _finanz_resolve_recreation_category_id(db, schema) if parsed.get("recreation_budget") else None
    out = dict(args)
    # region agent log
    _did = False
    # endregion
    if tool_name == "insert_transaction":
        out["amount"] = float(neg)
        if parsed.get("description"):
            out["description"] = str(parsed["description"])[:500]
        if rec_id is not None:
            out["category_id"] = int(rec_id)
        _did = True
    elif tool_name == "admin_sql":
        q = str(out.get("query") or "")
        if q.strip():
            new_q = _finanz_patch_admin_sql_for_user_expense(
                q,
                amount=amt,
                recreation_category_id=rec_id,
                recreation_budget=bool(parsed.get("recreation_budget")),
            )
            if new_q != q:
                out["query"] = new_q
                _did = True
    # region agent log
    if _did:
        try:
            _payload = {
                "sessionId": "c964f7",
                "hypothesisId": "H-FINANZ-COP-OVERRIDE",
                "location": "factory.py:_finanz_override_local_expense_tool_args",
                "message": "applied_user_intent_override",
                "data": {
                    "tool": tool_name,
                    "amount_cop": amt,
                    "recreation_category_id": rec_id,
                    "description": (parsed.get("description") or "")[:80],
                },
                "timestamp": int(time.time() * 1000),
            }
            with open(
                "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
                "a",
                encoding="utf-8",
            ) as _df:
                _df.write(json.dumps(_payload, ensure_ascii=False) + "\n")
        except Exception:
            pass
    # endregion
    return out


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


def _finanz_user_requests_ohlcv_ingest(text: str) -> bool:
    """
    True si el usuario pide traer/descargar velas OHLCV (evita que el LLM invente tool calls).
    Requiere palabra clave de mercado + símbolo tipo ticker (1–5 letras mayúsculas).
    """
    if not text or not text.strip():
        return False
    raw = text.strip()
    low = raw.lower()
    if "quant_core.ohlcv" in low and any(
        k in low for k in ("trae", "descarga", "importa", "ingesta", "actualiza", "bajar", "pull")
    ):
        return True
    if not any(
        k in low
        for k in (
            "vela",
            "ohlcv",
            "candle",
            "fetch_market",
            "fetch market",
            "ingesta",
        )
    ):
        return False
    return bool(re.search(r"\b[A-Z]{1,5}\b", raw))


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


def _deepseek_max_estimated_input_tokens() -> int:
    """Tope estimado (chars/4) hacia DeepSeek; evita payloads enormes + tools (MCP Reddit)."""
    raw = (os.environ.get("DUCKCLAW_DEEPSEEK_MAX_INPUT_TOKENS") or "").strip()
    if raw:
        try:
            return max(4000, min(int(raw), 120_000))
        except ValueError:
            pass
    return 10000


def _deepseek_tool_message_max_chars() -> int:
    raw = (os.environ.get("DUCKCLAW_DEEPSEEK_TOOL_MESSAGE_MAX_CHARS") or "").strip()
    if raw:
        try:
            return max(400, min(int(raw), 200_000))
        except ValueError:
            pass
    return 8000


def _apply_deepseek_message_budget(messages: list[Any], *, provider: str) -> list[Any]:
    if (provider or "").strip().lower() != "deepseek" or not messages:
        return messages
    return _trim_messages_to_estimated_cap(
        messages,
        cap=_deepseek_max_estimated_input_tokens(),
        tool_cap=_deepseek_tool_message_max_chars(),
        note_brand="DEEPSEEK",
    )


def _apply_provider_input_budget(messages: list[Any], *, provider: str) -> list[Any]:
    """Recorte de contexto por proveedor (Groq TPM / MLX VRAM / DeepSeek payloads)."""
    pl = (provider or "").strip().lower()
    m = messages
    if pl == "groq":
        m = _apply_groq_message_budget(m, provider=provider)
    elif pl == "deepseek":
        m = _apply_deepseek_message_budget(m, provider=provider)
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
    El JSON de run_sandbox incluye figure_base64 / figures_base64 (grandes) y sandbox_document_paths
    (rutas largas del host). Para el LLM se omiten/sustituyen; las imágenes viven en
    state['sandbox_photo_base64'] y state['sandbox_photos_base64']; las rutas en state['sandbox_document_paths'].
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
        data.pop("figure_base64", None)
    if data.get("figures_base64"):
        data.pop("figures_base64", None)
    doc_paths = data.get("sandbox_document_paths")
    if isinstance(doc_paths, list) and doc_paths:
        data.pop("sandbox_document_paths", None)
        from pathlib import Path as _Path

        names = []
        for x in doc_paths:
            if isinstance(x, str) and str(x).strip():
                names.append(_Path(str(x).strip()).name)
        if names:
            data["sandbox_document_names"] = names
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
            if name in ("run_sandbox", "run_browser_sandbox"):
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
    Helper (unit-testable): si sandbox está OFF, elimina `run_sandbox` y `run_browser_sandbox`.
    """
    if enabled:
        return list(tools)
    deny = {"run_sandbox", "run_browser_sandbox"}
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
    if getattr(spec, "github_config", None):
        try:
            from duckclaw.forge.skills.github_bridge import register_github_skill
            register_github_skill(tools, spec.github_config)
        except Exception:
            pass
    if getattr(spec, "reddit_config", None):
        try:
            from duckclaw.forge.skills.reddit_bridge import register_reddit_skill

            register_reddit_skill(tools, spec.reddit_config)
        except Exception:
            pass
    if getattr(spec, "google_trends_config", None) is not None:
        try:
            from duckclaw.forge.skills.google_trends_bridge import register_google_trends_skill

            register_google_trends_skill(tools, spec.google_trends_config)
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

    # Si el turno debe usar MLX/IoT local (triplet o env fusionado) pero el objeto LLM heredado apunta
    # a un host remoto (p. ej. Groq vía _graph_state), reconstruir desde provider/model/base_url; si no,
    # el worker invoca Groq con model=/ruta/local y aparece el error HF «Repo id must be…».
    if llm is not None and provider in ("mlx", "iotcorelabs"):
        from duckclaw.integrations.llm_providers import infer_provider_from_openai_compatible_llm

        _inf_host = (infer_provider_from_openai_compatible_llm(llm) or "").strip().lower()
        if _inf_host and _inf_host not in ("mlx", "iotcorelabs"):
            _log.warning(
                "build_worker_graph: cliente LLM inferido=%s no coincide con triplet local declarado; "
                "reconstruyendo desde provider=%s model=%s…",
                _inf_host,
                provider,
                (model or "")[:48],
            )
            # region agent log
            try:
                _payload = {
                    "sessionId": "c964f7",
                    "hypothesisId": "H1",
                    "location": "workers/factory.py:build_worker_graph",
                    "message": "mlx declared but remote LLM client; rebuilding from triplet",
                    "data": {
                        "worker_id": worker_id,
                        "inferred_client": _inf_host,
                        "merged_provider": provider,
                    },
                    "timestamp": int(time.time() * 1000),
                }
                with open(
                    "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
                    "a",
                    encoding="utf-8",
                ) as _df:
                    _df.write(json.dumps(_payload, ensure_ascii=False) + "\n")
            except Exception:
                pass
            # endregion
            llm = None

    if llm is None and provider != "none_llm":
        from duckclaw.integrations.llm_providers import build_llm

        # Ya fusionamos llm_provider/model/base_url con env arriba; prefer_env_provider=False
        # evita que build_llm vuelva a imponer DUCKCLAW_LLM_* y anule /model (mlx en chat vs groq en PM2).
        llm = build_llm(provider, model, base_url, prefer_env_provider=False)
    elif llm is None:
        llm = None

    if llm is not None:
        from duckclaw.integrations.llm_providers import reconcile_worker_provider_label

        provider = reconcile_worker_provider_label(llm, provider, llm_provider)

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
    if isinstance(_qcfg, dict) and _qcfg.get("enabled") and _lid_q in ("quant_trader", "quanttrader"):
        try:
            from duckclaw.forge.skills.quant_trader_bridge import register_quant_trader_skills

            register_quant_trader_skills(db, llm, tools)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            _log.debug("quant trader skills registration skipped", exc_info=True)

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
            from duckclaw.graphs.sandbox import browser_sandbox_tool_factory, sandbox_tool_factory

            if getattr(spec, "browser_sandbox", False) and "run_browser_sandbox" not in tools_by_name:
                tools.append(browser_sandbox_tool_factory(db, llm))
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

    # Groq (TPM) y DeepSeek (runtime: petición masiva con MCP Reddit → 400 spurious "Model Not Exist"):
    # en rutas genéricas se omite reddit_*; rutas forzadas Reddit siguen con `tools` completos.
    _slim_reddit_for_bind = (provider or "").strip().lower() in ("groq", "deepseek")
    _tools_for_llm_bind = _groq_tools_without_reddit_for_bind(tools) if _slim_reddit_for_bind else tools
    _tools_sandbox_off_bind = (
        _groq_tools_without_reddit_for_bind(tools_sandbox_off) if _slim_reddit_for_bind else tools_sandbox_off
    )
    if _slim_reddit_for_bind:
        _log.info(
            "%s: bind genérico sin reddit_* (%d tools; forzados Reddit/otros usan set acorde).",
            (provider or "").strip().lower() or "llm",
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
        # Groq (~12k TPM) y DeepSeek: rutas genéricas sin reddit_* (ver _slim_reddit_for_bind); Reddit forzado usa `tools` completo.
        llm_with_tools_on = _bind_tools(llm, _tools_for_llm_bind)
        llm_with_tools_off = _bind_tools(llm, _tools_sandbox_off_bind)
        # Finanz: mutaciones locales (gasto/presupuesto) — bind sin IBKR ni ingesta mercado (evita bucle read_sql↔get_ibkr_portfolio y llamadas espurias a fetch_market_data/CFD).
        _FINANZ_LOCAL_MUT_EXCLUDE = frozenset({"get_ibkr_portfolio", "fetch_market_data", "fetch_lake_ohlcv"})
        _finanz_local_mut_bind_on = [
            t for t in _tools_for_llm_bind if getattr(t, "name", None) not in _FINANZ_LOCAL_MUT_EXCLUDE
        ]
        _finanz_local_mut_bind_off = [
            t for t in _tools_sandbox_off_bind if getattr(t, "name", None) not in _FINANZ_LOCAL_MUT_EXCLUDE
        ]
        if (_lid or "").strip().lower() == "finanz":
            llm_with_tools_on_nibkr = _bind_tools(llm, _finanz_local_mut_bind_on)
            llm_with_tools_off_nibkr = _bind_tools(llm, _finanz_local_mut_bind_off)
        else:
            llm_with_tools_on_nibkr = None
            llm_with_tools_off_nibkr = None

        has_ibkr = "get_ibkr_portfolio" in tools_by_name
        has_read_sql = "read_sql" in tools_by_name
        has_admin_sql = "admin_sql" in tools_by_name
        has_run_sandbox = "run_sandbox" in tools_by_name
        tool_choice_inspect_schema = {"type": "function", "function": {"name": "inspect_schema"}}
        tool_choice_read_sql = {"type": "function", "function": {"name": "read_sql"}}
        tool_choice_admin_sql = {"type": "function", "function": {"name": "admin_sql"}}
        tool_choice_portfolio = {"type": "function", "function": {"name": "get_ibkr_portfolio"}}
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
            Enlaces /r/<sub>/s/<slug> no son post_id de la API de Reddit: reddit_get_post devuelve 404.
            Sustituye get_post por reddit_search_reddit(query=url) y fija query en búsquedas.
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
            if re.search(
                r"\b(que\s+hay\s+en\s+la\s+tabla|qué\s+hay\s+en\s+la\s+tabla|contenido\s+de\s+la\s+tabla|"
                r"muestr(a|ame)\s+la\s+tabla|ver\s+datos\s+de\s+la\s+tabla|registros?\s+de\s+la\s+tabla|"
                r"filas?\s+de\s+la\s+tabla|select\s+\*\s+from)\b",
                t,
            ):
                return False
            return any(k in t for k in ("tablas", "tabla", "duckdb", "esquema", "schema", "estructura", "qué tablas", "que tablas"))

        def _is_table_content_query(text: str) -> bool:
            if not text or not text.strip():
                return False
            t = text.strip().lower()
            if "read_sql" in t and "job_opportunities" in t:
                return True
            return bool(
                re.search(
                    r"\b(que\s+hay\s+en\s+la\s+tabla|qué\s+hay\s+en\s+la\s+tabla|contenido\s+de\s+la\s+tabla|"
                    r"muestr(a|ame)\s+la\s+tabla|ver\s+datos\s+de\s+la\s+tabla|registros?\s+de\s+la\s+tabla|"
                    r"filas?\s+de\s+la\s+tabla|select\s+\*\s+from|select\s+.+\s+from)\b",
                    t,
                )
            )

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
            is_schema = _is_schema_query(incoming)
            is_table_content = _is_table_content_query(incoming)
            is_latest_game = _is_latest_game_query(incoming)
            is_portfolio = has_ibkr and _is_portfolio_query(incoming)
            force_finanz_cuentas = (
                (_lid or "").strip().lower() == "finanz"
                and has_read_sql
                and _is_finanz_local_accounts_query(incoming)
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
                force_finanz_admin_sql = False
            # No forzar herramienta si el último mensaje ya es ToolMessage (ya ejecutamos la tool):
            # así el LLM puede responder con texto y no entrar en bucle (inspect_schema -> agent -> inspect_schema).
            last_msg = (state.get("messages") or [])[-1] if state.get("messages") else None
            already_has_tool_result = last_msg is not None and isinstance(last_msg, ToolMessage)

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
                is_table_content or is_latest_game or force_finanz_cuentas
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
            force_reddit = bool(
                _lid == "finanz"
                and has_reddit_tools
                and _reddit_anchor_u is not None
                and not summarize_stored_directive
                and not (force_schema or force_admin_sql or force_read_sql or force_portfolio or force_tavily)
                and (not already_has_tool_result or need_share_followup)
            )

            if not _worker_use_heuristic_first_tool(spec):
                force_schema = False
                force_admin_sql = False
                force_read_sql = False
                force_portfolio = False
                force_tavily = False
                force_reddit = False

            force_fetch_market_data = bool(
                (_lid or "").strip().lower() == "finanz"
                and has_fetch_market
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
                force_fetch_market_data = False
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
                )
                and not already_has_tool_result
            )
            if not _worker_use_heuristic_first_tool(spec):
                force_plot_docs = False
                force_run_sandbox = False
            if force_plot_docs:
                force_tavily = True

            if jh_fast_text is not None:
                resp = AIMessage(content=jh_fast_text)
                out = {**state, "messages": state["messages"] + [resp]}
                out.update(_identity_fields(state))
                return out

            sandbox_enabled = _sandbox_enabled_for_state(state)
            _finanz_hide_ibkr_bind = bool(
                (_lid or "").strip().lower() == "finanz"
                and llm_with_tools_on_nibkr is not None
                and not telegram_context_summarize_directive
                and _is_finanz_local_account_write_query(incoming)
                and "[SYSTEM_DIRECTIVE:" not in (incoming or "")
                and not is_portfolio
            )
            llm_with_tools = (
                (llm_with_tools_on_nibkr if sandbox_enabled else llm_with_tools_off_nibkr)
                if _finanz_hide_ibkr_bind
                else (llm_with_tools_on if sandbox_enabled else llm_with_tools_off)
            )
            # region agent log
            try:
                if str(_lid or "").strip().lower() == "finanz":
                    _payload = {
                        "sessionId": "c964f7",
                        "hypothesisId": "H-LOOP",
                        "location": "factory.py:agent_node:hide_ibkr_bind",
                        "message": "finanz_local_mut_bind_choice",
                        "data": {
                            "hide_ibkr_bind": _finanz_hide_ibkr_bind,
                            "incoming_snip": (incoming or "")[:120],
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                    with open(
                        "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
                        "a",
                        encoding="utf-8",
                    ) as _df:
                        _df.write(json.dumps(_payload, ensure_ascii=False) + "\n")
            except Exception:
                pass
            # endregion
            forced_name = (
                "admin_sql"
                if force_admin_sql
                else (
                    "inspect_schema"
                    if force_schema
                    else (
                        "read_sql"
                        if force_read_sql
                        else (
                            "get_ibkr_portfolio"
                            if force_portfolio
                            else (
                                "tavily_search"
                                if force_tavily
                                else (
                                    "reddit"
                                    if force_reddit
                                    else (
                                        "fetch_market_data"
                                        if force_fetch_market_data
                                        else ("run_sandbox" if force_run_sandbox else "auto")
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
            if (
                (str(_lid or "").strip().lower() == "finanz")
                and not telegram_context_summarize_directive
                and _is_finanz_local_account_write_query(incoming)
            ):
                _anchor_txt = _finanz_local_mutation_anchor_message(incoming)
                if _anchor_txt:
                    _before_n = len(_msg_list)
                    _msg_list = _insert_system_after_leading_systems(
                        _msg_list, SystemMessage(content=_anchor_txt)
                    )
                    # region agent log
                    try:
                        _tail_types = [
                            type(_msg_list[i]).__name__
                            for i in range(max(0, len(_msg_list) - 4), len(_msg_list))
                        ]
                        _payload = {
                            "sessionId": "c964f7",
                            "hypothesisId": "H-ANCHOR",
                            "location": "factory.py:agent_node:local_mutation_anchor",
                            "message": "finanz_anchor_after_leading_systems",
                            "data": {
                                "incoming_snip": (incoming or "")[:160],
                                "msg_count_before": _before_n,
                                "msg_count_after": len(_msg_list),
                                "tail_message_types": _tail_types,
                            },
                            "timestamp": int(time.time() * 1000),
                        }
                        with open(
                            "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
                            "a",
                            encoding="utf-8",
                        ) as _df:
                            _df.write(json.dumps(_payload, ensure_ascii=False) + "\n")
                    except Exception:
                        pass
                    # endregion
            _groq_msgs = _apply_provider_input_budget(_msg_list, provider=provider)
            _invoked_llm: Any = llm_with_tools
            if force_admin_sql:
                _fa = llm_force_admin_sql_on if sandbox_enabled else llm_force_admin_sql_off
                _invoked_llm = _fa or llm_with_tools
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
            elif force_tavily:
                _ft = llm_force_tavily_on if sandbox_enabled else llm_force_tavily_off
                _invoked_llm = _ft or llm_with_tools
            elif force_reddit:
                _fr = None
                if _incoming_has_reddit_share_path(incoming_for_reddit):
                    _fr = llm_force_reddit_search_on if sandbox_enabled else llm_force_reddit_search_off
                elif _incoming_looks_like_reddit_post_url(incoming_for_reddit):
                    _fr = llm_force_reddit_post_on if sandbox_enabled else llm_force_reddit_post_off
                if _fr is None:
                    _fr = llm_force_reddit_search_on if sandbox_enabled else llm_force_reddit_search_off
                if _fr is None:
                    _fr = llm_force_reddit_fallback_on if sandbox_enabled else llm_force_reddit_fallback_off
                _invoked_llm = _fr or llm_with_tools
            elif force_fetch_market_data:
                _ffmd = llm_force_fetch_market_on if sandbox_enabled else llm_force_fetch_market_off
                _invoked_llm = _ffmd or llm_with_tools
            elif force_run_sandbox:
                _frs = llm_force_run_sandbox_on if sandbox_enabled else llm_force_run_sandbox_off
                _invoked_llm = _frs or llm_with_tools
            # region agent log
            try:
                if (str(_lid or "").strip().lower() == "finanz"):
                    from duckclaw.integrations.llm_providers import infer_provider_from_openai_compatible_llm as _inf_dbg

                    def _unwrap_openai_compat(co: Any) -> tuple[str, str]:
                        z: Any = co
                        for _ in range(12):
                            if z is None:
                                return "", ""
                            mo = str(getattr(z, "model_name", None) or getattr(z, "model", "") or "")[:120]
                            ba = getattr(z, "openai_api_base", None) or getattr(z, "base_url", None)
                            if ba is None:
                                cl = getattr(z, "client", None) or getattr(z, "root_client", None)
                                ba = getattr(cl, "base_url", None) if cl else None
                            if mo.strip() or (ba is not None and str(ba).strip()):
                                return mo.strip(), str(ba).strip()[:200]
                            z = getattr(z, "bound", None)
                        return "", ""

                    _m0, _b0 = _unwrap_openai_compat(llm)
                    _m1, _b1 = _unwrap_openai_compat(_invoked_llm)
                    _payload = {
                        "sessionId": "c964f7",
                        "hypothesisId": "H-B",
                        "location": "factory.py:agent_node:pre_invoke",
                        "message": "finanz_llm_unwrap",
                        "data": {
                            "merged_provider": str(provider or ""),
                            "merged_model": str(model or "")[:120],
                            "merged_base": str(base_url or "")[:160],
                            "infer_llm": str(_inf_dbg(llm) or ""),
                            "infer_invoked": str(_inf_dbg(_invoked_llm) or ""),
                            "unwrap_llm_model": _m0,
                            "unwrap_llm_base": _b0,
                            "unwrap_inv_model": _m1,
                            "unwrap_inv_base": _b1,
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                    with open(
                        "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
                        "a",
                        encoding="utf-8",
                    ) as _df:
                        _df.write(json.dumps(_payload, ensure_ascii=False) + "\n")
            except Exception:
                pass
            # endregion
            try:
                if force_admin_sql:
                    resp = _invoked_llm.invoke(_groq_msgs)
                elif force_schema and not force_read_sql:
                    resp = _invoked_llm.invoke(_groq_msgs)
                elif force_read_sql:
                    resp = _invoked_llm.invoke(_groq_msgs)
                elif force_portfolio:
                    resp = _invoked_llm.invoke(_groq_msgs)
                elif force_tavily:
                    resp = _invoked_llm.invoke(_groq_msgs)
                elif force_reddit:
                    resp = _invoked_llm.invoke(_groq_msgs)
                elif force_fetch_market_data:
                    resp = _invoked_llm.invoke(_groq_msgs)
                elif force_run_sandbox:
                    resp = _invoked_llm.invoke(_groq_msgs)
                else:
                    resp = _invoked_llm.invoke(_groq_msgs)
                if (
                    (_lid or "").strip().lower() == "finanz"
                    and resp is not None
                    and getattr(resp, "tool_calls", None)
                ):
                    _ru_share = _first_reddit_url_in_text(incoming_for_reddit)
                    if _ru_share and _incoming_has_reddit_share_path(_ru_share):
                        resp = _patch_ai_reddit_share_tool_calls(resp, _ru_share)
            except Exception as exc:
                _log.warning("[%s] LLM invoke failed in agent_node: %s", _wl, exc, exc_info=True)
                from duckclaw.integrations.llm_providers import failure_provider_label_for_llm_invoke

                _pl_fail = failure_provider_label_for_llm_invoke(_invoked_llm, provider)
                resp = AIMessage(content=_agent_node_llm_failure_user_message(exc, provider=_pl_fail))
            tool_calls = getattr(resp, "tool_calls", None) or []
            if tool_calls:
                _tc_names: list[Any] = []
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        _tc_names.append(tc.get("name"))
                    else:
                        _tc_names.append(getattr(tc, "name", None))
                _log.info("[%s] LLM tool_calls=%s", _wl, _tc_names)
            # region agent log
            try:
                if (str(_lid or "").strip().lower() == "finanz") and resp is not None:
                    _ak_dbg = getattr(resp, "additional_kwargs", None) or {}
                    _ak_tc_dbg = _ak_dbg.get("tool_calls") if isinstance(_ak_dbg, dict) else None
                    _rm_dbg = getattr(resp, "response_metadata", None) or {}
                    _fn_dbg = _rm_dbg.get("finish_reason") if isinstance(_rm_dbg, dict) else None
                    _prev_txt = str(getattr(resp, "content", "") or "")[:400].replace("\n", " ")
                    with open(
                        "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
                        "a",
                        encoding="utf-8",
                    ) as _df:
                        _df.write(
                            json.dumps(
                                {
                                    "sessionId": "c964f7",
                                    "hypothesisId": "H1-H5",
                                    "location": "factory.py:agent_node",
                                    "message": "finanz_after_llm_invoke",
                                    "data": {
                                        "provider": str(provider or ""),
                                        "tool_calls_len": len(tool_calls),
                                        "tool_call_names": _tc_names if tool_calls else [],
                                        "additional_kwargs_has_tool_calls": bool(_ak_tc_dbg),
                                        "finish_reason": _fn_dbg,
                                        "content_preview": _prev_txt,
                                    },
                                    "timestamp": int(time.time() * 1000),
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        )
            except Exception:
                pass
            # endregion
            out = {**state, "messages": state["messages"] + [resp]}
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
        _wl = _worker_log_label(worker_id)
        messages = state["messages"]
        last = messages[-1]
        tool_calls = getattr(last, "tool_calls", None) or []
        new_msgs = list(messages)
        sandbox_enabled = _sandbox_enabled_for_state(state)
        tool_lookup = tools_by_name if sandbox_enabled else tools_by_name_sandbox_off
        sandbox_b64: str | None = (
            state.get("sandbox_photo_base64") if isinstance(state.get("sandbox_photo_base64"), str) else None
        )
        sandbox_photos_b64: list[str] = []
        _prev_pl = state.get("sandbox_photos_base64")
        if isinstance(_prev_pl, list):
            sandbox_photos_b64 = [str(x).strip() for x in _prev_pl if isinstance(x, str) and str(x).strip()]
        sandbox_document_paths: list[str] = []
        _prev_docs = state.get("sandbox_document_paths")
        if isinstance(_prev_docs, list):
            sandbox_document_paths = [
                str(x).strip() for x in _prev_docs if isinstance(x, str) and str(x).strip()
            ]
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
                        _schedule_tool_heartbeat(name)
                        invoke_args: Any = args
                        if isinstance(args, dict):
                            invoke_args = {**args}
                        if name in ("run_sandbox", "run_browser_sandbox") and isinstance(invoke_args, dict):
                            if not str(invoke_args.get("worker_id") or "").strip():
                                invoke_args["worker_id"] = worker_id
                        if isinstance(invoke_args, dict) and (str(_lid or "").strip().lower() == "finanz"):
                            _inc_ov = (state.get("incoming") or "").strip()
                            _sch_ov = (getattr(spec, "schema_name", None) or "finance_worker").strip()
                            invoke_args = _finanz_override_local_expense_tool_args(
                                tool_name=name,
                                args=invoke_args,
                                incoming=_inc_ov,
                                db=db,
                                schema=_sch_ov,
                            )
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
                        try:
                            from duckclaw.forge.skills.quant_tool_context import (
                                set_quant_tool_chat_id,
                                set_quant_tool_db_path,
                                set_quant_tool_tenant_id,
                                set_quant_tool_user_id,
                            )

                            set_quant_tool_chat_id(str(state.get("chat_id") or state.get("session_id") or ""))
                            set_quant_tool_tenant_id(str(state.get("tenant_id") or "default"))
                            set_quant_tool_user_id(str(state.get("user_id") or state.get("chat_id") or "default"))
                            set_quant_tool_db_path(str(getattr(db, "_path", "") or ""))
                        except Exception:
                            pass
                        result = tool.invoke(invoke_args)
                        content = str(result) if result is not None else "OK"
                        if name in ("run_sandbox", "run_browser_sandbox"):
                            try:
                                payload = json.loads(content)
                                if isinstance(payload, dict) and payload.get("exit_code") == 0:
                                    figs = payload.get("figures_base64")
                                    if isinstance(figs, list):
                                        sandbox_photos_b64 = [
                                            str(x) for x in figs if isinstance(x, str) and len(str(x).strip()) > 32
                                        ]
                                    fb = payload.get("figure_base64")
                                    if sandbox_photos_b64:
                                        sandbox_b64 = sandbox_photos_b64[0]
                                    elif isinstance(fb, str) and len(fb) > 32:
                                        sandbox_b64 = fb
                                        sandbox_photos_b64 = [fb]
                                    sdp = payload.get("sandbox_document_paths")
                                    if isinstance(sdp, list):
                                        sandbox_document_paths = [
                                            str(x).strip()
                                            for x in sdp
                                            if isinstance(x, str) and str(x).strip()
                                        ]
                            except (json.JSONDecodeError, TypeError):
                                pass
                            if not use_cm:
                                content = _compact_run_sandbox_tool_content_for_llm(
                                    content, _RUN_SANDBOX_TOOL_LLM_MAX_CHARS
                                )
                        if name.startswith("reddit_"):
                            content = format_reddit_mcp_reply_if_applicable(content)
                        _log.info(
                            "[%s] tool=%s | result_len=%d | preview=%r",
                            _wl,
                            name,
                            len(content),
                            content[:120] + ("..." if len(content) > 120 else ""),
                        )
                    except Exception as e:
                        content = f"Error: {e}"
                        _log.warning("[%s] tool=%s failed: %s", _wl, name, e)
                else:
                    if not sandbox_enabled and name in ("run_sandbox", "run_browser_sandbox"):
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
        out: dict[str, Any] = {**state, "messages": new_msgs}
        if sandbox_photos_b64:
            out["sandbox_photos_base64"] = sandbox_photos_b64
        if sandbox_b64:
            out["sandbox_photo_base64"] = sandbox_b64
        if sandbox_document_paths:
            out["sandbox_document_paths"] = sandbox_document_paths
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
        from duckclaw.forge.atoms.user_reply_nl_synthesis import (
            incoming_has_context_summarize_directive,
            maybe_synthesize_reply,
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
            )

        msgs = state.get("messages") or []
        last = msgs[-1] if msgs else None
        reply = lc_message_content_to_text(last) if last else ""
        reply = sanitize_worker_reply_phase1(reply)
        if (getattr(spec, "worker_id", "") or "").strip().lower() == "finanz":
            from duckclaw.forge.skills.quant_market_bridge import (
                finanz_reconcile_cuentas_placeholder_reply,
                finanz_reconcile_reply_with_fetch_market_tool,
            )

            reply = finanz_reconcile_reply_with_fetch_market_tool(msgs, reply)
            reply = finanz_reconcile_cuentas_placeholder_reply(msgs, reply)
        reply = format_reddit_mcp_reply_if_applicable(reply)
        suppress_egress = bool(state.get("suppress_subagent_egress"))

        def _nl_user_ask() -> str:
            inc = state.get("incoming") or state.get("input") or ""
            return (inc.strip() if isinstance(inc, str) else str(inc or "")).strip()

        def _apply_nl_synthesis(candidate: str) -> str:
            return maybe_synthesize_reply(llm, spec=spec, user_ask=_nl_user_ask(), reply_candidate=candidate)

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
                _formatted = sanitize_worker_reply_text(_apply_nl_synthesis(_combined))
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
        reply = _apply_nl_synthesis(reply or "")
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
        reply = sanitize_worker_reply_text(reply or "")
        if not (reply or "").strip():
            tool_content = ""
            for _m in reversed(msgs):
                if getattr(_m, "type", "") == "tool":
                    tool_content = str(getattr(_m, "content", "") or "").strip()
                    if tool_content:
                        break
            if tool_content:
                try:
                    from duckclaw.utils import format_tool_reply

                    reply = sanitize_worker_reply_text(format_tool_reply(tool_content))
                except Exception:
                    reply = tool_content
            if not (reply or "").strip():
                reply = "No encontré resultados para responder en este turno."
        if suppress_egress:
            out = {**state, "reply": "", "internal_reply": (reply or ""), "messages": msgs}
        else:
            out = {**state, "reply": reply or "", "internal_reply": (reply or ""), "messages": msgs}
        sb = (state.get("sandbox_photo_base64") or "").strip()
        if sb:
            out["sandbox_photo_base64"] = sb
        sb_pl = state.get("sandbox_photos_base64")
        if isinstance(sb_pl, list) and sb_pl:
            out["sandbox_photos_base64"] = [str(x) for x in sb_pl if isinstance(x, str) and str(x).strip()]
        sb_docs = state.get("sandbox_document_paths")
        if isinstance(sb_docs, list) and sb_docs:
            out["sandbox_document_paths"] = [str(x).strip() for x in sb_docs if isinstance(x, str) and str(x).strip()]
        out.update(_identity_fields(state))
        return out

    def should_continue(state: dict) -> str:
        last = state["messages"][-1]
        _ptc = getattr(last, "tool_calls", None)
        _ak_sc = getattr(last, "additional_kwargs", None) or {}
        _ak_tc_sc = _ak_sc.get("tool_calls") if isinstance(_ak_sc, dict) else None
        _branch = "tools" if _ptc else "end"
        # region agent log
        try:
            if (str(_lid or "").strip().lower() == "finanz"):
                with open(
                    "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
                    "a",
                    encoding="utf-8",
                ) as _df:
                    _df.write(
                        json.dumps(
                            {
                                "sessionId": "c964f7",
                                "hypothesisId": "H2",
                                "location": "factory.py:should_continue",
                                "message": "route_after_agent",
                                "data": {
                                    "branch": _branch,
                                    "parsed_tool_calls_truthy": bool(_ptc),
                                    "additional_kwargs_tool_calls_truthy": bool(_ak_tc_sc),
                                },
                                "timestamp": int(time.time() * 1000),
                            },
                            ensure_ascii=False,
                        )
                        + "\n"
                    )
        except Exception:
            pass
        # endregion
        return _branch

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
