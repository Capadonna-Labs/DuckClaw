"""DB-first worker identity and runtime policy readers."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from duckclaw.shared_db_grants import _query_all_dicts, _sql_lit

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class WorkerIdentity:
    worker_uid: str
    tenant_id: str
    worker_id: str
    display_name: str
    source_kind: str
    active: bool


@dataclass(frozen=True)
class WorkerCapability:
    capability_id: str
    name: str
    kind: str
    provider: str
    permission: str
    config: dict[str, Any]
    policy: dict[str, Any]
    quota: dict[str, Any]


@dataclass(frozen=True)
class WorkerRuntimePolicyEntry:
    runtime_policy_id: str
    worker_uid: str
    policy_key: str
    policy_scope: str
    policy_value: dict[str, Any]


@dataclass(frozen=True)
class WorkerRuntimePolicy:
    worker_id: str
    identity: WorkerIdentity | None
    capabilities: tuple[WorkerCapability, ...] = ()
    runtime_policies: tuple[WorkerRuntimePolicyEntry, ...] = ()

    def has_capability(self, capability_name: str) -> bool:
        wanted = normalize_worker_id(capability_name)
        return any(normalize_worker_id(cap.name) == wanted for cap in self.capabilities)

    def policy_for(self, capability_name: str) -> dict[str, Any]:
        wanted = normalize_worker_id(capability_name)
        for cap in self.capabilities:
            if normalize_worker_id(cap.name) == wanted:
                return dict(cap.policy)
        return {}

    def runtime_policy_value(
        self,
        policy_key: str,
        *,
        policy_scope: str | None = None,
    ) -> dict[str, Any]:
        wanted_key = normalize_worker_id(policy_key)
        wanted_scope = normalize_worker_id(policy_scope)
        for entry in self.runtime_policies:
            if normalize_worker_id(entry.policy_key) != wanted_key:
                continue
            if wanted_scope and normalize_worker_id(entry.policy_scope) != wanted_scope:
                continue
            return dict(entry.policy_value)
        return {}


def normalize_worker_id(worker_id: str | None) -> str:
    return (worker_id or "").strip().lower()


def is_worker(worker_id: str | None, *expected: str) -> bool:
    normalized = normalize_worker_id(worker_id)
    return normalized in {normalize_worker_id(item) for item in expected}


def _json_dict(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except (TypeError, json.JSONDecodeError):
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    return str(value or "").strip().lower() not in {"false", "0", "no", "off"}


def _identity_from_row(row: dict[str, Any]) -> WorkerIdentity:
    return WorkerIdentity(
        worker_uid=str(row.get("worker_uid") or ""),
        tenant_id=str(row.get("tenant_id") or ""),
        worker_id=str(row.get("worker_id") or ""),
        display_name=str(row.get("display_name") or ""),
        source_kind=str(row.get("source_kind") or "runtime"),
        active=_coerce_bool(row.get("active")),
    )


class WorkerRuntimePolicyReader:
    """Read generic worker identity, capabilities and policy from DuckDB."""

    def __init__(self, db: Any):
        if db is None:
            raise RuntimeError("WorkerRuntimePolicyReader requires a DuckDB connection")
        self.db = db

    def load(self, worker_id: str | None, *, tenant_id: str | None = None) -> WorkerRuntimePolicy:
        identity = self.resolve_identity(worker_id, tenant_id=tenant_id)
        return self._policy_for_identity(identity, fallback_worker_id=worker_id)

    def load_by_uid(self, worker_uid: str) -> WorkerRuntimePolicy:
        identity = self.resolve_identity_by_uid(worker_uid)
        return self._policy_for_identity(identity, fallback_worker_id=None)

    def resolve_identity(
        self,
        worker_id: str | None,
        *,
        tenant_id: str | None = None,
    ) -> WorkerIdentity | None:
        normalized = normalize_worker_id(worker_id)
        if not normalized:
            return None
        tenant_clause = ""
        if tenant_id:
            tenant_clause = f"AND tenant_id = '{_sql_lit(tenant_id, 128)}' "
        try:
            rows = _query_all_dicts(
                self.db,
                "SELECT worker_uid, tenant_id, worker_id, display_name, source_kind, active "
                "FROM main.admin_worker_catalog "
                f"WHERE lower(worker_id) = '{_sql_lit(normalized, 64)}' "
                f"{tenant_clause}"
                "AND active = true "
                "ORDER BY updated_at DESC, worker_uid LIMIT 1",
            )
        except Exception as exc:
            _log.debug("worker identity lookup skipped: %s", exc)
            return None
        return _identity_from_row(rows[0]) if rows else None

    def resolve_identity_by_uid(self, worker_uid: str) -> WorkerIdentity | None:
        uid = (worker_uid or "").strip()
        if not uid:
            return None
        try:
            rows = _query_all_dicts(
                self.db,
                "SELECT worker_uid, tenant_id, worker_id, display_name, source_kind, active "
                "FROM main.admin_worker_catalog "
                f"WHERE worker_uid = '{_sql_lit(uid, 64)}' "
                "AND active = true LIMIT 1",
            )
        except Exception as exc:
            _log.debug("worker identity lookup by uid skipped: %s", exc)
            return None
        return _identity_from_row(rows[0]) if rows else None

    def _policy_for_identity(
        self,
        identity: WorkerIdentity | None,
        *,
        fallback_worker_id: str | None,
    ) -> WorkerRuntimePolicy:
        worker_uid = identity.worker_uid if identity else ""
        capabilities = self._load_capabilities(worker_uid) if worker_uid else ()
        runtime_policies = self._load_runtime_policies(worker_uid) if worker_uid else ()
        worker_id = identity.worker_id if identity else normalize_worker_id(fallback_worker_id)
        return WorkerRuntimePolicy(
            worker_id=normalize_worker_id(worker_id),
            identity=identity,
            capabilities=capabilities,
            runtime_policies=runtime_policies,
        )

    def _load_capabilities(self, worker_uid: str) -> tuple[WorkerCapability, ...]:
        if not worker_uid:
            return ()
        try:
            rows = _query_all_dicts(
                self.db,
                "SELECT c.capability_id, c.name, c.kind, c.provider, wc.permission, "
                "wc.config_json, wc.policy_json, wc.quota_json "
                "FROM main.admin_worker_capabilities wc "
                "JOIN main.admin_capabilities c ON c.capability_id = wc.capability_id "
                f"WHERE wc.worker_uid = '{_sql_lit(worker_uid, 64)}' "
                "AND wc.enabled = true AND c.active = true "
                "ORDER BY c.name",
            )
        except Exception as exc:
            _log.debug("worker capability lookup skipped: %s", exc)
            return ()
        return tuple(
            WorkerCapability(
                capability_id=str(row.get("capability_id") or ""),
                name=str(row.get("name") or ""),
                kind=str(row.get("kind") or ""),
                provider=str(row.get("provider") or ""),
                permission=str(row.get("permission") or "use"),
                config=_json_dict(row.get("config_json")),
                policy=_json_dict(row.get("policy_json")),
                quota=_json_dict(row.get("quota_json")),
            )
            for row in rows
            if isinstance(row, dict)
        )

    def _load_runtime_policies(self, worker_uid: str) -> tuple[WorkerRuntimePolicyEntry, ...]:
        if not worker_uid:
            return ()
        try:
            rows = _query_all_dicts(
                self.db,
                "SELECT runtime_policy_id, worker_uid, policy_key, policy_scope, policy_value_json "
                "FROM main.worker_runtime_policies "
                f"WHERE worker_uid = '{_sql_lit(worker_uid, 64)}' "
                "AND active = true ORDER BY policy_scope, policy_key",
            )
        except Exception as exc:
            _log.debug("worker runtime policy lookup skipped: %s", exc)
            return ()
        return tuple(
            WorkerRuntimePolicyEntry(
                runtime_policy_id=str(row.get("runtime_policy_id") or ""),
                worker_uid=str(row.get("worker_uid") or ""),
                policy_key=str(row.get("policy_key") or ""),
                policy_scope=str(row.get("policy_scope") or "runtime"),
                policy_value=_json_dict(row.get("policy_value_json")),
            )
            for row in rows
            if isinstance(row, dict)
        )


def load_worker_runtime_policy(
    db: Any,
    worker_id: str | None,
    *,
    tenant_id: str | None = None,
) -> WorkerRuntimePolicy:
    return WorkerRuntimePolicyReader(db).load(worker_id, tenant_id=tenant_id)


def load_worker_runtime_policy_by_uid(db: Any, worker_uid: str) -> WorkerRuntimePolicy:
    return WorkerRuntimePolicyReader(db).load_by_uid(worker_uid)


def get_worker_identity(db: Any, worker_uid: str) -> WorkerIdentity | None:
    return WorkerRuntimePolicyReader(db).resolve_identity_by_uid(worker_uid)


def worker_has_capability(
    db: Any,
    worker_id: str | None,
    capability_name: str,
    *,
    tenant_id: str | None = None,
) -> bool:
    return load_worker_runtime_policy(db, worker_id, tenant_id=tenant_id).has_capability(capability_name)
