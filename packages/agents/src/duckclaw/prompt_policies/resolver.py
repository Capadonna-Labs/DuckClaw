"""DB-first prompt policy resolver."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
    """Resolve prompt policies from ``main.prompt_policy_registry`` only."""

    db: Any | None = None

    def load(self, policy_type: str, policy_name: str) -> str:
        normalized_type = _normalize_policy_type(policy_type)
        name = (policy_name or "").strip()
        if not normalized_type or not name:
            raise FileNotFoundError("prompt policy requires type and name")

        content = self._load_from_db(normalized_type, name)
        if not content:
            raise RuntimeError(
                "active prompt policy has empty content in main.prompt_policy_registry: "
                f"{normalized_type}/{name}"
            )
        return content

    def format(self, policy_type: str, policy_name: str, **kwargs: str) -> str:
        return self.load(policy_type, policy_name).format(**kwargs)

    def _load_from_db(self, policy_type: str, policy_name: str) -> str:
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
            raise FileNotFoundError(
                "active prompt policy not found in main.prompt_policy_registry: "
                f"{policy_type}/{policy_name}"
            )
        if isinstance(row, dict):
            return str(row.get("content") or "").strip()
        return str(row[0] or "").strip()

    @staticmethod
    def _first_row(result: Any) -> Any | None:
        if hasattr(result, "fetchone"):
            return result.fetchone()
        if isinstance(result, list):
            return result[0] if result else None
        if isinstance(result, tuple):
            return result
        return None
