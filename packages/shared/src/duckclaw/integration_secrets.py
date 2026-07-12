"""DB-first resolution for integration API keys.

Catalog source: ``seeds/framework_integration_secrets_v1.json`` via ``integration_catalog``.
"""

from __future__ import annotations

import os
from typing import Any, Sequence

from duckclaw.integration_catalog import (
    IntegrationCatalogEntry,
    get_integration_catalog_entry,
    integration_entry_for_setting_key,
    list_integration_catalog_entries,
)

# Back-compat alias for tests and older imports.
IntegrationSecretSpec = IntegrationCatalogEntry


def list_integration_secret_specs() -> tuple[IntegrationCatalogEntry, ...]:
    return list_integration_catalog_entries()


def get_integration_secret_spec(integration_id: str) -> IntegrationCatalogEntry | None:
    return get_integration_catalog_entry(integration_id)


def integration_spec_for_setting_key(setting_key: str) -> IntegrationCatalogEntry | None:
    return integration_entry_for_setting_key(setting_key)


def _env_candidates(token_env: str | None, env_keys: Sequence[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    if (token_env or "").strip():
        ordered.append(token_env.strip())
    for key in env_keys:
        if key not in ordered:
            ordered.append(key)
    return tuple(ordered)


def _resolve_from_env(candidates: Sequence[str]) -> str:
    for key in candidates:
        val = (os.environ.get(key) or "").strip()
        if val:
            return val
    return ""


def _resolve_from_db(
    db: Any,
    *,
    spec: IntegrationCatalogEntry,
    tenant_id: str,
    actor_email: str,
) -> str:
    from duckclaw.admin_runtime_settings import (
        _candidate_rows,
        _row_value,
        _scope_rank,
        normalize_runtime_setting_name,
    )

    dom = normalize_runtime_setting_name(spec.domain)
    setting_key = normalize_runtime_setting_name(spec.setting_key)
    candidates = sorted(
        _candidate_rows(
            db,
            tenant_id=tenant_id,
            actor_email=actor_email,
            domain=dom,
            key=setting_key,
        ),
        key=lambda row: _scope_rank(row, tenant_id=tenant_id, actor_email=actor_email),
    )
    if not candidates:
        return ""
    return str(_row_value(candidates[0]) or "").strip()


def resolve_integration_api_key(
    integration_id: str,
    *,
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
    token_env: str | None = None,
) -> str:
    """Return API key/plain secret without logging it."""
    spec = get_integration_catalog_entry(integration_id)
    if spec is None:
        return _resolve_from_env(_env_candidates(token_env, ()))
    candidates = _env_candidates(token_env, spec.env_keys)
    if db is not None:
        db_val = _resolve_from_db(db, spec=spec, tenant_id=tenant_id, actor_email=actor_email)
        if db_val:
            return db_val
    return _resolve_from_env(candidates)


def integration_api_key_configured(
    integration_id: str,
    *,
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
    token_env: str | None = None,
) -> bool:
    return bool(
        resolve_integration_api_key(
            integration_id,
            db=db,
            tenant_id=tenant_id,
            actor_email=actor_email,
            token_env=token_env,
        )
    )
