"""LLM provider factory and DuckClaw tools for agents."""

from __future__ import annotations

import inspect
import os
import re
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


def mlx_openai_compatible_model_name(requested: str) -> str:
    """
    Nombre de modelo para ``ChatOpenAI`` → ``mlx_lm.server``.

    Alias cortos (p. ej. ``Slayer-8B`` guardados en chat o ``LLM_MODEL``) no son repo HF
    ni ruta en disco; LangChain puede intentar resolverlos en HuggingFace y MLX devuelve 404.
    En ese caso se usa ``MLX_MODEL_ID`` / ``MLX_MODEL_PATH``. Rutas (``/``, ``./``),
    rutas con subcarpetas (``/``) y pares tipo ``org/model`` se respetan.
    """
    r = (requested or "").strip()
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
    "<|end|>",
    "</s>",
    "<s>",
    "[INST]",
    "[/INST]",
)


def _strip_eot(text: str) -> str:
    """Elimina tokens de end-of-turn del texto."""
    if not text:
        return ""
    s = str(text)
    for pat in _EOT_PATTERNS:
        s = s.replace(pat, "")
    return s


# Prefijos que algunos modelos locales (p. ej. MLX/Slayer) repiten al imitar trazas HTTP/OpenAI.
_LEADING_ERROR_CODE_LINE = re.compile(r"^\s*Error\s+code:\s*\d+.*$", re.IGNORECASE)


def _strip_leading_error_code_line(text: str) -> str:
    """Quita la primera línea tipo ``Error code: 200 - {...}`` si ocupa una sola línea."""
    raw = text or ""
    lines = raw.split("\n")
    if not lines:
        return raw
    if _LEADING_ERROR_CODE_LINE.match(lines[0].strip()):
        return "\n".join(lines[1:]).lstrip()
    return raw


def sanitize_worker_reply_text(text: str) -> str:
    """Limpia respuestas assistant para Telegram/trazas: basura HTTP simulada + EOT."""
    s = _strip_leading_error_code_line(text or "")
    return _strip_eot(s).strip()


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
