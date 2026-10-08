"""Per-worker LLM model (DB-first, ``admin_runtime_settings`` domain ``worker_llm``).

A worker with a model set here runs on it in every chat of the tenant; workers without one
inherit the chat's model. The model is an OpenRouter id, so it is portable across chats
whatever provider the chat itself uses.
"""

from __future__ import annotations

from typing import Any

from duckclaw.admin_runtime_settings import normalize_runtime_setting_name
from duckclaw.shared_db_grants import _query_all_dicts, _sql_lit

WORKER_LLM_DOMAIN = "worker_llm"
WORKER_LLM_PROVIDER = "openrouter"
WORKER_LLM_BASE_URL = "https://openrouter.ai/api/v1"


def worker_llm_key(worker_id: str) -> str:
    return normalize_runtime_setting_name(worker_id)


def list_worker_llm_models(db: Any, *, tenant_id: str) -> dict[str, str]:
    """``{worker_key: model}`` for the tenant (tenant rows win over ``global``); empty = inherit."""
    tenant = _sql_lit((tenant_id or "global").strip() or "global", 128)
    try:
        rows = _query_all_dicts(
            db,
            "SELECT tenant_id, key, value_text FROM main.admin_runtime_settings "
            f"WHERE active = true AND domain = '{WORKER_LLM_DOMAIN}' AND actor_email = '' "
            f"AND tenant_id IN ('{tenant}', 'global')",
        )
    except Exception:
        return {}
    out: dict[str, str] = {}
    for row in sorted(rows, key=lambda r: str(r.get("tenant_id")) != "global"):  # tenant last = wins
        out[str(row.get("key") or "")] = str(row.get("value_text") or "").strip()
    return {k: v for k, v in out.items() if k and v}


def worker_llm_model(db: Any, *, tenant_id: str, worker_id: str) -> str:
    """Model set for ``worker_id`` in this tenant, or ``""`` to inherit the chat's model."""
    if db is None or not (worker_id or "").strip():
        return ""
    try:
        return list_worker_llm_models(db, tenant_id=tenant_id).get(worker_llm_key(worker_id), "")
    except ValueError:
        return ""


def apply_worker_llm_override(
    db: Any,
    *,
    tenant_id: str,
    worker_id: str,
    llm: Any,
    llm_provider: str,
    llm_model: str,
    llm_base_url: str,
) -> tuple[Any, str, str, str]:
    """(llm, provider, model, base_url) for building ``worker_id``'s graph.

    With a per-worker model the chat's prebuilt ``llm`` is dropped (``None``) so the worker
    factory builds one from the returned triplet; the triplet also feeds the graph cache key.
    """
    model = worker_llm_model(db, tenant_id=tenant_id, worker_id=worker_id)
    if not model or (model == (llm_model or "").strip() and (llm_provider or "") == WORKER_LLM_PROVIDER):
        return llm, llm_provider, llm_model, llm_base_url
    return None, WORKER_LLM_PROVIDER, model, WORKER_LLM_BASE_URL
