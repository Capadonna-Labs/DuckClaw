"""DB-first prompt policy resolver with framework airbag (capa 0)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from duckclaw.prompt_policies.framework_fallbacks import (
    framework_fallback_content,
    is_framework_policy_key,
)

_log = logging.getLogger(__name__)


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
