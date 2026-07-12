"""Canonical integration secrets catalog (seed pack → API → runtime)."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

IntegrationScope = Literal["tenant", "global", "actor"]

PACK_FILENAME = "framework_integration_secrets_v1.json"
PACK_SEED = "framework_integration_secrets_v1"
_SETTING_KEY_RE = re.compile(r"^[a-z0-9_]+\.(api_key|token|secret)$")


@dataclass(frozen=True)
class IntegrationCatalogEntry:
    integration_id: str
    setting_key: str
    label: str
    description: str
    env_keys: tuple[str, ...]
    related_skills: tuple[str, ...]
    docs_url: str
    default_scope: IntegrationScope
    group_id: str
    group_title: str
    group_description: str
    group_sort_order: int

    @property
    def domain(self) -> str:
        return "integrations"


def bundled_integration_secrets_pack_path() -> Path:
    return Path(__file__).resolve().parent / "seeds" / PACK_FILENAME


def resolve_integration_secrets_pack_path() -> Path:
    """Pack resolution (same precedence idea as MCP presets).

    1. ``DUCKCLAW_INTEGRATION_SECRETS_PACK_PATH`` — explicit override (fork / extensión)
    2. ``{DUCKCLAW_REPO_ROOT}/config/integration_secrets_pack.json`` — monorepo local
    3. Bundled ``framework_integration_secrets_v1.json`` in duckclaw-shared
    """
    override = (os.environ.get("DUCKCLAW_INTEGRATION_SECRETS_PACK_PATH") or "").strip()
    if override:
        return Path(override).expanduser().resolve()
    repo_root = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    if repo_root:
        candidate = Path(repo_root).expanduser().resolve() / "config" / "integration_secrets_pack.json"
        if candidate.is_file():
            return candidate
    return bundled_integration_secrets_pack_path()


def validate_integration_secrets_pack(data: dict[str, Any]) -> None:
    if not isinstance(data, dict):
        raise ValueError("integration secrets pack must be a JSON object")
    groups = data.get("groups")
    if not isinstance(groups, list) or not groups:
        raise ValueError("integration secrets pack requires non-empty groups")
    seen_ids: set[str] = set()
    seen_keys: set[str] = set()
    for group in groups:
        if not isinstance(group, dict):
            raise ValueError("each group must be an object")
        integrations = group.get("integrations") or []
        if not isinstance(integrations, list):
            raise ValueError("group.integrations must be an array")
        for raw in integrations:
            if not isinstance(raw, dict):
                raise ValueError("each integration must be an object")
            integration_id = (str(raw.get("id") or "").strip().lower().replace("-", "_"))
            setting_key = str(raw.get("setting_key") or "").strip().lower()
            if not integration_id:
                raise ValueError("integration.id is required")
            if not setting_key:
                raise ValueError(f"integration {integration_id}: setting_key is required")
            if not _SETTING_KEY_RE.match(setting_key):
                raise ValueError(
                    f"integration {integration_id}: setting_key must look like "
                    "'vendor.api_key' or 'vendor.token'"
                )
            if integration_id in seen_ids:
                raise ValueError(f"duplicate integration id: {integration_id}")
            if setting_key in seen_keys:
                raise ValueError(f"duplicate setting_key: {setting_key}")
            seen_ids.add(integration_id)
            seen_keys.add(setting_key)
            scope = str(raw.get("default_scope") or "tenant").strip().lower()
            if scope not in {"tenant", "global", "actor"}:
                raise ValueError(f"integration {integration_id}: invalid default_scope {scope}")


def clear_integration_catalog_cache() -> None:
    load_integration_secrets_pack.cache_clear()
    list_integration_catalog_entries.cache_clear()
    integration_catalog_by_id.cache_clear()
    from duckclaw.integration_gaps import clear_integration_gaps_cache

    clear_integration_gaps_cache()


@lru_cache(maxsize=1)
def load_integration_secrets_pack() -> dict[str, Any]:
    path = resolve_integration_secrets_pack_path()
    if not path.is_file():
        raise FileNotFoundError(f"integration secrets pack not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    validate_integration_secrets_pack(data)
    return data


def _normalize_integration_id(value: str) -> str:
    return (value or "").strip().lower().replace("-", "_")


@lru_cache(maxsize=1)
def list_integration_catalog_entries() -> tuple[IntegrationCatalogEntry, ...]:
    pack = load_integration_secrets_pack()
    out: list[IntegrationCatalogEntry] = []
    for group in pack.get("groups") or []:
        if not isinstance(group, dict):
            continue
        group_id = str(group.get("id") or "").strip()
        group_title = str(group.get("title") or group_id).strip()
        group_description = str(group.get("description") or "").strip()
        try:
            group_sort = int(group.get("sort_order") or 0)
        except (TypeError, ValueError):
            group_sort = 0
        integrations = group.get("integrations") or []
        if not isinstance(integrations, list):
            continue
        for raw in integrations:
            if not isinstance(raw, dict):
                continue
            integration_id = _normalize_integration_id(str(raw.get("id") or ""))
            setting_key = str(raw.get("setting_key") or "").strip().lower()
            if not integration_id or not setting_key:
                continue
            env_keys = tuple(
                str(item).strip()
                for item in (raw.get("env_keys") or [])
                if str(item).strip()
            )
            related = tuple(
                _normalize_integration_id(str(item))
                for item in (raw.get("related_skills") or [])
                if str(item).strip()
            )
            scope = str(raw.get("default_scope") or "tenant").strip().lower()
            if scope not in {"tenant", "global", "actor"}:
                scope = "tenant"
            out.append(
                IntegrationCatalogEntry(
                    integration_id=integration_id,
                    setting_key=setting_key,
                    label=str(raw.get("label") or integration_id).strip(),
                    description=str(raw.get("description") or "").strip(),
                    env_keys=env_keys,
                    related_skills=related,
                    docs_url=str(raw.get("docs_url") or "").strip(),
                    default_scope=scope,  # type: ignore[arg-type]
                    group_id=group_id,
                    group_title=group_title,
                    group_description=group_description,
                    group_sort_order=group_sort,
                )
            )
    return tuple(out)


@lru_cache(maxsize=1)
def integration_catalog_by_id() -> dict[str, IntegrationCatalogEntry]:
    return {entry.integration_id: entry for entry in list_integration_catalog_entries()}


def get_integration_catalog_entry(integration_id: str) -> IntegrationCatalogEntry | None:
    return integration_catalog_by_id().get(_normalize_integration_id(integration_id))


def integration_entry_for_setting_key(setting_key: str) -> IntegrationCatalogEntry | None:
    normalized = (setting_key or "").strip().lower()
    for entry in list_integration_catalog_entries():
        if entry.setting_key == normalized:
            return entry
    return None


def integration_setting_fallbacks() -> dict[tuple[str, str], dict[str, Any]]:
    """Runtime settings fallbacks derived from the seed pack."""
    out: dict[tuple[str, str], dict[str, Any]] = {}
    for entry in list_integration_catalog_entries():
        env_key = entry.env_keys[0] if entry.env_keys else ""
        out[(entry.domain, entry.setting_key)] = {
            "env_key": env_key,
            "default": "",
            "secret": True,
        }
    return out


def _env_fallback_label(env_keys: tuple[str, ...]) -> str:
    if not env_keys:
        return "—"
    if len(env_keys) == 1:
        return env_keys[0]
    return " / ".join(env_keys)


def integration_catalog_api_payload(
    db: Any,
    *,
    tenant_id: str,
    actor_email: str,
) -> dict[str, Any]:
    from duckclaw.integration_secrets import integration_api_key_configured

    groups_map: dict[str, dict[str, Any]] = {}
    for entry in list_integration_catalog_entries():
        configured = integration_api_key_configured(
            entry.integration_id,
            db=db,
            tenant_id=tenant_id,
            actor_email=actor_email,
        )
        from duckclaw.admin_runtime_settings import resolve_runtime_setting

        status = resolve_runtime_setting(
            db,
            tenant_id=tenant_id,
            actor_email=actor_email,
            domain=entry.domain,
            key=entry.setting_key,
        )
        item = {
            "id": entry.integration_id,
            "setting_key": entry.setting_key,
            "domain": entry.domain,
            "label": entry.label,
            "description": entry.description,
            "env_fallback": _env_fallback_label(entry.env_keys),
            "env_keys": list(entry.env_keys),
            "related_skills": list(entry.related_skills),
            "docs_url": entry.docs_url or None,
            "default_scope": entry.default_scope,
            "configured": configured,
            "source": str(status.get("source") or "default"),
        }
        group = groups_map.get(entry.group_id)
        if group is None:
            group = {
                "id": entry.group_id,
                "title": entry.group_title,
                "description": entry.group_description,
                "sort_order": entry.group_sort_order,
                "integrations": [],
            }
            groups_map[entry.group_id] = group
        group["integrations"].append(item)

    groups = sorted(groups_map.values(), key=lambda row: (int(row.get("sort_order") or 0), str(row.get("id") or "")))
    integrations = [item for group in groups for item in group["integrations"]]
    pack_path = resolve_integration_secrets_pack_path()
    return {
        "pack_version": load_integration_secrets_pack().get("pack_version") or PACK_SEED,
        "pack_source": str(pack_path),
        "tenant_id": tenant_id,
        "actor_email": actor_email,
        "groups": groups,
        "integrations": integrations,
    }