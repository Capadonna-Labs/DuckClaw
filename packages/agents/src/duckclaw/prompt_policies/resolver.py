"""DB-first prompt policy resolver with framework airbag (capa 0)."""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.prompt_policies.framework_fallbacks import (
    framework_fallback_content,
    is_framework_policy_key,
)

_log = logging.getLogger(__name__)


def _registry_readable(db: Any) -> bool:
    try:
        db.execute("SELECT 1 FROM main.prompt_policy_registry LIMIT 0")
    except Exception:
        return False
    return True


def _distinct_hub_path(vault_path: str) -> str:
    hub = (get_gateway_db_path() or "").strip()
    if not hub or not os.path.isfile(hub):
        return ""
    try:
        if Path(vault_path).resolve() == Path(hub).resolve():
            return ""
    except OSError:
        return ""
    return hub


class _EphemeralHubPolicyDb:
    """Lee el hub y cierra. Un RO persistente bloquea el lock de DB-Writer."""

    __slots__ = ("_path", "_read_only")

    def __init__(self, path: str) -> None:
        self._path = path
        self._read_only = True

    def execute(self, sql: str, params: Any = None) -> list[Any]:
        con = duckdb.connect(self._path, read_only=True)
        try:
            cursor = con.execute(sql, params) if params is not None else con.execute(sql)
            return cursor.fetchall()
        finally:
            con.close()


def prompt_policy_source_db(db: Any) -> Any:
    """Policies live on the hub. A playground vault does not have the registry."""
    vault_path = str(getattr(db, "_path", "") or "").strip()
    if db is None or not vault_path or vault_path == ":memory:":
        return db
    if _registry_readable(db):
        return db
    hub = _distinct_hub_path(vault_path)
    if not hub:
        return db
    _log.info("prompt policies: vault %s has no registry; using hub", vault_path)
    return _EphemeralHubPolicyDb(hub)


def normalize_policy_type(policy_type: str) -> str:
    value = (policy_type or "").strip().lower()
    aliases = {
        "capabilities": "capability",
        "directives": "directive",
        "manager_tasks": "manager_task",
        "system_prompts": "system_prompt",
    }
    return aliases.get(value, value)


_normalize_policy_type = normalize_policy_type


@dataclass(frozen=True)
class PromptPolicyResolver:
    """Resolve prompt policies: DB (capa 1/2) → framework airbag (capa 0) → worker inherit."""

    db: Any | None = None

    def load(self, policy_type: str, policy_name: str) -> str:
        normalized_type = _normalize_policy_type(policy_type)
        name = (policy_name or "").strip()
        if not normalized_type or not name:
            raise FileNotFoundError("prompt policy requires type and name")

        content = self._resolve(normalized_type, name)
        if not content:
            raise FileNotFoundError(
                "active prompt policy not found in main.prompt_policy_registry: "
                f"{normalized_type}/{name}"
            )
        return content

    def format(self, policy_type: str, policy_name: str, **kwargs: str) -> str:
        return self.load(policy_type, policy_name).format(**kwargs)

    def _resolve(self, policy_type: str, policy_name: str, *, _inherit_default: bool = True) -> str:
        content = self._try_load_from_db(policy_type, policy_name)
        if content:
            return content

        if is_framework_policy_key(policy_type, policy_name):
            fallback = framework_fallback_content(policy_type, policy_name)
            if fallback:
                _log.warning(
                    "degraded_framework_policy: using capa 0 fallback for %s/%s",
                    policy_type,
                    policy_name,
                )
                return fallback

        if (
            _inherit_default
            and policy_type == "system_prompt"
            and policy_name not in ("", "default")
        ):
            inherited = self._resolve("system_prompt", "default", _inherit_default=False)
            if inherited:
                _log.warning(
                    "inherited_system_prompt: %s inherits system_prompt/default",
                    policy_name,
                )
                return inherited

        return ""

    def _try_load_from_db(self, policy_type: str, policy_name: str) -> str:
        if self.db is None:
            raise RuntimeError(
                "PromptPolicyResolver requires a DuckDB connection; "
                "no Markdown or Python fallback is available"
            )
        try:
            result = self.db.execute(
                """
                SELECT content
                FROM main.prompt_policy_registry
                WHERE policy_type = ?
                  AND policy_name = ?
                  AND active = true
                  AND status = 'active'
                ORDER BY version DESC
                LIMIT 1
                """,
                [policy_type, policy_name],
            )
            row = self._first_row(result)
        except Exception as exc:
            # Tabla ausente / DB efímera: dejar que capa 0 (airbag) resuelva si aplica.
            if is_framework_policy_key(policy_type, policy_name):
                _log.warning(
                    "prompt_policy_registry unavailable for framework key %s/%s: %s",
                    policy_type,
                    policy_name,
                    exc,
                )
                return ""
            raise RuntimeError(
                "main.prompt_policy_registry is unavailable; run schema migration 16 "
                f"before resolving prompt policy {policy_type}/{policy_name}"
            ) from exc
        if not row:
            return ""
        if isinstance(row, dict):
            content = str(row.get("content") or "").strip()
        else:
            content = str(row[0] or "").strip()
        if not content:
            raise RuntimeError(
                "active prompt policy has empty content in main.prompt_policy_registry: "
                f"{policy_type}/{policy_name}"
            )
        return content

    @staticmethod
    def _first_row(result: Any) -> Any | None:
        if hasattr(result, "fetchone"):
            return result.fetchone()
        if isinstance(result, list):
            return result[0] if result else None
        if isinstance(result, tuple):
            return result
        return None
