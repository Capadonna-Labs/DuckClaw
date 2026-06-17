"""Framework policy pack v1 — JSON seed, DB apply, and lookup helpers."""

from __future__ import annotations

import hashlib
import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

PACK_FILENAME = "framework_policy_pack_v1.json"
PACK_SEED = "framework_policy_pack_v1"


def framework_policy_pack_path() -> Path:
    return Path(__file__).resolve().parent / "seeds" / PACK_FILENAME


@lru_cache(maxsize=1)
def load_framework_policy_pack() -> dict[str, Any]:
    path = framework_policy_pack_path()
    if not path.is_file():
        raise FileNotFoundError(f"framework policy pack not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("framework policy pack must be a JSON object")
    policies = data.get("policies")
    if not isinstance(policies, list) or not policies:
        raise ValueError("framework policy pack requires a non-empty policies list")
    return data


def framework_policy_keys() -> frozenset[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    for entry in load_framework_policy_pack()["policies"]:
        policy_type = str(entry.get("policy_type") or "").strip().lower()
        policy_name = str(entry.get("policy_name") or "").strip()
        if policy_type and policy_name:
            keys.add((policy_type, policy_name))
    return frozenset(keys)


def get_framework_policy_content(policy_type: str, policy_name: str) -> str | None:
    normalized_type = (policy_type or "").strip().lower()
    name = (policy_name or "").strip()
    for entry in load_framework_policy_pack()["policies"]:
        entry_type = str(entry.get("policy_type") or "").strip().lower()
        entry_name = str(entry.get("policy_name") or "").strip()
        if entry_type == normalized_type and entry_name == name:
            content = str(entry.get("content") or "").strip()
            return content or None
    return None


def _pack_metadata() -> dict[str, Any]:
    pack = load_framework_policy_pack()
    metadata = pack.get("metadata")
    if isinstance(metadata, dict):
        return {**metadata, "seed": PACK_SEED, "scope": "framework"}
    return {"seed": PACK_SEED, "scope": "framework", "editable": True}


def _next_policy_version(db: Any, policy_type: str, policy_name: str) -> int:
    row = db.execute(
        """
        SELECT COALESCE(MAX(version), 0)
        FROM main.prompt_policy_registry
        WHERE policy_type = ? AND policy_name = ?
        """,
        [policy_type, policy_name],
    ).fetchone()
    if not row:
        return 1
    return int(row[0]) + 1


def _active_policy_row(db: Any, policy_type: str, policy_name: str) -> tuple[str, str, int] | None:
    result = db.execute(
        """
        SELECT content, checksum, version
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
    if not result:
        return None
    if isinstance(result, dict):
        return (
            str(result.get("content") or ""),
            str(result.get("checksum") or ""),
            int(result.get("version") or 0),
        )
    return str(result[0] or ""), str(result[1] or ""), int(result[2] or 0)


def _deactivate_policy_versions(db: Any, policy_type: str, policy_name: str) -> None:
    db.execute(
        """
        UPDATE main.prompt_policy_registry
        SET active = false, status = 'inactive', updated_at = CURRENT_TIMESTAMP
        WHERE policy_type = ? AND policy_name = ? AND active = true
        """,
        [policy_type, policy_name],
    )


def apply_framework_policy_pack(db: Any, *, force: bool = False) -> list[str]:
    """Upsert framework policies from the versioned JSON pack. Returns keys applied."""

    from duckclaw.write_handlers.prompt_policies import _apply_upsert_prompt_policy

    metadata = _pack_metadata()
    applied: list[str] = []

    for entry in load_framework_policy_pack()["policies"]:
        policy_type = str(entry.get("policy_type") or "").strip().lower()
        policy_name = str(entry.get("policy_name") or "").strip()
        content = str(entry.get("content") or "").strip()
        if not policy_type or not policy_name or not content:
            raise ValueError("each pack policy requires policy_type, policy_name, and content")

        checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
        active = _active_policy_row(db, policy_type, policy_name)
        if active and not force:
            _active_content, active_checksum, active_version = active
            if active_checksum == checksum:
                row = db.execute(
                    """
                    SELECT metadata_json
                    FROM main.prompt_policy_registry
                    WHERE policy_type = ? AND policy_name = ? AND version = ?
                    """,
                    [policy_type, policy_name, active_version],
                ).fetchone()
                raw_meta = ""
                if isinstance(row, dict):
                    raw_meta = str(row.get("metadata_json") or "")
                elif row:
                    raw_meta = str(row[0] or "")
                if PACK_SEED in raw_meta:
                    continue

        version = _next_policy_version(db, policy_type, policy_name)
        _deactivate_policy_versions(db, policy_type, policy_name)
        _apply_upsert_prompt_policy(
            db,
            {
                "policy_type": policy_type,
                "policy_name": policy_name,
                "version": version,
                "status": "active",
                "content": content,
                "metadata": metadata,
            },
        )
        key = f"{policy_type}/{policy_name}"
        applied.append(key)
        _log.info("framework policy pack applied: %s v%s", key, version)

    return applied
