"""Load/save per-tenant homeostasis manifest from harness_core.homeostasis_targets."""

from __future__ import annotations

import json
import logging
from typing import Any

from harness_core.skills.emit_correction_delta import push_meditate_state_delta_sync
from harness_core.states.meditate_state import DomainGoal, HomeostasisManifest, HomeostasisTarget

_log = logging.getLogger(__name__)

_INFRA_KEYS = frozenset(HomeostasisTarget.model_fields.keys())


def _parse_targets_json(raw: Any) -> HomeostasisManifest:
    """Parse DB targets_json; legacy flat infra JSON → manifest wrapper."""
    if raw is None:
        return HomeostasisManifest()
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return HomeostasisManifest()
    if not isinstance(raw, dict):
        return HomeostasisManifest()
    if "infra" in raw or "goals" in raw:
        try:
            return HomeostasisManifest.model_validate(raw)
        except Exception:
            pass
    # Legacy: flat HomeostasisTarget fields at root
    try:
        infra = HomeostasisTarget.model_validate(raw)
        return HomeostasisManifest(infra=infra, goals=[])
    except Exception:
        return HomeostasisManifest()


def _query_manifest_row(db: Any, tenant_id: str) -> HomeostasisManifest:
    tid = (tenant_id or "default").strip() or "default"
    try:
        esc = tid.replace("'", "''")
        raw = db.query(
            f"SELECT targets_json FROM harness_core.homeostasis_targets "
            f"WHERE tenant_id = '{esc}' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            return _parse_targets_json(rows[0].get("targets_json"))
    except Exception as exc:
        _log.debug("load_homeostasis_manifest query failed tenant=%s: %s", tid, exc)
    return HomeostasisManifest()


def _legacy_goals_from_chat(db: Any, chat_id: Any) -> list[DomainGoal]:
    try:
        from duckclaw.commands.goals import get_manager_goals

        raw_goals = get_manager_goals(db, chat_id)
        out: list[DomainGoal] = []
        for g in raw_goals or []:
            if not isinstance(g, dict):
                continue
            key = (g.get("belief_key") or "").strip()
            if not key:
                continue
            try:
                out.append(
                    DomainGoal(
                        belief_key=key,
                        target_value=float(g.get("target_value") or 0),
                        threshold=float(g.get("threshold") or 0),
                        title=str(g.get("title") or key).strip(),
                        observed_value=(
                            float(g["observed_value"])
                            if g.get("observed_value") is not None
                            else None
                        ),
                    )
                )
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        return []


def load_homeostasis_manifest(
    db: Any,
    tenant_id: str,
    *,
    chat_id: Any = None,
    migrate_legacy: bool = True,
) -> HomeostasisManifest:
    """Read manifest for tenant; optional in-memory migrate from agent_config goals."""
    manifest = _query_manifest_row(db, tenant_id)
    if migrate_legacy and not manifest.goals and chat_id:
        legacy = _legacy_goals_from_chat(db, chat_id)
        if legacy:
            _log.info(
                "homeostasis_manifest: migrated %d legacy goals from agent_config chat=%s",
                len(legacy),
                chat_id,
            )
            manifest = manifest.model_copy(update={"goals": legacy})
    return manifest


def load_homeostasis_targets(db: Any, tenant_id: str) -> HomeostasisTarget:
    """Read infra targets for tenant; fallback to Pydantic defaults."""
    return load_homeostasis_manifest(db, tenant_id, migrate_legacy=False).infra


def manifest_goals_as_dicts(manifest: HomeostasisManifest) -> list[dict[str, Any]]:
    return [g.model_dump() for g in manifest.goals]


def get_manifest_goals_for_chat(
    db: Any,
    chat_id: Any,
    *,
    tenant_id: str | None = None,
) -> list[dict[str, Any]]:
    """Goals from homeostasis manifest (single source for /crons scheduler and /meditate)."""
    tid = (tenant_id or "").strip()
    if not tid:
        try:
            from duckclaw.graphs.on_the_fly_commands import get_chat_state

            tid = (get_chat_state(db, chat_id, "tenant_id") or "default").strip() or "default"
        except Exception:
            tid = "default"
    return manifest_goals_as_dicts(load_homeostasis_manifest(db, tid, chat_id=chat_id))


def save_homeostasis_manifest(
    *,
    tenant_id: str,
    user_id: str,
    target_db_path: str,
    manifest: HomeostasisManifest,
) -> bool:
    """Enqueue UPSERT_HOMEOSTASIS_MANIFEST via meditate state delta queue."""
    return push_meditate_state_delta_sync(
        {
            "delta_type": "UPSERT_HOMEOSTASIS_MANIFEST",
            "tenant_id": tenant_id,
            "user_id": user_id,
            "target_db_path": target_db_path,
            "mutation": {"manifest": manifest.model_dump()},
        }
    )


def set_infra_field(manifest: HomeostasisManifest, field: str, value: Any) -> HomeostasisManifest:
    key = (field or "").strip()
    if key not in _INFRA_KEYS:
        raise ValueError(f"unknown infra field: {field}")
    infra = manifest.infra.model_copy(update={key: value})
    return manifest.model_copy(update={"infra": infra})
