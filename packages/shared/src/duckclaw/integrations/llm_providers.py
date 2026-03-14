"""LLM provider factory and DuckClaw tools for agents."""

from __future__ import annotations

import re
from typing import Any, Optional

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


def build_llm(
    provider: str,
    model: str = "",
    base_url: str = "",
) -> Optional[Any]:
    """
    Construye un LLM según el proveedor.
    Devuelve None para none_llm o si no se puede inicializar.
    """
    p = (provider or "").strip().lower()
    m = (model or "").strip()
    url = (base_url or "").strip()

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
                api_key=__import__("os").environ.get("DEEPSEEK_API_KEY", ""),
            )
        except Exception:
            raise RuntimeError("DeepSeek requiere DEEPSEEK_API_KEY.")

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
            if not url and p == "mlx":
                url = "http://127.0.0.1:8080/v1"
            if not m and p == "mlx":
                m = "mlx-community/Llama-3.2-1B-Instruct"
            return ChatOpenAI(
                model=m or "default",
                temperature=0,
                base_url=url or None,
                api_key=__import__("os").environ.get("OPENAI_API_KEY", "not-needed"),
            )
        except Exception:
            raise RuntimeError(f"{p} requiere URL base y langchain-openai.")

    if p == "huggingface":
        try:
            from langchain_huggingface import ChatHuggingFace
            return ChatHuggingFace(
                model=m or "mistralai/Mistral-7B-Instruct-v0.3",
                temperature=0,
                huggingfacehub_api_token=__import__("os").environ.get("HUGGINGFACE_API_KEY") or __import__("os").environ.get("HF_TOKEN"),
            )
        except Exception:
            try:
                from langchain_community.chat_models import HuggingFaceEndpoint
                return HuggingFaceEndpoint(
                    repo_id=m or "mistralai/Mistral-7B-Instruct-v0.3",
                    huggingfacehub_api_token=__import__("os").environ.get("HUGGINGFACE_API_KEY") or __import__("os").environ.get("HF_TOKEN"),
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
