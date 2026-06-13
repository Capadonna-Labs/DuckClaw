"""Finance worker runtime policy."""

from __future__ import annotations

import re
from typing import Any

FINANZ_LOCAL_ACCOUNT_NAMES = (
    "bancolombia", "nequi", "davivienda", "efectivo", "global 66", "global66",
    "scotiabank", "cívica", "civica", "tarjeta cívica", "tarjeta civica", "nu",
)


def is_finanz(worker_id: str | None) -> bool:
    _ = worker_id
    return False


def is_finanz_local_account_write_query(text: str) -> bool:
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
    if any(name in t for name in FINANZ_LOCAL_ACCOUNT_NAMES) and (
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

def finanz_hallucinated_balance_write_reply(incoming: str, content: str) -> bool:
    """True si el modelo afirmó actualizar saldo sin evidencia de admin_sql en el turno."""
    if not is_finanz_local_account_write_query(incoming):
        return False
    body = (content or "").strip().lower()
    if not body:
        return False
    markers = ("✅", "actualizad", "actualizado", "quedó en", "quedo en", "nuevo saldo")
    return any(m in body for m in markers)

def is_finanz_local_accounts_query(text: str) -> bool:
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

def finanz_should_force_current_time(text: str) -> bool:
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
    if is_finanz_debts_query(raw):
        return True
    if is_finanz_local_accounts_query(raw):
        return True
    if is_finanz_budgets_query(raw):
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

def is_finanz_debts_query(text: str) -> bool:
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

def is_finanz_validate_db_intent(text: str) -> bool:
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

def is_finanz_budgets_query(text: str) -> bool:
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

def finanz_user_requests_ohlcv_ingest(text: str) -> bool:
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

def finanz_should_force_ibkr_after_local_cuentas_read(
    messages: list[Any] | None,
    *,
    logical_worker_id: str,
    has_ibkr: bool,
    is_finance_ledger_worker: bool = False,
) -> bool:
    """
    Tras un ToolMessage de read_sql, forzar get_ibkr_portfolio si el último HumanMessage
    fue un resumen general de cuentas locales y aún no hubo get_ibkr_portfolio en ese turno.
    """
    from langchain_core.messages import HumanMessage, ToolMessage

    _ = logical_worker_id
    if not has_ibkr or not is_finance_ledger_worker:
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
    if not is_finanz_local_accounts_query(human_text):
        return False
    for m in msgs[last_human_idx + 1 :]:
        if isinstance(m, ToolMessage) and (m.name or "") == "get_ibkr_portfolio":
            return False
    return True

def finanz_followup_reddit_read_intent(text: str) -> bool:
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
