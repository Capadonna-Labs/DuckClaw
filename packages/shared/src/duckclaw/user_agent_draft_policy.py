"""Seed and refresh admin user-agent draft policy (LLM wizard templates)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

_SEED_PATH = Path(__file__).resolve().parent / "seeds" / "user_agent_draft_policy_v2.json"


def _load_seed() -> dict[str, Any]:
    raw = _SEED_PATH.read_text(encoding="utf-8")
    return json.loads(raw)


_MIN_SYSTEM_PROMPT_LEN = 80
_MIN_SOUL_LEN = 20
_WIZARD_QUESTION_BLOCKLIST = (
    "db",
    "vault",
    "sandbox",
    " sql",
    "rag",
    "duckdb",
    "prod/staging",
    "hitl",
)


def sanitize_wizard_questions(prompt: str, questions: Any) -> list[str]:
    """Drop jargon questions; skip entirely when the user already described the agent."""

    if len((prompt or "").strip()) >= 20:
        return []
    out: list[str] = []
    for raw in questions or []:
        question = str(raw or "").strip()
        if not question:
            continue
        lower = question.lower()
        if any(token in lower for token in _WIZARD_QUESTION_BLOCKLIST):
            continue
        out.append(question[:512])
        break
    return out


def coalesce_user_agent_draft(
    draft: dict[str, Any],
    fallback: dict[str, Any],
    *,
    normalize_tool_profile: Any,
    behavior_prompt: str = "",
) -> dict[str, Any]:
    """Fill missing or too-short generated fields from deterministic fallback templates."""

    merged = dict(draft)
    for key in ("description", "system_prompt", "soul"):
        value = str(merged.get(key) or "").strip()
        fallback_value = str(fallback.get(key) or "").strip()
        if not value and fallback_value:
            merged[key] = fallback_value
    system_prompt = str(merged.get("system_prompt") or "").strip()
    if len(system_prompt) < _MIN_SYSTEM_PROMPT_LEN:
        fallback_prompt = str(fallback.get("system_prompt") or "").strip()
        if len(fallback_prompt) >= _MIN_SYSTEM_PROMPT_LEN:
            merged["system_prompt"] = fallback_prompt
    soul = str(merged.get("soul") or "").strip()
    if len(soul) < _MIN_SOUL_LEN:
        fallback_soul = str(fallback.get("soul") or "").strip()
        if len(fallback_soul) >= _MIN_SOUL_LEN:
            merged["soul"] = fallback_soul
    if not str(merged.get("display_name") or "").strip():
        merged["display_name"] = fallback["display_name"]
    if not str(merged.get("worker_id") or "").strip():
        merged["worker_id"] = fallback["worker_id"]
    merged["tool_profile"] = normalize_tool_profile(str(merged.get("tool_profile") or "general"))
    merged["browser_sandbox"] = bool(merged.get("browser_sandbox"))
    merged["web_search"] = bool(merged.get("web_search"))
    merged["questions"] = sanitize_wizard_questions(behavior_prompt, merged.get("questions") or [])
    return merged


def apply_user_agent_draft_policy(db: Any, *, force: bool = False) -> bool:
    """
    Upsert ``manager_task/admin_user_agent_draft`` from the repo seed.

    Idempotent by checksum; ``force=True`` always writes a new active version.
    """
    seed = _load_seed()
    metadata = dict(seed.get("metadata") or {})
    policy_body = dict(seed.get("policy") or {})
    content = json.dumps(policy_body, ensure_ascii=False, sort_keys=True)
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    policy_type = str(metadata.get("policy_type") or "manager_task")
    policy_name = str(metadata.get("policy_name") or "admin_user_agent_draft")

    row = db.execute(
        """
        SELECT checksum
        FROM main.prompt_policy_registry
        WHERE policy_type = ?
          AND policy_name = ?
          AND active = true
          AND status = 'active'
        ORDER BY version DESC
        LIMIT 1
        """,
        [policy_type, policy_name],
    ).fetchone()
    existing_checksum = ""
    if row:
        existing_checksum = str(row[0] if not isinstance(row, dict) else row.get("checksum") or "")

    if not force and existing_checksum == checksum:
        return False

    version_row = db.execute(
        """
        SELECT COALESCE(MAX(version), 0)
        FROM main.prompt_policy_registry
        WHERE policy_type = ? AND policy_name = ?
        """,
        [policy_type, policy_name],
    ).fetchone()
    next_version = int(version_row[0] if version_row else 0) + 1
    policy_id = f"ppol_{policy_name}_v{next_version}"

    db.execute(
        """
        UPDATE main.prompt_policy_registry
        SET active = false, status = 'inactive', updated_at = CURRENT_TIMESTAMP
        WHERE policy_type = ? AND policy_name = ? AND active = true
        """,
        [policy_type, policy_name],
    )
    db.execute(
        """
        INSERT INTO main.prompt_policy_registry
          (policy_id, policy_type, policy_name, version, status, content, checksum, metadata_json, active)
        VALUES (?, ?, ?, ?, 'active', ?, ?, ?, true)
        """,
        [
            policy_id,
            policy_type,
            policy_name,
            next_version,
            content,
            checksum,
            json.dumps(metadata, ensure_ascii=False),
        ],
    )
    return True
