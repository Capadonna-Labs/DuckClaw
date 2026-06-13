"""Quant worker runtime policy and tool-call guards."""

from __future__ import annotations

import json
import re
from typing import Any

from duckclaw.egress.market_worker_tool_repair import reply_is_get_current_time_json_only as _reply_is_get_current_time_json_only
from duckclaw.finance.runtime_policy import (
    finanz_user_requests_ohlcv_ingest as _finanz_user_requests_ohlcv_ingest,
    is_finanz_local_accounts_query as _is_finanz_local_accounts_query,
)

_LONE_HTTP_URL_ONLY_LINE = re.compile(r"^\s*https?://[^\s]+\s*$", re.I)


def is_quant_trader(worker_id: str | None) -> bool:
    _ = worker_id
    return False


def duckclaw_env_truthy(name: str) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def quant_allows_reddit_anchor_force(
    logical_worker_id: str,
    incoming: str,
    reddit_anchor_url: str | None,
    *,
    is_quant_trading_worker: bool = False,
) -> bool:
    _ = logical_worker_id
    if not is_quant_trading_worker:
        return False
    if not reddit_anchor_url:
        return False
    return bool(_LONE_HTTP_URL_ONLY_LINE.match((incoming or "").strip()))

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

def _quant_ohlcv_context_summary_forced_fetch_enabled() -> bool:
    """Opt-in: forzar ingesta OHLCV en turnos SUMMARIZE_* cuando el texto pide velas explícitas."""
    return duckclaw_env_truthy("DUCKCLAW_QUANT_OHLCV_ON_CONTEXT_SUMMARY")

def _quant_summarize_allows_forced_ohlcv_fetch(
    incoming: str,
    worker_lid: str,
    *,
    is_quant_trading_worker: bool = False,
) -> bool:
    """SUMMARIZE_* no bloquea fetch_market_data si Quant + env + heurística OHLCV del usuario."""
    _ = worker_lid
    if not _quant_ohlcv_context_summary_forced_fetch_enabled():
        return False
    if not is_quant_trading_worker:
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

def _quant_user_requests_cancel_trade_signal(text: str) -> bool:
    """Usuario pide cancelar señal(es) HITL (Quant Trader)."""
    if not text or not str(text).strip():
        return False
    low = text.strip().lower()
    if "[system_directive:" in low or "[system_event:" in low:
        return False
    if "/cancel_signal" in low or "--action cancel" in low:
        return True
    if re.search(r"\b(cancela(r|ar)?|anula(r|ar)?)\b", low) and re.search(
        r"\b(se[nñ]al|se[nñ]ales|signal)\b", low
    ):
        return True
    if re.search(r"\bpuedes?\s+cancelar\b", low) and re.search(
        r"\b(se[nñ]al|se[nñ]ales)\b", low
    ):
        return True
    return False

def _quant_extract_cancel_signal_ref(text: str) -> str:
    """UUID completo o prefijo hex (≥4) para cancel_trade_signal."""
    full = _quant_extract_signal_id(text)
    if full:
        return full
    raw = str(text or "")
    for pat in (
        r"[`'\"]([0-9a-f]{4,32})[`'\"]",
        r"\b([0-9a-f]{8,32})\b",
        r"\b([0-9a-f]{4,7})\b",
    ):
        m = re.search(pat, raw, flags=re.IGNORECASE)
        if m:
            return str(m.group(1)).lower()
    return ""

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
    return bool(re.search(r"\b(procede|continu(a|ar|úa)|sigue|adelante|hazlo|vamos|dale)\b", low))

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

def _quant_tool_called_recently(
    messages: list[Any],
    tool_name: str,
    *,
    max_messages: int = 32,
) -> bool:
    """True si la herramienta apareció en los últimos mensajes del hilo (evita bucles IBKR)."""
    from langchain_core.messages import ToolMessage

    tail = list(messages or [])[-max(1, max_messages) :]
    for m in tail:
        if isinstance(m, ToolMessage) and str(getattr(m, "name", "") or "") == tool_name:
            return True
    return False

def _quant_strip_duplicate_ibkr_portfolio_tool_calls(
    messages: list[Any],
    tool_calls: list[Any],
    *,
    last_human_idx: int,
) -> list[Any]:
    """Quita get_ibkr_portfolio repetido en el mismo turno tras un snapshot exitoso."""
    if not tool_calls:
        return tool_calls
    already_in_turn = _quant_tool_called_since(
        messages or [], last_human_idx, "get_ibkr_portfolio"
    )
    filtered: list[Any] = []
    seen_pf_in_batch = False
    for tc in tool_calls:
        name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
        if str(name or "") != "get_ibkr_portfolio":
            filtered.append(tc)
            continue
        if already_in_turn or seen_pf_in_batch:
            continue
        seen_pf_in_batch = True
        filtered.append(tc)
    return filtered

def _incoming_has_vlm_context(text: str) -> bool:
    low = (text or "").lower()
    return "[vlm_context" in low or "contexto visual adjunto:" in low

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



def _quant_retry_or_probe_needs_ibkr_portfolio(messages: list, text: str) -> bool:
    from langchain_core.messages import AIMessage

    t = (text or "").strip().lower()
    if not t or len(t) > 180:
        return False
    probe_kw = ("cuenta paper", "validar conexión", "validar conexion", "probar conexión", "probar conexion", "conexion ibkr", "conexión ibkr", "conectar con ibkr", "servicio de portfolio", "snapshot ibkr", "validación de conexión", "validacion de conexion")
    if any(k in t for k in probe_kw):
        return True
    if not re.search(r"\b(reintent|vuelv\w*|intent\w*|de\s+nuevo|otra\s+vez|try\s+again)\b", t):
        return False
    for m in reversed((messages or [])[-12:]):
        if not isinstance(m, AIMessage):
            continue
        c = (str(m.content) or "").lower()
        if len(c) < 40:
            continue
        if any(x in c for x in ("ibkr", "interactive brokers", "portfolio", "portafolio", "cuenta paper", "validación de conexión", "validacion de conexion", "servicio de portfolio", "conexión", "conexion", "paper", "gateway")):
            return True
    return False


def _quant_execution_bug_probe_needs_ibkr_portfolio(text: str) -> bool:
    t = (text or "").strip().lower()
    if not t:
        return False
    if _quant_user_requests_cancel_trade_signal(text):
        return False
    has_bug_probe = any(k in t for k in ("bug", "falla", "falla", "error", "verifica", "revisa"))
    has_execution_context = any(k in t for k in ("ejec", "señal", "senal", "order id", "ib order", "broker", "paper"))
    return has_bug_probe and has_execution_context

_REDDIT_SHARE_PATH_RE = re.compile(r"reddit\.com/r/[\w_]+/s/[a-zA-Z0-9]+", re.IGNORECASE)

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

