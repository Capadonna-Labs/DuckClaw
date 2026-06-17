"""
Configuración agent_config y ensamblado Forge para long polling.

Egress genérico (HTML, artefactos, normalización): ``duckclaw.integrations.telegram.telegram_reply_egress``.
Entry point: ``duckclaw.graphs.telegram_bot``.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Optional

_AGENT_CONFIG_TABLE = "agent_config"
DEFAULT_FRAMEWORK = "langgraph"
DEFAULT_SYSTEM_PROMPT = (
    "Eres un asistente DuckClaw con acceso a DuckDB (SQL, PGQ, VSS). "
    "Responde de forma breve y clara; prioriza datos de la base antes de suposiciones."
)


def persist_conversation(db: Any, chat_id: Any, role: str, content: str) -> None:
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


def get_db_path() -> str:
    from duckclaw.gateway_db import get_gateway_db_path

    path = (get_gateway_db_path() or "").strip()
    if path:
        return str(Path(path).resolve())
    return str(Path.cwd() / "duckclaw_agents.duckdb")


def _worker_db_path() -> str:
    env_path = os.environ.get("DUCKCLAW_WORKERS_DB_PATH", "").strip()
    if env_path:
        return str(Path(env_path).resolve())
    return get_db_path()


def _load_wizard_config() -> dict:
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
    try:
        r = db.query(f"SELECT key, value FROM {_AGENT_CONFIG_TABLE}")
        rows = json.loads(r) if isinstance(r, str) else r
        keys_present = {row.get("key") for row in (rows or []) if isinstance(row, dict)}
        defaults = [("framework", DEFAULT_FRAMEWORK), ("system_prompt", DEFAULT_SYSTEM_PROMPT)]
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


def get_config(db: Any) -> dict:
    _ensure_agent_config(db)
    r = db.query(f"SELECT key, value FROM {_AGENT_CONFIG_TABLE}")
    rows = json.loads(r) if isinstance(r, str) else r
    out = {}
    for row in (rows or []):
        if isinstance(row, dict):
            out[row.get("key", "")] = row.get("value", "")
    wizard = _load_wizard_config()
    for key in ("llm_provider", "llm_model", "llm_base_url"):
        if not out.get(key) and wizard.get(key):
            out[key] = str(wizard[key])
    for key in ("save_grpo_traces", "send_to_langsmith"):
        if key not in out or out.get(key) == "":
            wv = wizard.get(key)
            if wv is not None:
                out[key] = bool(wv) if isinstance(wv, bool) else str(wv).lower() in ("true", "1", "yes", "y", "sí", "si")
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


def set_config(db: Any, key: str, value: str) -> None:
    _ensure_agent_config(db)
    k = str(key).replace("'", "''")[:128]
    v = str(value).replace("'", "''")[:16384]
    db.execute(
        f"""
        INSERT INTO {_AGENT_CONFIG_TABLE} (key, value) VALUES ('{k}', '{v}')
        ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = now()
        """
    )


def get_store_db(config: dict) -> Any:
    """Deprecated — store_db_path ya no se usa en el core genérico."""
    _ = config
    return None


def build_graph_via_forge(
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
    """Ensambla LangGraph vía AgentAssembler (forge). Requiere LLM válido salvo worker none_llm."""
    from duckclaw.forge import AgentAssembler, ENTRY_ROUTER_YAML, WORKERS_TEMPLATES_DIR
    from duckclaw.integrations.llm_providers import build_llm

    provider = (llm_provider or "").strip().lower() or "none_llm"
    llm = build_llm(provider, (llm_model or "").strip(), (llm_base_url or "").strip())
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
