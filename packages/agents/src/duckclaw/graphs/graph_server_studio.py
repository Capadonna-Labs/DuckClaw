"""Grafo manager en :memory: para LangGraph Studio y GET /graph."""

from __future__ import annotations

import logging as _logging
from typing import Any, Optional

from duckclaw.graphs.graph_server_llm_config import _ensure_llm_config, get_graph_state

_graph_init_error: Optional[Exception] = None


def _build_manager_graph_for_db(
    db: Any,
    *,
    llm_override: Any | None = None,
    llm_provider_override: str | None = None,
    llm_model_override: str | None = None,
    llm_base_url_override: str | None = None,
) -> Any:
    """Compila el grafo manager con la conexión ``db`` del turno (o :memory: para Studio)."""
    from duckclaw.forge import AgentAssembler, MANAGER_ROUTER_YAML

    _ensure_llm_config()
    graph_state = get_graph_state()
    llm = graph_state["llm"] if llm_override is None else llm_override
    provider = graph_state["provider"] if llm_provider_override is None else llm_provider_override
    model = graph_state["model"] if llm_model_override is None else llm_model_override
    base_url = graph_state["base_url"] if llm_base_url_override is None else llm_base_url_override
    db_path = graph_state["db_path"]
    system_prompt = graph_state["system_prompt"]

    # :memory: exige read_only=False en DuckDB; no advertir por ello.
    _dp = (getattr(db, "_path", None) or "").strip()
    if (
        db is not None
        and _dp
        and _dp != ":memory:"
        and not getattr(db, "_read_only", False)
    ):
        from duckclaw.spawn_profile import is_spawn_profile

        if not is_spawn_profile():
            _logging.getLogger(__name__).warning(
                "graph_server: DuckClaw no está en read_only; revisar core y ruta gateway (multiplex)"
            )

    return AgentAssembler.from_yaml(MANAGER_ROUTER_YAML).build(
        db=db,
        llm=llm,
        system_prompt=system_prompt,
        llm_provider=provider,
        llm_model=model,
        llm_base_url=base_url,
        db_path=db_path,
    )


def _ensure_studio_graph() -> Any:
    """Grafo compilado contra :memory: para langgraph dev / GET /graph (sin lock al vault)."""
    graph_state = get_graph_state()
    if graph_state.get("studio_graph") is not None:
        return graph_state["studio_graph"]

    from duckclaw import DuckClaw

    # DuckDB: «Cannot launch in-memory database in read-only mode»
    mem = DuckClaw(":memory:", read_only=False)
    graph_state["studio_db"] = mem
    graph_state["studio_graph"] = _build_manager_graph_for_db(mem)
    return graph_state["studio_graph"]


def get_graph() -> Any:
    """
    Entry point para langgraph dev / LangSmith Studio.
    Usa DuckDB :memory: para no mantener lock sobre el archivo del gateway.
    """
    graph_state = get_graph_state()
    if _graph_init_error is not None and graph_state.get("llm") is None:
        raise _graph_init_error
    try:
        return _ensure_studio_graph()
    except Exception as exc:
        if _graph_init_error is not None:
            raise _graph_init_error from exc
        raise


def _get_or_build_graph() -> Any:
    """Compatibilidad: mismo grafo que LangGraph Studio (:memory:), no el del archivo del gateway."""
    return _ensure_studio_graph()


def _pre_init() -> None:
    global _graph_init_error
    try:
        _ensure_llm_config()
        _ensure_studio_graph()
    except Exception as exc:
        _graph_init_error = exc
        print(f"[graph_server] Pre-init warning: {exc}", flush=True)


_pre_init()
