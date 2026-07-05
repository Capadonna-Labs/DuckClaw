"""Apertura efímera DuckDB y resolución LLM por turno para ``graph_server``."""

from __future__ import annotations

import logging as _logging
import os
import time
from pathlib import Path
from typing import Any

_log = _logging.getLogger(__name__)


def is_duckdb_lock_error(exc: BaseException) -> bool:
    """
    Errores de contención al abrir el mismo archivo DuckDB (otro proceso, o RO+RW en el mismo PID).
    Incluye «different configuration» cuando ya hay una conexión RW y se pide RO.
    """
    msg = str(exc).lower()
    return (
        "lock" in msg
        or "conflicting" in msg
        or "different configuration" in msg
    )


def open_duckclaw_writable_with_retry(db_path: str) -> Any:
    """Abre DuckClaw RW al archivo con engine=python (evita mezclar C++ native + Python duckdb)."""
    from duckclaw import DuckClaw

    return DuckClaw(db_path, read_only=False, engine="python")


def open_duckclaw_readonly_with_retry(db_path: str) -> Any:
    """
    Abre DuckClaw RO al archivo; reintenta si el db-writer u otro proceso tiene el lock RW.
    Alineado con el backoff de ``context_injection_handler._connect_duckdb_writable``.
    """
    from duckclaw import DuckClaw

    raw_attempts = (os.environ.get("DUCKCLAW_GATEWAY_RO_LOCK_ATTEMPTS") or "24").strip()
    try:
        attempts = max(1, min(int(raw_attempts), 80))
    except ValueError:
        attempts = 24
    raw_sleep = (os.environ.get("DUCKCLAW_GATEWAY_RO_LOCK_BASE_SLEEP_S") or "0.15").strip()
    try:
        base_sleep_s = float(raw_sleep)
    except ValueError:
        base_sleep_s = 0.15
    base_sleep_s = max(0.05, base_sleep_s)

    last: BaseException | None = None
    for i in range(attempts):
        try:
            return DuckClaw(db_path, read_only=True)
        except Exception as exc:
            last = exc
            if is_duckdb_lock_error(exc):
                delay = base_sleep_s * min(i + 1, 12)
                _log.warning(
                    "graph_server: DuckDB RO lock intento %s/%s, reintento en %.2fs: %s",
                    i + 1,
                    attempts,
                    delay,
                    exc,
                )
                time.sleep(delay)
                continue
            raise
    assert last is not None
    raise last


def is_openrouter_chat_provider(provider: str) -> bool:
    return (provider or "").strip().lower() in ("openrouter", "or", "router")


def openrouter_gateway_config_error(exc: BaseException) -> RuntimeError:
    return RuntimeError(
        "OpenRouter no está configurado en el gateway: añade OPENROUTER_API_KEY "
        "al .env del repositorio y reinicia DuckClaw-Gateway "
        "(pm2 restart DuckClaw-Gateway --update-env)."
    )


def paths_same_canonical(a: str, b: str) -> bool:
    if not (a or "").strip() or not (b or "").strip():
        return False
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return (a or "").strip() == (b or "").strip()


def resolve_llm_triplet_for_graph_invoke(
    hub_db: Any,
    chat_id: str | None,
    vault_db_path: str | None,
    *,
    same_file: bool,
    log: Any | None = None,
) -> tuple[tuple[str, str, str] | None, str]:
    """
    Resuelve provider/model/base_url para un turno.

    Cuando hub y vault son archivos distintos, el override del **hub** gana (admin
    playground / PUT /playground/model escribe ahí). El vault solo se usa si el hub
    no tiene llm_* para ese chat_id.
    """
    from duckclaw.gateway_db import GatewayDbEphemeralReadonly
    from duckclaw.graphs.on_the_fly_commands import resolve_llm_triplet_for_chat_invocation

    cid = (chat_id or "").strip() or None
    hub_trip = resolve_llm_triplet_for_chat_invocation(hub_db, cid) if cid else None

    if same_file:
        source = "same_file_as_hub" if hub_trip else "same_file_no_chat_override"
        return hub_trip, source

    vault_trip: tuple[str, str, str] | None = None
    v_p = (vault_db_path or "").strip()
    if v_p and v_p != ":memory:":
        try:
            vault_trip = resolve_llm_triplet_for_chat_invocation(
                GatewayDbEphemeralReadonly(v_p), cid
            )
        except Exception as exc:
            if log is not None:
                log.warning(
                    "graph_server: resolve_llm_triplet vault read failed chat_id=%s vault_suffix=%s err=%s",
                    cid,
                    v_p[-96:] if len(v_p) > 96 else v_p,
                    exc,
                )

    if hub_trip:
        source = "hub_over_vault" if vault_trip else "hub_only"
        return hub_trip, source
    if vault_trip:
        return vault_trip, "vault_separate"
    return None, "env_defaults"


def invoke_ephemeral_gateway_graph(
    chat_id: str | None = None,
    vault_db_path: str | None = None,
) -> tuple[Any, Any]:
    """
    Abre DuckClaw RO al archivo del gateway, compila el manager y devuelve (graph, db).
    El caller debe ``db.close()`` y llamar ``clear_worker_graph_cache()`` en ``finally``.

    Si ``chat_id`` tiene llm_* en agent_config (p. ej. /model), el LLM del grafo sigue esa
    tripleta en lugar del cache global basado solo en env. Con ``vault_db_path`` distinto
    del hub, gana el override del hub (consola admin); el vault solo si el hub no tiene llm_*.
    """
    from duckclaw.integrations.llm_providers import build_llm
    from duckclaw.manager.graph import trim_worker_graph_cache

    from duckclaw.graphs.graph_server_llm_config import _ensure_llm_config, get_graph_state
    from duckclaw.graphs.graph_server_studio import _build_manager_graph_for_db

    _ensure_llm_config()
    graph_state = get_graph_state()
    db_path = str(graph_state["db_path"])
    os.makedirs(str(Path(db_path).parent), exist_ok=True)
    trim_worker_graph_cache()
    v_p = (vault_db_path or "").strip()
    from duckclaw.spawn_profile import spawn_inline_writes_enabled

    use_spawn_rw = spawn_inline_writes_enabled() and (
        not v_p or v_p == ":memory:" or paths_same_canonical(v_p, db_path)
    )
    if use_spawn_rw:
        db = open_duckclaw_writable_with_retry(db_path)
    else:
        db = open_duckclaw_readonly_with_retry(db_path)
    ovr: dict[str, Any] = {}
    trip: tuple[str, str, str] | None = None
    trip_source = "env_defaults"
    try:
        same_file = bool(v_p and v_p != ":memory:" and paths_same_canonical(v_p, db_path))
        trip, trip_source = resolve_llm_triplet_for_graph_invoke(
            db,
            chat_id,
            v_p or None,
            same_file=same_file,
            log=_log,
        )
        if trip is not None:
            tp, tm, tu = trip
            try:
                built = build_llm(tp, tm, tu, prefer_env_provider=False)
            except Exception as exc:
                _log.warning(
                    "graph_server: build_llm(chat triplet) failed provider=%s err=%s",
                    tp,
                    exc,
                    exc_info=True,
                )
                if is_openrouter_chat_provider(tp) and "OPENROUTER_API_KEY" in str(exc):
                    raise openrouter_gateway_config_error(exc) from exc
                built = None
            if built is not None:
                ovr = {
                    "llm_override": built,
                    "llm_provider_override": tp,
                    "llm_model_override": tm,
                    "llm_base_url_override": tu,
                }
            else:
                _log.warning(
                    "graph_server: build_llm returned None for chat triplet provider=%s model=%s",
                    tp,
                    (tm or "")[:80],
                )
        _invoke_provider = str(graph_state.get("provider") or "")
        if ovr.get("llm_provider_override"):
            _invoke_provider = str(ovr.get("llm_provider_override") or "")
        elif trip:
            _invoke_provider = str(trip[0] or "")
        _log.info(
            "graph_server: llm_invoke_override chat_id=%s trip_source=%s has_trip=%s ovr=%s global_provider=%s",
            chat_id,
            trip_source,
            trip is not None,
            bool(ovr),
            _invoke_provider,
        )
    except Exception as exc:
        _log.warning("graph_server: LLM override resolution failed: %s", exc, exc_info=True)
    graph = _build_manager_graph_for_db(db, **ovr)
    return graph, db
