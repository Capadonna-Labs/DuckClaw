"""Coordinador ADF: un template delega a sub-templates (forge/templates hermanos)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from duckclaw.workers.manifest import get_worker_dir, load_manifest
from duckclaw.workers.template_registry import list_template_ids, resolve_template_id_global

_ORCHESTRATOR_TOPOLOGY_IDS = frozenset({"orchestrator"})


@dataclass(frozen=True)
class OrchestratorConfig:
    coordinator_id: str
    orchestrates: tuple[str, ...]


def _normalize_orchestrates(
    raw: list | tuple | None,
    templates_root: Path | None,
) -> tuple[str, ...]:
    out: list[str] = []
    for item in raw or ():
        if not isinstance(item, str) or not item.strip():
            continue
        resolved = resolve_template_id_global(item.strip(), templates_root) or item.strip()
        if resolved not in out:
            out.append(resolved)
    return tuple(out)


def catalog_manifest_and_files(db: Any, worker_id: str, tenant_id: str) -> tuple[str, dict, dict] | None:
    """(catalog worker_id, manifest dict, files dict) of the latest catalog version, or None."""
    import json

    try:
        from duckclaw.catalog_worker import _lookup_catalog_worker, get_latest_worker_version

        cat, cdb = _lookup_catalog_worker(db, worker_id=worker_id, tenant_id=tenant_id)
        ver = get_latest_worker_version(cdb, worker_uid=cat["worker_uid"]) if cat else None
        if not ver:
            return None
        load = lambda v: json.loads(v) if isinstance(v, str) else (v if isinstance(v, dict) else {})  # noqa: E731
        return (str(cat.get("worker_id") or worker_id), load(ver.get("manifest_snapshot_json") or "{}"),
                load(ver.get("files_snapshot_json") or "{}"))
    except Exception:
        return None


def load_orchestrator_config(
    worker_id: str,
    templates_root: Path | None = None,
    *,
    db: Any = None,
    tenant_id: str = "default",
) -> OrchestratorConfig | None:
    """
    Lee ``orchestrator.enabled`` + ``orchestrator.orchestrates`` del manifest.
    También acepta ``topology: orchestrator`` con ``orchestrates`` en raíz del manifest.
    Con ``db``, un worker del catálogo DB usa el manifest de su última versión (los extra
    workers no existen en disco, así que antes nunca coordinaban).
    """
    wid = (worker_id or "").strip()
    if not wid:
        return None
    canonical = resolve_template_id_global(wid, templates_root) or wid
    data: Any = None
    try:
        manifest_path = get_worker_dir(canonical, templates_root) / "manifest.yaml"
        if manifest_path.is_file():
            import yaml

            data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception:
        data = None
    if data is None and db is not None:
        hit = catalog_manifest_and_files(db, wid, tenant_id)
        if hit:
            canonical, data, _files = hit
    if data is None:
        return None

    if not isinstance(data, dict):
        return None

    topology = str(data.get("topology") or "").strip().lower()
    orch_block = data.get("orchestrator")
    enabled = topology in _ORCHESTRATOR_TOPOLOGY_IDS
    raw_list: list | None = None

    if isinstance(orch_block, dict):
        if orch_block.get("enabled") is False:
            return None
        enabled = enabled or bool(orch_block.get("enabled"))
        raw_list = orch_block.get("orchestrates")
    if data.get("orchestrates") and isinstance(data.get("orchestrates"), list):
        raw_list = data.get("orchestrates")
        enabled = True

    if not enabled:
        return None

    orchestrates = _normalize_orchestrates(raw_list, templates_root)
    if not orchestrates:
        return None

    return OrchestratorConfig(coordinator_id=canonical, orchestrates=orchestrates)


def effective_delegation_pool(
    orchestrates: tuple[str, ...],
    team_templates: list[str],
    templates_root: Path | None = None,
) -> list[str]:
    """Intersección equipo ∩ orchestrates; si equipo vacío → todos los orchestrates."""
    pool = list(orchestrates)
    if not team_templates:
        return pool
    resolved_team: list[str] = []
    for t in team_templates:
        c = resolve_template_id_global(str(t).strip(), templates_root) or str(t).strip()
        if c and c not in resolved_team:
            resolved_team.append(c)
    if not resolved_team:
        return pool
    intersected = [w for w in pool if w in resolved_team]
    return intersected if intersected else pool


_DELEGATE_RULES: tuple[tuple[re.Pattern[str], str], ...] = ()


def pick_delegate_heuristic(
    incoming: str,
    pool: list[str],
    *,
    coordinator_id: str,
) -> str | None:
    """Elige subagente por palabras clave; fallback = coordinador si está en pool, si no el primero."""
    if not pool:
        return coordinator_id or None
    text = (incoming or "").strip()
    for pattern, target in _DELEGATE_RULES:
        if target in pool and pattern.search(text):
            return target
    if coordinator_id in pool:
        return coordinator_id
    return pool[0]


def pick_delegate_from_planner(
    delegate_worker_id: str | None,
    pool: list[str],
    templates_root: Path | None = None,
) -> str | None:
    if not delegate_worker_id or not pool:
        return None
    resolved = resolve_template_id_global(delegate_worker_id.strip(), templates_root)
    if resolved and resolved in pool:
        return resolved
    # Catalog workers are not in the template registry: match the pool ignoring case/punctuation.
    key = lambda s: "".join(ch for ch in str(s).lower() if ch.isalnum())  # noqa: E731
    return next((w for w in pool if key(w) == key(delegate_worker_id)), None)
