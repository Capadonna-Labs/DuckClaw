"""
DEPRECATED — Bot Telegram en polling legado.

Producción: webhook del api-gateway (``services/api-gateway/routers/telegram_inbound_webhook.py``).
Este módulo se conserva como stub de compatibilidad para tests y despliegues PM2 legacy.

Uso legacy (no recomendado):
  uv sync --extra agents
  uv run python -m duckclaw.graphs.telegram_bot

Requiere: TELEGRAM_BOT_TOKEN y opcionalmente rutas multiplex / DUCKDB_PATH (vía ``get_gateway_db_path``).
Lee variables desde .env en el directorio actual o en la raíz del proyecto.
"""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from duckclaw.utils.langsmith_trace import get_tracing_config

_AGENT_CONFIG_TABLE = "agent_config"


def _load_dotenv() -> None:
    """Carga .env en os.environ si existe (sin dependencia python-dotenv)."""
    for base in (Path.cwd(), Path(__file__).resolve().parent.parent.parent):
        env_file = base / ".env"
        if env_file.is_file():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, _, value = line.partition("=")
                        key = key.strip()
                        value = value.strip()
                        if value.startswith('"') and value.endswith('"'):
                            value = value[1:-1].replace('\\"', '"')
                        elif value.startswith("'") and value.endswith("'"):
                            value = value[1:-1].replace("\\'", "'")
                        if key:
                            os.environ.setdefault(key, value)
            except Exception:
                pass
            break
_DEFAULT_SYSTEM_PROMPT = (
    "Eres un asistente DuckClaw con acceso a DuckDB (SQL, PGQ, VSS). "
    "Responde de forma breve y clara; prioriza datos de la base antes de suposiciones."
)
_DEFAULT_FRAMEWORK = "langgraph"

_ARTIFACT_SEARCH_DIRS = ("output/sandbox/default", "output")


def _truncate_at_break(text: str, max_len: int = 600) -> str:
    if not text or len(text) <= max_len:
        return text
    s = text[: max_len + 1]
    for sep in ("\n\n", ".\n", "\n", ". ", " "):
        idx = s.rfind(sep)
        if idx > max_len // 2:
            return text[: idx + len(sep)].strip()
    return text[:max_len].strip()


def _artifact_search_bases() -> tuple[Path, ...]:
    cwd = Path.cwd()
    return (cwd,)


def _resolve_artifact_path(raw: str, *, extensions: tuple[str, ...]) -> str | None:
    m_clean = (raw or "").strip()
    if not m_clean:
        return None
    p = Path(m_clean)
    if p.is_absolute() and p.is_file() and p.suffix.lower() in extensions:
        return str(p.resolve())
    fname = p.name
    for base in _artifact_search_bases():
        for sub in _ARTIFACT_SEARCH_DIRS:
            candidate = (base / sub / fname).resolve()
            if candidate.is_file() and candidate.suffix.lower() in extensions:
                return str(candidate)
        candidate = (base / m_clean).resolve()
        if candidate.is_file() and candidate.suffix.lower() in extensions:
            return str(candidate)
    return None


def _extract_paths_by_extension(text: str, extensions: tuple[str, ...]) -> list[str]:
    if not (text or "").strip():
        return []
    ext_pat = "|".join(re.escape(e.lstrip(".")) for e in extensions)
    pattern = rf"([^\s`\"'<>]+\.(?:{ext_pat}))"
    seen: set[str] = set()
    found: list[str] = []
    for match in re.findall(pattern, text, re.IGNORECASE):
        resolved = _resolve_artifact_path(match, extensions=extensions)
        if resolved and resolved not in seen:
            seen.add(resolved)
            found.append(resolved)
    return found


def _extract_image_paths(text: str) -> list[str]:
    return _extract_paths_by_extension(text, (".png", ".jpg", ".jpeg", ".webp"))


def _extract_excel_paths(text: str) -> list[str]:
    return _extract_paths_by_extension(text, (".xlsx",))


def _is_export_hashed_md(filename: str) -> bool:
    name = Path(filename).stem
    return bool(re.match(r"^export_[a-f0-9]{8}$", name, re.I))


def _extract_markdown_paths(text: str) -> list[str]:
    paths = _extract_paths_by_extension(text, (".md",))
    return [p for p in paths if not _is_export_hashed_md(p)]


def _strip_paths_from_reply(text: str) -> str:
    if not (text or "").strip():
        return text or ""
    s = re.sub(
        r"\s*[.;]?\s*(?:El gráfico|La gráfica|El diagrama|La imagen)\s+(?:ha\s+sido\s+)?guardad[oa]\s+en:\s*[^\n]+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    s = re.sub(r"\s*[.;]?\s*El archivo\s+se\s+ha\s+guardado\s+en:\s*[^\n]+", "", s, flags=re.IGNORECASE)
    s = re.sub(r"\s*[.;]?\s*Archivo\s+(?:Excel|Markdown)?\s*guardado:\s*[^\n]+", "", s, flags=re.IGNORECASE)
    path_kw = ("guardado en", "guardada en", "se ha guardado", "saved in", "saved to", "ruta:", "path:")
    lines = []
    for line in s.split("\n"):
        low = line.strip().lower()
        if "/workspace/output/" in low:
            continue
        if any(k in low for k in path_kw):
            continue
        if any(ext in low for ext in (".png", ".jpg", ".jpeg", ".webp", ".xlsx", ".md")) and ("/" in line or "\\" in line):
            continue
        lines.append(line)
    return re.sub(r"\s{2,}", " ", "\n".join(lines).strip()).strip()


def _caption_for_photo(text: str, image_paths: list[str]) -> str:
    del image_paths
    return _truncate_at_break(_strip_paths_from_reply(text), 600)


def _log(msg: str) -> None:
    """Write logs unbuffered so PM2 shows them immediately."""
    print(msg, flush=True)


def _normalize_reply(reply: str) -> str:
    """Strip EOT tokens; hide raw tool-call JSON and error JSON so they never reach Telegram or logs."""
    import json
    from duckclaw.integrations.llm_providers import sanitize_worker_reply_text
    from duckclaw.utils.tool_reply import friendly_query_error

    s = sanitize_worker_reply_text(str(reply or ""))
    # If graph returned raw tool-call JSON (e.g. Slayer-8B text output), don't send to user
    if s.startswith("{") and '"name"' in s and ("parameters" in s or '"args"' in s):
        return "El asistente está procesando. Si no ves resultado, intenta de nuevo."
    # If graph returned raw {"error": "..."}, show a short message instead
    if s.startswith('{"error"') or (s.startswith("{") and '"error"' in s[:20]):
        try:
            data = json.loads(s)
            err = str((data or {}).get("error", ""))
            friendly = friendly_query_error(err)
            if friendly:
                return friendly
            if "Catalog Error" in err or "Table" in err or "does not exist" in err:
                return "Esa tabla no existe. Pregunta por las tablas disponibles."
            return "No se pudo completar la operación."
        except (json.JSONDecodeError, TypeError):
            pass
    return s or ""


def _format_reply_for_telegram(reply: str, max_len: int = 800) -> str:
    """Convierte markdown del agente a HTML seguro para Telegram."""
    from duckclaw.utils.telegram_markdown_v2 import llm_markdown_to_telegram_html

    if not reply:
        return ""
    html = llm_markdown_to_telegram_html(reply.strip())
    return _truncate_at_break(html, max_len) if len(html) > max_len else html


def _persist_conversation(db: Any, chat_id: Any, role: str, content: str) -> None:
    """Guarda un turno (user/assistant) en telegram_conversation para memoria."""
    if not content or not str(content).strip():
        return
    try:
        esc = str(content).replace("'", "''")[:16384]
        db.execute(
            f"INSERT INTO telegram_conversation (chat_id, role, content) VALUES ({int(chat_id)}, '{role}', '{esc}')"
        )
    except Exception:
        pass


def _get_db_path() -> str:
    from duckclaw.gateway_db import get_gateway_db_path

    path = (get_gateway_db_path() or "").strip()
    if path:
        return str(Path(path).resolve())
    return str(Path.cwd() / "duckclaw_agents.duckdb")


def _worker_db_path() -> str:
    """Ruta a la DB de workers. Por defecto usa la misma que el agente (backward compat).
    Si DUCKCLAW_WORKERS_DB_PATH está definida, usa esa ruta para una DB separada."""
    env_path = os.environ.get("DUCKCLAW_WORKERS_DB_PATH", "").strip()
    if env_path:
        return str(Path(env_path).resolve())
    return _get_db_path()


def _load_wizard_config() -> dict:
    """Carga la config guardada por la TUI (scripts/install_duckclaw.sh → wizard)."""
    import json
    path = Path.home() / ".config" / "duckclaw" / "wizard_config.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def _ensure_agent_config(db: Any) -> None:
    db.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_AGENT_CONFIG_TABLE} (
            key VARCHAR PRIMARY KEY,
            value TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Valores por defecto si no existen; sembrar llm_* desde wizard si existe
    try:
        import json
        r = db.query(f"SELECT key, value FROM {_AGENT_CONFIG_TABLE}")
        rows = json.loads(r) if isinstance(r, str) else r
        keys_present = {row.get("key") for row in (rows or []) if isinstance(row, dict)}
        defaults = [("framework", _DEFAULT_FRAMEWORK), ("system_prompt", _DEFAULT_SYSTEM_PROMPT)]
        wizard = _load_wizard_config()
        for k, v in wizard.items():
            if k in ("llm_provider", "llm_model", "llm_base_url") and v:
                defaults.append((k, str(v)))
            if k in ("save_grpo_traces", "send_to_langsmith") and v is not None:
                defaults.append((k, "true" if (v is True or str(v).lower() in ("true", "1", "yes", "y", "sí", "si")) else "false"))
        for k, v in defaults:
            if k not in keys_present:
                esc = str(v).replace("'", "''")[:16384]
                db.execute(
                    f"INSERT INTO {_AGENT_CONFIG_TABLE} (key, value) VALUES ('{k}', '{esc}')"
                )
    except Exception:
        pass


def _get_config(db: Any) -> dict:
    _ensure_agent_config(db)
    import json
    r = db.query(f"SELECT key, value FROM {_AGENT_CONFIG_TABLE}")
    rows = json.loads(r) if isinstance(r, str) else r
    out = {}
    for row in (rows or []):
        if isinstance(row, dict):
            out[row.get("key", "")] = row.get("value", "")
    # Rellenar llm_* y GRPO desde wizard si no están en agent_config
    wizard = _load_wizard_config()
    for key in ("llm_provider", "llm_model", "llm_base_url"):
        if not out.get(key) and wizard.get(key):
            out[key] = str(wizard[key])
    for key in ("save_grpo_traces", "send_to_langsmith"):
        if key not in out or out.get(key) == "":
            wv = wizard.get(key)
            if wv is not None:
                out[key] = bool(wv) if isinstance(wv, bool) else str(wv).lower() in ("true", "1", "yes", "y", "sí", "si")
    # Precedencia final: variables de entorno de ejecución.
    # El instalador exporta DUCKCLAW_LLM_* al arrancar, así que deben poder
    # sobrescribir valores viejos persistidos en agent_config.
    env_overrides = {
        "llm_provider": os.environ.get("DUCKCLAW_LLM_PROVIDER", "").strip(),
        "llm_model": os.environ.get("DUCKCLAW_LLM_MODEL", "").strip(),
        "llm_base_url": os.environ.get("DUCKCLAW_LLM_BASE_URL", "").strip(),
    }
    for key, val in env_overrides.items():
        if val:
            out[key] = val
    for key, env_key in (("save_grpo_traces", "DUCKCLAW_SAVE_GRPO_TRACES"), ("send_to_langsmith", "DUCKCLAW_SEND_TO_LANGSMITH")):
        ev = os.environ.get(env_key, "").strip().lower()
        if ev:
            out[key] = ev in ("true", "1", "yes", "y", "sí", "si")
    return out


def _set_config(db: Any, key: str, value: str) -> None:
    _ensure_agent_config(db)
    k = str(key).replace("'", "''")[:128]
    v = str(value).replace("'", "''")[:16384]
    db.execute(
        f"""
        INSERT INTO {_AGENT_CONFIG_TABLE} (key, value) VALUES ('{k}', '{v}')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """
    )


def _get_store_db(config: dict) -> Any:
    """Deprecated — store_db_path / DUCKCLAW_STORE_DB_PATH ya no se usan en el core genérico."""
    _ = config
    return None


def _build_graph_via_forge(
    db: Any,
    system_prompt: str,
    llm_provider: str = "",
    llm_model: str = "",
    llm_base_url: str = "",
    store_db: Optional[Any] = None,
    save_traces: bool = False,
    send_to_langsmith: bool = False,
    worker_id: Optional[str] = None,
) -> Any:
    """Build compiled LangGraph via AgentAssembler (forge). Requires a valid LLM."""
    from duckclaw.integrations.llm_providers import build_llm
    from duckclaw.forge import AgentAssembler, ENTRY_ROUTER_YAML, WORKERS_TEMPLATES_DIR

    provider = (llm_provider or "").strip().lower() or "none_llm"
    llm = build_llm(provider, (llm_model or "").strip(), (llm_base_url or "").strip())
    # Workers support none_llm (llm=None); entry router requires an LLM
    if llm is None and not worker_id:
        raise RuntimeError(
            "Configura llm_provider en /setup (openai, anthropic, deepseek, mlx, iotcorelabs). "
            "O añade OPENAI_API_KEY / ANTHROPIC_API_KEY en .env."
        )

    if worker_id:
        yaml_path = WORKERS_TEMPLATES_DIR / worker_id / "manifest.yaml"
    else:
        yaml_path = ENTRY_ROUTER_YAML

    return AgentAssembler.from_yaml(yaml_path).build(
        db=db,
        llm=llm,
        store_db=store_db,
        system_prompt=system_prompt,
        llm_provider=(llm_provider or "").strip(),
        llm_model=(llm_model or "").strip(),
        save_traces=save_traces,
        send_to_langsmith=send_to_langsmith,
        db_path=_worker_db_path() if worker_id else None,
    )


def _run_bot() -> None:
    _load_dotenv()
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    if not token:
        _log("Falta TELEGRAM_BOT_TOKEN. Exporta la variable o ponla en .env en el directorio actual o en la raíz del proyecto.")
        raise SystemExit(1)

    try:
        from telegram.ext import ApplicationBuilder  # noqa: F401
    except ImportError:
        _log("Falta el extra telegram. Instala con:")
        _log("  uv sync --extra agents")
        _log("  # o: pip install 'duckclaw[agents]'   (usa comillas en zsh)")
        raise SystemExit(1)

    from duckclaw import DuckClaw
    from duckclaw.integrations.telegram import TelegramBotBase

    db_path = _get_db_path()
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    db = DuckClaw(db_path)

    # Persistir mensajes en telegram_messages (tabla estándar)
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_messages (
            message_id BIGINT, chat_id BIGINT, user_id BIGINT, username TEXT,
            text TEXT, raw_update_json TEXT, received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # Memoria de conversación: user + assistant para contexto multi-turno
    db.execute(
        """
        CREATE TABLE IF NOT EXISTS telegram_conversation (
            chat_id BIGINT, role TEXT, content TEXT, received_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    # GraphRAG (spec: Estructura_Basada_en_Grafos_DuckDB_PGQ_GraphRAG.md): memory_nodes, memory_edges, duckclaw_kg
    try:
        from duckclaw.graphs.graph_rag import ensure_graph_rag_schema
        ensure_graph_rag_schema(db)
    except Exception:
        pass

    class DynamicAgentBot(TelegramBotBase):
        def handle_message(self, update: Any) -> None:
            message = getattr(update, "effective_message", None)
            if message is None:
                return
            text = (getattr(message, "text", None) or getattr(message, "caption", None) or "").strip()
            chat_id = getattr(getattr(message, "chat", None), "id", None)
            user = getattr(message, "from_user", None)
            username = getattr(user, "username", None) or getattr(user, "first_name", None) or "unknown"
            _log(f"📩 Mensaje chat={chat_id} user={username}: {text}")

            # Comando /setup: cambiar system_prompt y framework en caliente
            if text.startswith("/setup"):
                _log("⚙️ Comando /setup recibido")
                self._handle_setup(message, text, chat_id)
                return

            # On-the-Fly CLI (spec: interfaz_de_comandos_dinamicos_On-the-Fly_CLI.md)
            from duckclaw.graphs.on_the_fly_commands import handle_command
            # tenant_id (por defecto) porque TelegramBot no define multi-tenant en este módulo.
            # request identity para whitelist del comando /team.
            user_id = getattr(getattr(message, "from_user", None), "id", None)
            cmd_reply = handle_command(
                self.db,
                chat_id,
                text,
                requester_id=user_id,
                tenant_id="default",
                vault_user_id=user_id,
                username=str(username or ""),
            )
            if cmd_reply is not None:
                _log(f"📋 Comando ejecutado chat={chat_id}")
                asyncio.create_task(message.reply_text(cmd_reply, parse_mode="Markdown"))
                return

            # Saludo corto: responder sin invocar el grafo para evitar que el modelo devuelva tool calls
            _greetings = (
                "hola", "hey", "hi", "hello", "buenas", "qué tal", "que tal",
                "buenos días", "buenos dias", "buenas tardes", "buenas noches",
                "ola", "saludos",
            )
            if text and len(text) <= 25 and text.lower().strip() in _greetings:
                reply = "👋 Hola, ¿en qué puedo ayudarte?"
                _log(f"📤 Respuesta chat={chat_id}: {reply}")
                _persist_conversation(self.db, chat_id, "user", text)
                _persist_conversation(self.db, chat_id, "assistant", reply)
                asyncio.create_task(message.reply_text(reply))
                return

            # Cargar config desde agent_config (y wizard si falta llm_*)
            config = _get_config(self.db)
            system_prompt = config.get("system_prompt") or _DEFAULT_SYSTEM_PROMPT
            llm_provider = config.get("llm_provider") or ""
            llm_model = config.get("llm_model") or ""
            llm_base_url = config.get("llm_base_url") or ""
            store_db = _get_store_db(config)
            save_tr = config.get("save_grpo_traces", False)
            if isinstance(save_tr, str):
                save_tr = str(save_tr).lower() in ("true", "1", "yes", "y", "sí", "si")
            send_ls = config.get("send_to_langsmith", False)
            if isinstance(send_ls, str):
                send_ls = str(send_ls).lower() in ("true", "1", "yes", "y", "sí", "si")

            # Resolver el model ID — misma prioridad que build_llm para consistencia
            def _resolve_display_model(provider: str, model: str, base_url: str) -> str:
                if provider == "mlx":
                    # 1. MLX_MODEL_ID del env (ruta local — más confiable)
                    mid = os.environ.get("MLX_MODEL_ID", "").strip()
                    if not mid:
                        mid = os.environ.get("MLX_MODEL_PATH", "").strip()
                    if mid:
                        # Mostrar solo el nombre del directorio para brevedad
                        name = mid.rstrip("/").rsplit("/", 1)[-1]
                        return f"mlx:{name}"
                    return f"mlx:{model or 'local'}"
                if model:
                    return f"{provider}:{model}"
                return provider or "none_llm"

            display_model = _resolve_display_model(llm_provider, llm_model, llm_base_url)
            _log(f"🤔 [{display_model}] pensando...")

            from duckclaw.graphs.on_the_fly_commands import (
                append_task_audit,
                get_chat_state,
                get_history_limit_for_chat,
                get_worker_id_for_chat,
                save_last_audit,
            )
            history_limit = get_history_limit_for_chat(self.db, chat_id, default=10)
            worker_id = get_worker_id_for_chat(self.db, chat_id)
            use_rag = get_chat_state(self.db, chat_id, "use_rag") != "false"

            try:
                from duckclaw.graphs.activity import set_busy, set_idle
                set_busy(chat_id, task=text)
            except Exception:
                pass
            t0 = time.perf_counter()
            task_success = True
            try:
                graph = _build_graph_via_forge(
                    self.db,
                    system_prompt,
                    llm_provider=llm_provider,
                    llm_model=llm_model,
                    llm_base_url=llm_base_url,
                    store_db=store_db,
                    save_traces=save_tr,
                    send_to_langsmith=send_ls,
                    worker_id=worker_id or None,
                )
                history = self._get_history(chat_id, limit=history_limit)
                _persist_conversation(self.db, chat_id, "user", text)
                state = {"input": text, "incoming": text, "history": history}
                if use_rag:
                    try:
                        from duckclaw.graphs.graph_rag import graph_context_retriever
                        state["graph_context"] = graph_context_retriever(self.db, text) or ""
                    except Exception:
                        state["graph_context"] = ""
                wk = (worker_id or "forge").strip() or "forge"
                trace_cfg = get_tracing_config("default", wk, str(chat_id))
                result = graph.invoke(state, trace_cfg)
                reply = result.get("reply") or ""
            except RuntimeError as e:
                reply = str(e)
                task_success = False
            except Exception as e:
                reply = f"Error del agente: {e}"
                task_success = False
                import traceback
                traceback.print_exc()
            finally:
                try:
                    from duckclaw.graphs.activity import set_idle
                    set_idle(chat_id)
                except Exception:
                    pass
            reply = _normalize_reply(reply) or ""
            if use_rag and reply and text:
                try:
                    from duckclaw.graphs.graph_rag import run_graph_memory_extractor_background
                    from duckclaw.integrations.llm_providers import build_llm
                    _llm = build_llm(provider=llm_provider or "", model=llm_model or "", base_url=llm_base_url or "")
                    run_graph_memory_extractor_background(self.db, _llm, text, reply)
                except Exception:
                    pass
            elapsed_ms = int((time.perf_counter() - t0) * 1000)
            try:
                save_last_audit(self.db, chat_id, elapsed_ms)
                append_task_audit(
                    self.db,
                    chat_id,
                    worker_id or "",
                    text,
                    "SUCCESS" if task_success else "FAILED",
                    elapsed_ms,
                )
            except Exception:
                pass
            reply_for_user = reply
            reply_for_user = _strip_paths_from_reply(reply) or reply
            text_to_send = _format_reply_for_telegram(reply_for_user, max_len=3500) or "Sin respuesta."
            image_paths = []
            excel_paths = []
            markdown_paths = []
            image_paths = _extract_image_paths(reply)
            excel_paths = _extract_excel_paths(reply)
            markdown_paths = _extract_markdown_paths(reply)
            if image_paths:
                _log(f"🖼️ Enviando {len(image_paths)} imagen(es) a Telegram")
            if excel_paths:
                _log(f"📎 Enviando {len(excel_paths)} archivo(s) Excel a Telegram")
            if markdown_paths:
                _log(f"📄 Enviando {len(markdown_paths)} archivo(s) Markdown a Telegram")
            # Log lo que realmente se envía (para que coincida con Telegram)
            _log_preview = (text_to_send or "")[:200].replace("\n", " ")
            if len(text_to_send or "") > 200:
                _log_preview += "…"
            if image_paths:
                try:
                    caption_preview = _caption_for_photo(reply, image_paths)
                    caption_preview = _format_reply_for_telegram(caption_preview or "📊 Gráfica generada", max_len=600)
                    _log(f"📤 [{display_model}] chat={chat_id} ({elapsed_ms}ms): [imagen] {caption_preview[:120]}")
                except Exception:
                    _log(f"📤 [{display_model}] chat={chat_id} ({elapsed_ms}ms): [imagen]")
            elif excel_paths or markdown_paths:
                _log(f"📤 [{display_model}] chat={chat_id} ({elapsed_ms}ms): [documento] {_log_preview}")
            else:
                _log(f"📤 [{display_model}] chat={chat_id} ({elapsed_ms}ms): {_log_preview}")
            def _user_wants_excel_only() -> bool:
                """True si el usuario pidió explícitamente Excel (exportar a excel) y no reporte/informe MD."""
                t = (text or "").lower()
                if "excel" not in t:
                    return False
                if "reporte" in t or "informe" in t or "markdown" in t or " en md" in t:
                    return False
                return any(k in t for k in ("exportar", "exporta", "exporte", " a excel", " en excel", "descargar"))

            def _user_wants_report_md() -> bool:
                """True si el usuario pidió reporte/informe en MD (un solo archivo con insights e imágenes)."""
                t = (text or "").lower()
                return any(
                    k in t
                    for k in (
                        "reporte", "informe", "resumen ejecutivo", "logros", "estrategias",
                        "mejoras futuras", " md ", "markdown", " en md", "un md", "un markdown",
                    )
                )

            excel_only = _user_wants_excel_only()
            report_md_only = _user_wants_report_md() and markdown_paths and image_paths
            if excel_only and (image_paths or markdown_paths):
                _log("📎 Usuario pidió Excel: enviando solo archivo Excel (sin imagen ni MD)")
            if report_md_only:
                _log("📄 Reporte MD: enviando solo archivo .md con insights (sin imágenes)")
            async def _send():
                try:
                    # Reporte MD: un solo archivo .md con insights (sin imágenes)
                    if report_md_only:
                        md_path = Path(markdown_paths[0]).resolve()
                        if md_path.is_file():
                            md_content = md_path.read_text(encoding="utf-8")
                            # Quitar sección Gráficas
                            md_content = re.sub(r"\n## Gráficas\n[\s\S]*?(?=\n## |\Z)", "\n", md_content, flags=re.IGNORECASE)
                            doc_bytes = md_content.encode("utf-8")
                            caption = "📊 Reporte: insights incluidos."
                            await message.reply_document(
                                document=doc_bytes,
                                filename=md_path.name,
                                caption=caption,
                                parse_mode="HTML",
                            )
                            _persist_conversation(self.db, chat_id, "assistant", reply or "")
                            return
                    # Si pidió explícitamente Excel: solo enviar Excel, no MD ni imágenes
                    if excel_only and excel_paths:
                        doc_paths = excel_paths
                        send_images = False
                    else:
                        # Reportes MD: priorizar. Si solo Excel, enviar Excel.
                        doc_paths = markdown_paths if markdown_paths else excel_paths
                        send_images = True
                    if doc_paths:
                        caption = _format_reply_for_telegram(reply_for_user, max_len=900) or "📎 Archivo generado"
                        if len(caption) > 1024:
                            caption = _truncate_at_break(caption, 900)
                        for doc_path in doc_paths:
                            with open(doc_path, "rb") as f:
                                doc_bytes = f.read()
                            await message.reply_document(
                                document=doc_bytes,
                                filename=Path(doc_path).name,
                                caption=caption if doc_path == doc_paths[0] else None,
                                parse_mode="HTML",
                            )
                    if send_images and image_paths and not report_md_only:
                        # Solo insights, sin aviso de guardado ni rutas
                        try:
                            caption_raw = _caption_for_photo(reply, image_paths)
                            caption = _format_reply_for_telegram(caption_raw) if caption_raw else "📊 Gráfica generada"
                        except Exception:
                            caption = "📊 Gráfica generada"
                        if len(caption) > 1024:
                            caption = _truncate_at_break(caption, 900)
                        if len(image_paths) == 1:
                            with open(image_paths[0], "rb") as f:
                                photo_bytes = f.read()
                            try:
                                await message.reply_photo(
                                    photo=photo_bytes,
                                    caption=caption or "📊 Gráfica generada",
                                    parse_mode="HTML",
                                )
                            except Exception:
                                # Fallback: caption HTML puede causar rechazo; enviar sin caption
                                await message.reply_photo(
                                    photo=photo_bytes,
                                    caption="📊 Gráfica generada",
                                )
                        else:
                            from telegram import InputMediaPhoto
                            files = [open(p, "rb") for p in image_paths]
                            try:
                                # caption y parse_mode deben ir en el constructor (no se pueden asignar después)
                                media = [
                                    InputMediaPhoto(
                                        media=files[0],
                                        caption=caption or "📊 Gráficas generadas",
                                        parse_mode="HTML",
                                    )
                                ]
                                media += [InputMediaPhoto(media=f) for f in files[1:]]
                                await message.reply_media_group(media=media)
                            finally:
                                for f in files:
                                    f.close()
                    if not doc_paths and not image_paths:
                        await message.reply_text(text_to_send, parse_mode="HTML")
                    _persist_conversation(self.db, chat_id, "assistant", reply or "")
                except Exception as send_err:
                    _log(f"🖼️ Error enviando foto: {send_err}")
                    try:
                        await message.reply_text(text_to_send or "Sin respuesta.", parse_mode="HTML")
                        _persist_conversation(self.db, chat_id, "assistant", reply or "")
                    except Exception:
                        pass
            asyncio.create_task(_send())

        def _handle_setup(self, message: Any, text: str, chat_id: Any) -> None:
            # /setup framework=openai
            # /setup system_prompt=Eres un experto en SQL.
            parts = text.split(maxsplit=1)
            body = (parts[1] if len(parts) > 1 else "").strip()
            if not body:
                config = _get_config(self.db)
                save_tr = config.get("save_grpo_traces", False)
                if isinstance(save_tr, str):
                    save_tr = str(save_tr).lower() in ("true", "1", "yes", "y", "sí", "si")
                send_ls = config.get("send_to_langsmith", False)
                if isinstance(send_ls, str):
                    send_ls = str(send_ls).lower() in ("true", "1", "yes", "y", "sí", "si")
                asyncio.create_task(
                    message.reply_text(
                        f"Config actual:\nframework={config.get('framework', _DEFAULT_FRAMEWORK)}\n"
                        f"llm_provider={config.get('llm_provider', '')}\n"
                        f"llm_model={config.get('llm_model', '')}\n"
                        f"save_grpo_traces={save_tr}\nsend_to_langsmith={send_ls}\n"
                        f"system_prompt={config.get('system_prompt', '')[:150]}...\n\n"
                        "Para cambiar: /setup llm_provider=openai | save_grpo_traces=true | send_to_langsmith=true"
                    )
                )
                return
            if "=" in body:
                key, _, value = body.partition("=")
                key = key.strip().lower()
                value = value.strip()
                allowed = ("framework", "system_prompt", "llm_provider", "llm_model", "llm_base_url", "save_grpo_traces", "send_to_langsmith")
                if key in allowed:
                    _set_config(self.db, key, value)
                    asyncio.create_task(message.reply_text(f"Config actualizado: {key}={value[:80]}..."))
                else:
                    asyncio.create_task(message.reply_text(f"Claves permitidas: {', '.join(allowed)}"))
            else:
                asyncio.create_task(message.reply_text("Uso: /setup framework=openai o /setup system_prompt=..."))

        def _get_history(self, chat_id: Any, limit: int = 10) -> list:
            """Historial de conversación (user + assistant) para contexto multi-turno."""
            import json
            try:
                r = self.db.query(
                    f"SELECT role, content FROM telegram_conversation WHERE chat_id = {int(chat_id)} "
                    f"ORDER BY received_at DESC LIMIT {(limit * 2) + 1}"
                )
                rows = json.loads(r) if isinstance(r, str) else []
                out = []
                for row in reversed((rows or [])):
                    role = (row.get("role") or "user").lower()
                    content = (row.get("content") or "").strip()
                    if content and (role != "user" or not content.startswith("/")):
                        out.append({"role": role, "content": content})
                return out[-(limit * 2) :]  # últimos N turnos (user+assistant)
            except Exception:
                return []

    bot = DynamicAgentBot(db=db)
    app = bot.build_application(token)

    from telegram import error as tg_error

    def _error_handler(update: Any, context: Any) -> None:
        err = getattr(context, "error", None)
        if isinstance(err, tg_error.Conflict):
            _log(
                "Conflict: otra instancia del bot está usando el mismo token (p. ej. con PM2). "
                "Detén la otra instancia o no arranques este proceso. Salida con código 0 para evitar reinicio en bucle."
            )
            raise SystemExit(0)
        if err:
            raise err

    app.add_error_handler(_error_handler)
    _log("Bot dinámico DuckClaw agents. Comando /setup para cambiar framework y system_prompt en caliente.")
    _log(f"DB: {db_path}")
    _log("🎧 Escuchando mensajes en Telegram... (Ctrl+C para salir)")
    app.run_polling()


if __name__ == "__main__":
    # Python 3.10+: el main thread ya no tiene event loop por defecto; run_polling() lo necesita
    import asyncio
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    _run_bot()
