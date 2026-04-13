"""LLM provider factory and DuckClaw tools for agents."""

from __future__ import annotations

import inspect
import logging
import os
import re
import time
from typing import Any, Optional, Sequence


def _ensure_duckclaw_llm_env_from_legacy_llm_vars() -> None:
    """
    Copia ``LLM_*`` del .env a ``DUCKCLAW_LLM_*`` cuando estas últimas están vacías.

    El gateway y el forge leen ``DUCKCLAW_LLM_PROVIDER`` / ``MODEL`` / ``BASE_URL``;
    muchos `.env` solo definen ``LLM_PROVIDER``, etc.
    """
    if not (os.environ.get("DUCKCLAW_LLM_PROVIDER") or "").strip():
        leg = (os.environ.get("LLM_PROVIDER") or "").strip()
        if leg:
            os.environ["DUCKCLAW_LLM_PROVIDER"] = leg
    if not (os.environ.get("DUCKCLAW_LLM_MODEL") or "").strip():
        leg = (os.environ.get("LLM_MODEL") or "").strip()
        if leg:
            os.environ["DUCKCLAW_LLM_MODEL"] = leg
    if not (os.environ.get("DUCKCLAW_LLM_BASE_URL") or "").strip():
        leg = (os.environ.get("LLM_BASE_URL") or "").strip()
        if leg:
            os.environ["DUCKCLAW_LLM_BASE_URL"] = leg


def mlx_openai_compatible_base_url() -> str:
    """Base OpenAI-compatible para ``mlx_lm.server`` (``MLX_PORT``, default 8080)."""
    port = (os.environ.get("MLX_PORT") or "8080").strip() or "8080"
    return f"http://127.0.0.1:{port}/v1"


def infer_provider_from_openai_compatible_llm(llm: Any) -> str:
    """
    Deduce proveedor desde ``ChatOpenAI`` (base URL) cuando la etiqueta ``llm_provider`` del grafo
    no coincide (p. ej. caché de worker o cadena vacía que cayó en ``DUCKCLAW_LLM_PROVIDER=mlx``).
    """
    if llm is None:
        return ""
    bound = getattr(llm, "bound", None)
    if bound is not None and bound is not llm:
        inner = infer_provider_from_openai_compatible_llm(bound)
        if inner:
            return inner
    bases: list[str] = []
    for attr in ("openai_api_base", "base_url"):
        v = getattr(llm, attr, None)
        if v is None:
            continue
        s = str(v).strip()
        if s:
            bases.append(s.lower())
    for attr in ("client", "async_client", "root_client", "root_async_client"):
        c = getattr(llm, attr, None)
        if c is None:
            continue
        bu = getattr(c, "base_url", None)
        if bu is not None:
            bases.append(str(bu).strip().lower())
    u = " ".join(bases)
    if u:
        if "deepseek" in u:
            return "deepseek"
        if "groq.com" in u:
            return "groq"
        if "anthropic" in u:
            return "anthropic"
        if "api.openai.com" in u and "azure" not in u:
            return "openai"
        if "127.0.0.1" in u or "localhost" in u:
            return "mlx"
    # Sin URL aún (cliente lazy) o host no reconocido: pistas por nombre de modelo (p. ej. deepseek-chat).
    mn = ""
    for attr in ("model_name", "model", "model_id"):
        v = getattr(llm, attr, None)
        if v is None:
            continue
        ms = str(v).strip()
        if ms:
            mn = ms.lower()
            break
    if "deepseek" in mn:
        return "deepseek"
    return ""


def is_transient_inference_connection_error(exc: BaseException) -> bool:
    """Errores transitorios de transporte (backend local remoto, red, reinicios)."""
    if isinstance(exc, (ConnectionError, TimeoutError, BrokenPipeError)):
        return True
    name = type(exc).__name__
    if name in ("APIConnectionError", "ConnectError", "ReadTimeout", "WriteTimeout", "RemoteProtocolError"):
        return True
    low = str(exc).lower()
    return "connection refused" in low or "connection reset" in low or "eof occurred" in low


def _llm_invoke_max_attempts_from_env() -> int:
    raw = (os.environ.get("DUCKCLAW_LLM_INVOKE_MAX_ATTEMPTS") or "3").strip()
    try:
        n = int(raw)
        return max(1, min(n, 10))
    except ValueError:
        return 3


def _llm_invoke_retry_delay_sec_from_env() -> float:
    raw = (os.environ.get("DUCKCLAW_LLM_INVOKE_RETRY_DELAY_SEC") or "0.4").strip()
    try:
        return max(0.0, min(float(raw), 30.0))
    except ValueError:
        return 0.4


def invoke_chat_model_with_transient_retries(
    llm: Any,
    messages: Any,
    **invoke_kwargs: Any,
) -> Any:
    """
    ``llm.invoke`` con reintentos solo ante fallos transitorios (MLX local, red inestable).

    ``DUCKCLAW_LLM_INVOKE_MAX_ATTEMPTS`` (default 3), ``DUCKCLAW_LLM_INVOKE_RETRY_DELAY_SEC`` (default 0.4).
    """
    max_attempts = _llm_invoke_max_attempts_from_env()
    delay_sec = _llm_invoke_retry_delay_sec_from_env()
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return llm.invoke(messages, **invoke_kwargs)
        except Exception as exc:
            last_exc = exc
            if attempt >= max_attempts or not is_transient_inference_connection_error(exc):
                raise
            if delay_sec > 0:
                time.sleep(delay_sec)
    assert last_exc is not None
    raise last_exc


def invoke_chat_model_with_transient_retries_and_fallback(
    primary: Any,
    fallback: Any | None,
    messages: Any,
    **invoke_kwargs: Any,
) -> Any:
    """
    Tras reintentos transitorios en el backend **primary**, si sigue fallando y existe **fallback**
    (otra tripleta vía env), intenta el mismo ``invoke`` en el modelo alternativo (mismo mensaje/tools bind).
    """
    _log = logging.getLogger(__name__)
    try:
        return invoke_chat_model_with_transient_retries(primary, messages, **invoke_kwargs)
    except Exception as first_exc:
        if fallback is None:
            raise
        _log.info(
            "llm invoke: primary failed (%s), trying fallback backend",
            type(first_exc).__name__,
            exc_info=False,
        )
        return invoke_chat_model_with_transient_retries(fallback, messages, **invoke_kwargs)


_REMOTE_USER_FACING_LLM = frozenset({"deepseek", "groq", "openai", "anthropic"})
_LOCAL_INFERENCE_FAIL_LABELS = frozenset({"mlx", "iotcorelabs"})


def failure_provider_label_for_llm_invoke(llm: Any, reconciled_provider: str) -> str:
    """
    Etiqueta para mensajes de fallo al usuario: combina inferencia por URL/modelo con la tripleta
    reconciliada del grafo. Si la heurística devuelve ``mlx``/``iotcorelabs`` (p. ej. ``localhost``)
    pero el turno se compiló con proveedor remoto vía ``/model``, gana el remoto para no culpar al
    motor local por error.
    """
    rec = (reconciled_provider or "").strip().lower()
    inf = (infer_provider_from_openai_compatible_llm(llm) or "").strip().lower()
    if not inf:
        out = rec
    elif inf in _LOCAL_INFERENCE_FAIL_LABELS and rec in _REMOTE_USER_FACING_LLM:
        out = rec
    else:
        out = inf
    # PM2/.env a veces dejan DUCKCLAW_* en mlx y LLM_* en deepseek; si la etiqueta sigue siendo local,
    # tomar el primer proveedor remoto explícito en env (no sustituye MLX real si ambos dicen mlx).
    if out in _LOCAL_INFERENCE_FAIL_LABELS:
        for _ek in ("DUCKCLAW_LLM_PROVIDER", "LLM_PROVIDER"):
            _ev = (os.environ.get(_ek) or "").strip().lower()
            if _ev in _REMOTE_USER_FACING_LLM:
                # ``LLM_PROVIDER=groq`` suele quedar como default en .env mientras el cliente apunta a
                # localhost; no culpar a Groq por ``Connection refused`` al motor local.
                if _ev == "groq" and inf in _LOCAL_INFERENCE_FAIL_LABELS:
                    continue
                out = _ev
                break
    return out


def reconcile_worker_provider_label(
    llm: Any,
    provider: str,
    llm_provider_arg: Optional[str],
) -> str:
    """
    Etiqueta efectiva para recortes de contexto y mensajes de fallo del agente.
    Si el manifest pasó ``mlx`` pero el cliente apunta a api.deepseek.com, corrige a ``deepseek``.
    """
    decl = (llm_provider_arg or "").strip().lower()
    inferred = infer_provider_from_openai_compatible_llm(llm)
    if decl and decl not in ("none_llm", "none"):
        if decl in ("mlx", "iotcorelabs") and inferred and inferred not in ("mlx", "iotcorelabs"):
            return inferred
        return decl
    if inferred:
        return inferred
    return (provider or "").strip().lower() or "none_llm"


# Repo HF por defecto para alias cortos gemma4 / gemma-4 (OpenAI-compatible MLX / ``mlx_vlm``).
# Override: ``MLX_GEMMA4_MODEL_PATH`` (ruta local o repo ``org/model``). Usar un id ``mlx-community/gemma-4-*``.
# E4B alinea con checkpoints locales típicos (p. ej. ``gemma4-e4b``); E2B sigue disponible vía repo HF explícito.
MLX_GEMMA4_DEFAULT_REPO_ID = "mlx-community/gemma-4-e4b-it-4bit"


def _is_gemma4_short_name(requested: str) -> bool:
    t = (requested or "").strip().lower().replace("_", "-")
    return t in ("gemma4", "gemma-4")


def _resolve_gemma4_openai_model_id() -> str:
    """Mismo identificador que debe usar el servidor MLX precargado (ruta local o repo HF)."""
    g4 = (os.environ.get("MLX_GEMMA4_MODEL_PATH") or "").strip()
    if g4:
        return g4
    mlx = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
    if mlx and "gemma" in mlx.lower():
        return mlx
    return MLX_GEMMA4_DEFAULT_REPO_ID


def mlx_openai_compatible_model_name(requested: str) -> str:
    """
    Nombre de modelo para ``ChatOpenAI`` → ``mlx_lm.server``.

    Alias cortos (p. ej. ``Slayer-8B`` guardados en chat o ``LLM_MODEL``) no son repo HF
    ni ruta en disco; LangChain puede intentar resolverlos en HuggingFace y MLX devuelve 404.
    En ese caso se usa ``MLX_MODEL_ID`` / ``MLX_MODEL_PATH``. Rutas (``/``, ``./``),
    rutas con subcarpetas (``/``) y pares tipo ``org/model`` se respetan.

    Alias **gemma4** / **gemma-4** (cualquier capitalización) resuelven a
    ``MLX_GEMMA4_MODEL_PATH`` si está definido; si no, a ``MLX_MODEL_ID`` / ``MLX_MODEL_PATH``
    cuando el valor contiene ``gemma`` (mismo id que ``pm2`` suele precargar); si no,
    ``MLX_GEMMA4_DEFAULT_REPO_ID``.
    """
    r = (requested or "").strip()
    if _is_gemma4_short_name(r):
        return _resolve_gemma4_openai_model_id()
    if not r:
        return (
            (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
            or "mlx-community/Llama-3.2-1B-Instruct"
        )
    if r.startswith("/") or r.startswith(("./", "../")):
        return r
    if "/" in r:
        return r
    mid = (os.environ.get("MLX_MODEL_ID") or os.environ.get("MLX_MODEL_PATH") or "").strip()
    return mid or r


def _mlx_base_url_is_incompatible(url: str) -> bool:
    u = (url or "").strip().lower()
    if not u:
        return True
    return any(h in u for h in ("groq.com", "deepseek.com", "anthropic.com", "api.openai.com"))


# EOT tokens comunes en modelos (Slayer, Llama, etc.)
_EOT_PATTERNS = (
    "<|end_of_text|>",
    "<|eot_id|>",
    "&lt;|eot_id|&gt;",  # a veces copiado/escapado en HTML o clientes
    "<|end|>",
    "</s>",
    "<s>",
    "[INST]",
    "[/INST]",
)

# Sufijo EOT pegado al último carácter (p. ej. "...COP.<|eot_id|>") sin espacio
_EOT_TAIL = re.compile(
    r"(?:<\|eot_id\|>|<\|end_of_text\|>|<\|end\|>|</s>)\s*\Z",
    re.IGNORECASE,
)


def _strip_eot(text: str) -> str:
    """Elimina tokens de end-of-turn del texto."""
    if not text:
        return ""
    s = str(text)
    for pat in _EOT_PATTERNS:
        s = s.replace(pat, "")
    s = _EOT_TAIL.sub("", s)
    return s


# Prefijos que algunos modelos locales (p. ej. MLX/Slayer) repiten al imitar trazas HTTP/OpenAI.
_LEADING_ERROR_CODE_LINE = re.compile(r"^\s*Error\s+code:\s*\d+.*$", re.IGNORECASE)
# Líneas tipo ``### read_sql`` / ``### get_ibkr_portfolio`` (marcadores internos de salida de tools).
_TOOL_SECTION_HEADER_LINE = re.compile(r"^###\s+([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\s*$")


def _strip_tool_section_header_lines(text: str) -> str:
    """Quita líneas que solo nombran una tool en snake_case (no títulos Markdown humanos con espacios)."""
    if "### " not in text:
        return text
    lines = (text or "").split("\n")
    out: list[str] = []
    for ln in lines:
        if _TOOL_SECTION_HEADER_LINE.match(ln.strip()):
            continue
        out.append(ln)
    return "\n".join(out)


def _strip_leading_error_code_line(text: str) -> str:
    """Quita la primera línea tipo ``Error code: 200 - {...}`` si ocupa una sola línea."""
    raw = text or ""
    lines = raw.split("\n")
    if not lines:
        return raw
    if _LEADING_ERROR_CODE_LINE.match(lines[0].strip()):
        return "\n".join(lines[1:]).lstrip()
    return raw


def strip_internal_tool_markdown_headers(text: str) -> str:
    """Quita líneas ``### snake_case_tool`` (salida intermedia); usar tras síntesis o en egress final."""
    return _strip_tool_section_header_lines(text or "")


def sanitize_worker_reply_phase1(text: str) -> str:
    """EOT + línea ``Error code:``; no quita ``### tool`` (necesario antes de ``reply_needs_nl_synthesis``)."""
    s = _strip_leading_error_code_line(text or "")
    return _strip_eot(s).strip()


def sanitize_worker_reply_text(text: str) -> str:
    """Limpia respuestas assistant para Telegram/trazas: basura HTTP + EOT + encabezados ``### tool``."""
    s = sanitize_worker_reply_phase1(text or "")
    s = _strip_tool_section_header_lines(s)
    return s.strip()


def strip_markdown_json_fence(text: str) -> str:
    s = (text or "").strip()
    if not s.startswith("```"):
        return s
    parts = s.split("```", 2)
    if len(parts) < 2:
        return s
    block = parts[1].strip()
    if block.lower().startswith("json"):
        block = block[4:].lstrip()
    return block.strip()


def coerce_json_tool_invoke(reply: str) -> tuple[str, dict[str, Any]] | None:
    """
    Algunos servidores OpenAI-compat (p. ej. MLX) devuelven la tool como JSON en ``content``
    sin rellenar ``tool_calls`` en el mensaje estructurado.
    """
    import json as _json

    s = strip_markdown_json_fence(reply)
    if not s.startswith("{"):
        return None
    try:
        data = _json.loads(s)
    except _json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    if not any(k in data for k in ("parameters", "args", "arguments")):
        return None
    name = data.get("name") or data.get("tool")
    if not name or not isinstance(name, str):
        return None
    params: dict[str, Any] = {}
    raw_p = data.get("parameters")
    if raw_p is None:
        raw_p = data.get("args")
    if isinstance(raw_p, dict):
        params = raw_p
    arg = data.get("arguments")
    if not params and arg is not None:
        if isinstance(arg, str):
            try:
                parsed = _json.loads(arg)
                if isinstance(parsed, dict):
                    params = parsed
            except _json.JSONDecodeError:
                pass
        elif isinstance(arg, dict):
            params = arg
    return (name, params)


def extract_embedded_json_tool_invokes(text: str) -> list[tuple[str, dict[str, Any]]]:
    """
    Una o más invocaciones tool serializadas en texto (p. ej. MLX sin ``tool_calls``).

    Incluye el caso ``{"name": "a", ...}; {"name": "b", ...}`` donde ``json.loads``
    sobre el string completo falla.
    """
    raw = (text or "").strip()
    if not raw:
        return []
    single = coerce_json_tool_invoke(raw)
    if single:
        return [single]
    out: list[tuple[str, dict[str, Any]]] = []
    n = len(raw)
    i = 0
    while i < n:
        j = raw.find("{", i)
        if j < 0:
            break
        depth = 0
        k = j
        while k < n:
            ch = raw[k]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    got = coerce_json_tool_invoke(raw[j : k + 1])
                    if got:
                        out.append(got)
                    i = k + 1
                    while i < n and raw[i] in " \t\n\r;":
                        i += 1
                    break
            k += 1
        else:
            break
    return out


def lc_message_content_to_text(message: Any) -> str:
    """
    Extrae texto plano del ``content`` de un mensaje LangChain (str o lista de bloques).
    Evita ``str(AIMessage)`` cuando ``content`` es lista o cadena vacía mal manejada.
    """
    if message is None:
        return ""
    content: Any = getattr(message, "content", None)
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict):
                t = block.get("text")
                if isinstance(t, str):
                    parts.append(t)
                else:
                    c = block.get("content")
                    if isinstance(c, str):
                        parts.append(c)
            else:
                parts.append(str(block))
        return "".join(parts)
    return str(content)


def _safe_table_name(name: str) -> Optional[str]:
    """Devuelve el nombre si es seguro (solo alfanuméricos y _), o None."""
    if not name or not isinstance(name, str):
        return None
    n = name.strip()
    if not n:
        return None
    if re.search(r"[;\s\-'\"]|DROP|DELETE|TRUNCATE", n, re.IGNORECASE):
        return None
    if not re.match(r"^[a-zA-Z0-9_]+$", n):
        return None
    return n


def _validate_read_sql(sql: str) -> tuple[bool, str]:
    """Valida que la SQL sea de solo lectura. Devuelve (ok, err)."""
    if not sql or not sql.strip():
        return False, "Consulta vacía."
    s = sql.strip().upper()
    forbidden = ("DROP", "INSERT", "UPDATE", "DELETE", "TRUNCATE", "CREATE", "ALTER")
    for kw in forbidden:
        if kw in s:
            return False, f"No se permiten operaciones {kw} en consultas de lectura."
    return True, ""


def _validate_write_sql(sql: str) -> tuple[bool, str]:
    """Valida que la SQL sea de escritura permitida (INSERT/UPDATE/DELETE). Devuelve (ok, err)."""
    if not sql or not sql.strip():
        return False, "Consulta vacía."
    s = sql.strip().upper()
    if any(kw in s for kw in ("DROP", "TRUNCATE", "CREATE", "ALTER")):
        return False, "No se permiten DROP, TRUNCATE, CREATE ni ALTER."
    if "SELECT" in s and "INSERT" not in s and "UPDATE" not in s and "DELETE" not in s:
        return False, "Para lectura usa run_read_sql."
    return True, ""


def bind_tools_with_parallel_default(llm: Any, tools: Sequence[Any], **kwargs: Any) -> Any:
    """
    Llama a ``llm.bind_tools`` con ``parallel_tool_calls=True`` cuando la firma lo admite
    (p. ej. ``langchain_openai.ChatOpenAI``: API OpenAI y servidores compatibles / MLX).
    Otros proveedores (Anthropic, Ollama, etc.) se dejan sin ese argumento.

    Para **forzar** una tool concreta (p. ej. ``tavily_search``), LangChain acepta
    ``tool_choice={"type": "function", "function": {"name": "tavily_search"}}`` en kwargs
    (formato OpenAI). Las ``StructuredTool`` con ``args_schema`` (Pydantic) generan el
    JSON Schema que el endpoint espera; si una tool no aparece en la petición, revisar que
    el paquete esté en el esquema y que el modelo esté en modo tools.
    """
    try:
        sig = inspect.signature(llm.bind_tools)
    except (TypeError, ValueError):
        return llm.bind_tools(tools, **kwargs)
    bind_kwargs = dict(kwargs)
    if (
        "parallel_tool_calls" in sig.parameters
        and "parallel_tool_calls" not in bind_kwargs
    ):
        env_pt = (os.environ.get("DUCKCLAW_MLX_PARALLEL_TOOL_CALLS") or "").strip().lower()
        if env_pt in ("0", "false", "no", "off"):
            bind_kwargs["parallel_tool_calls"] = False
        elif env_pt in ("1", "true", "yes", "on"):
            bind_kwargs["parallel_tool_calls"] = True
        elif infer_provider_from_openai_compatible_llm(llm) == "mlx":
            # mlx_lm Gemma 4 tool parser hace json.loads estricto sobre el bloque de argumentos;
            # varias tool_calls en un turno o JSON con comillas simples rompe el servidor (ver mlx_lm/tool_parsers/gemma4.py).
            model_hint = ""
            for attr in ("model_name", "model", "model_id"):
                v = getattr(llm, attr, None)
                if v is not None and str(v).strip():
                    model_hint = str(v).strip().lower()
                    break
            bind_kwargs["parallel_tool_calls"] = "gemma" not in model_hint
        else:
            bind_kwargs["parallel_tool_calls"] = True
    return llm.bind_tools(tools, **bind_kwargs)


def build_llm(
    provider: str,
    model: str = "",
    base_url: str = "",
    *,
    prefer_env_provider: bool = True,
) -> Optional[Any]:
    """
    Construye un LLM según el proveedor.
    Devuelve None para none_llm o si no se puede inicializar.

    ``prefer_env_provider`` (default True): env gana sobre los argumentos para **provider**,
    **model** y **base_url** (comportamiento histórico / tests). Pon False cuando la tripleta
    viene resuelta por chat (p. ej. /model) y debe imponerse por completo sobre PM2 (mlx +
    ruta local + URL 127.0.0.1).
    """
    _ensure_duckclaw_llm_env_from_legacy_llm_vars()
    p_arg = (provider or "").strip().lower()
    p_env = (os.environ.get("DUCKCLAW_LLM_PROVIDER") or "").strip().lower()
    m_arg = (model or "").strip()
    m_env = (os.environ.get("DUCKCLAW_LLM_MODEL") or "").strip()
    url_arg = (base_url or "").strip()
    url_env = (os.environ.get("DUCKCLAW_LLM_BASE_URL") or "").strip()
    # none_llm explícito no debe sustituirse por variables de entorno (p. ej. tests o apagado LLM).
    if p_arg in ("none_llm", "none"):
        p = p_arg
    elif prefer_env_provider:
        p = p_env or p_arg
    else:
        p = p_arg or p_env
    if prefer_env_provider:
        m = m_env or m_arg
        url = url_env or url_arg
    else:
        m = m_arg or m_env
        url = url_arg or url_env

    if p in ("none_llm", "none", ""):
        return None

    if p == "openai":
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=m or "gpt-4o-mini",
                temperature=0,
                base_url=url or None,
            )
        except Exception:
            raise RuntimeError("OpenAI requiere langchain-openai y OPENAI_API_KEY.")

    if p == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model=m or "claude-3-5-haiku-20241022",
                temperature=0,
            )
        except Exception:
            raise RuntimeError("Anthropic requiere langchain-anthropic y ANTHROPIC_API_KEY.")

    if p == "deepseek":
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model=m or "deepseek-chat",
                temperature=0,
                base_url=url or "https://api.deepseek.com/v1",
                api_key=os.environ.get("DEEPSEEK_API_KEY", ""),
            )
        except Exception:
            raise RuntimeError("DeepSeek requiere DEEPSEEK_API_KEY.")

    if p == "groq":
        key = (os.environ.get("GROQ_API_KEY") or "").strip()
        if not key:
            raise RuntimeError("Groq requiere GROQ_API_KEY.")
        try:
            from langchain_openai import ChatOpenAI

            # DUCKCLAW_LLM_BASE_URL suele quedar en DeepSeek/Otro al cambiar solo el provider;
            # no enviar peticiones Groq a otro host (p. ej. 402 Insufficient Balance de DeepSeek).
            _groq_default = "https://api.groq.com/openai/v1"
            u_low = (url or "").strip().lower()
            if not u_low or "deepseek" in u_low:
                groq_base = _groq_default.rstrip("/")
            else:
                groq_base = (url or _groq_default).rstrip("/")
            _mx = (os.environ.get("DUCKCLAW_GROQ_MAX_OUTPUT_TOKENS") or "").strip()
            _kwargs: dict[str, Any] = {
                "model": m or "llama-3.3-70b-versatile",
                "temperature": 0,
                "base_url": groq_base,
                "api_key": key,
            }
            if _mx:
                try:
                    _kwargs["max_tokens"] = max(256, min(int(_mx), 8192))
                except ValueError:
                    pass
            return ChatOpenAI(**_kwargs)
        except Exception:
            raise RuntimeError("Groq requiere langchain-openai y GROQ_API_KEY.")

    if p == "ollama":
        try:
            from langchain_community.chat_models import ChatOllama
            return ChatOllama(
                model=m or "llama3.2",
                base_url=url or "http://localhost:11434",
                temperature=0,
            )
        except Exception:
            try:
                from langchain_ollama import ChatOllama
                return ChatOllama(
                    model=m or "llama3.2",
                    base_url=url or "http://localhost:11434",
                    temperature=0,
                )
            except Exception:
                raise RuntimeError("Ollama requiere langchain-community o langchain-ollama.")

    if p in ("mlx", "iotcorelabs"):
        try:
            from langchain_openai import ChatOpenAI
            if p == "mlx":
                if _mlx_base_url_is_incompatible(url):
                    url = mlx_openai_compatible_base_url()
                m = mlx_openai_compatible_model_name(m)
            _mlx_out = (os.environ.get("DUCKCLAW_MLX_MAX_OUTPUT_TOKENS") or "4096").strip()
            try:
                _mt = max(512, min(int(_mlx_out), 8192))
            except ValueError:
                _mt = 4096
            return ChatOpenAI(
                model=m or "default",
                temperature=0,
                base_url=url or None,
                api_key=os.environ.get("OPENAI_API_KEY", "not-needed"),
                max_tokens=_mt,
            )
        except Exception:
            raise RuntimeError(f"{p} requiere URL base y langchain-openai.")

    if p == "huggingface":
        try:
            from langchain_huggingface import ChatHuggingFace
            return ChatHuggingFace(
                model=m or "mistralai/Mistral-7B-Instruct-v0.3",
                temperature=0,
                huggingfacehub_api_token=os.environ.get("HUGGINGFACE_API_KEY") or os.environ.get("HF_TOKEN"),
            )
        except Exception:
            try:
                from langchain_community.chat_models import HuggingFaceEndpoint
                return HuggingFaceEndpoint(
                    repo_id=m or "mistralai/Mistral-7B-Instruct-v0.3",
                    huggingfacehub_api_token=os.environ.get("HUGGINGFACE_API_KEY") or os.environ.get("HF_TOKEN"),
                    task="text-generation",
                )
            except Exception:
                raise RuntimeError("HuggingFace requiere HUGGINGFACE_API_KEY o HF_TOKEN.")

    return None


def build_llm_fallback_from_env() -> Optional[Any]:
    """
    Segundo LLM opcional para el grafo del worker: ``DUCKCLAW_LLM_FALLBACK_PROVIDER`` (+ MODEL, BASE_URL).
    No usa ``prefer_env_provider``: la tripleta es explícita. Devuelve None si no está configurado.
    """
    p = (os.environ.get("DUCKCLAW_LLM_FALLBACK_PROVIDER") or "").strip().lower()
    if not p or p in ("none", "none_llm"):
        return None
    m = (os.environ.get("DUCKCLAW_LLM_FALLBACK_MODEL") or "").strip()
    u = (os.environ.get("DUCKCLAW_LLM_FALLBACK_BASE_URL") or "").strip()
    return build_llm(p, m, u, prefer_env_provider=False)


def build_duckclaw_tools(db: Any) -> list[Any]:
    """Devuelve herramientas: list_tables, describe_table, run_read_sql, run_write_sql."""
    from langchain_core.tools import StructuredTool

    def list_tables() -> str:
        try:
            r = db.query("SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'")
            rows = r if isinstance(r, list) else (r if isinstance(r, str) else [])
            if isinstance(rows, str):
                import json
                try:
                    rows = json.loads(rows)
                except Exception:
                    rows = []
            names = [row.get("table_name", row) if isinstance(row, dict) else str(row) for row in (rows or [])]
            return "\n".join(str(n) for n in names) if names else "No hay tablas."
        except Exception as e:
            return f"Error: {e}"

    def describe_table(table_name: str) -> str:
        safe = _safe_table_name(table_name)
        if not safe:
            return "Error: nombre de tabla no válido."
        try:
            r = db.query(f"DESCRIBE {safe}")
            rows = r if isinstance(r, list) else (r if isinstance(r, str) else [])
            if isinstance(rows, str):
                import json
                try:
                    rows = json.loads(rows)
                except Exception:
                    rows = []
            lines = []
            for row in (rows or []):
                if isinstance(row, dict):
                    col = row.get("column_name", row.get("field", ""))
                    dtype = row.get("column_type", row.get("type", ""))
                    lines.append(f"{col}: {dtype}")
                else:
                    lines.append(str(row))
            return "\n".join(lines) if lines else "Sin columnas."
        except Exception as e:
            return f"Error: {e}"

    def run_read_sql(sql: str) -> str:
        ok, err = _validate_read_sql(sql)
        if not ok:
            return f"Error: {err}"
        try:
            r = db.query(sql)
            if isinstance(r, str):
                return r
            import json
            return json.dumps(r, default=str, ensure_ascii=False)
        except Exception as e:
            return f"Error: {e}"

    def run_write_sql(sql: str) -> str:
        ok, err = _validate_write_sql(sql)
        if not ok:
            return f"Error: {err}"
        try:
            db.execute(sql)
            return "OK"
        except Exception as e:
            return f"Error: {e}"

    return [
        StructuredTool.from_function(list_tables, name="list_tables", description="Lista las tablas de la base de datos."),
        StructuredTool.from_function(describe_table, name="describe_table", description="Describe columnas de una tabla.", args_schema=None),
        StructuredTool.from_function(run_read_sql, name="run_read_sql", description="Ejecuta una consulta SQL de solo lectura (SELECT, SHOW)."),
        StructuredTool.from_function(run_write_sql, name="run_write_sql", description="Ejecuta INSERT, UPDATE o DELETE."),
    ]


def build_agent_graph(db: Any, llm: Optional[Any] = None) -> Any:
    """
    Construye un grafo LangGraph simple.
    Si llm es None, devuelve un grafo que responde con eco/confirmación sin LLM.
    """
    from langgraph.graph import END, StateGraph

    def prepare(state: dict) -> dict:
        incoming = (state.get("incoming") or "").strip()
        return {"incoming": incoming, "reply": ""}

    def agent_echo(state: dict) -> dict:
        incoming = state.get("incoming") or ""
        if llm is None:
            return {"reply": f"Recibí: {incoming}" if incoming else "Hola."}
        return {"reply": incoming}

    def set_reply(state: dict) -> dict:
        reply = state.get("reply") or agent_echo(state).get("reply", "")
        return {"reply": reply}

    graph = StateGraph(dict)
    graph.add_node("prepare", prepare)
    graph.add_node("agent", agent_echo)
    graph.add_node("set_reply", set_reply)
    graph.set_entry_point("prepare")
    graph.add_edge("prepare", "agent")
    graph.add_edge("agent", "set_reply")
    graph.add_edge("set_reply", END)
    return graph.compile()
