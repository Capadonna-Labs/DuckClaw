"""Coordinador ADF: un template delega a sub-templates (forge/templates hermanos)."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from duckclaw.workers.manifest import get_worker_dir, load_manifest
from duckclaw.workers.template_registry import list_template_ids, resolve_template_id_global

# Subagentes AXIS por defecto si el manifest no define orchestrates.
DEFAULT_AXIS_ORCHESTRATES: tuple[str, ...] = (
    "AXIS-Coder",
    "AXIS-Mirror",
    "AXIS-Radar",
    "AXIS-Sentinel",
    "AXIS-Phantom",
)


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


def load_orchestrator_config(
    worker_id: str,
    templates_root: Path | None = None,
) -> OrchestratorConfig | None:
    """
    Lee ``orchestrator.enabled`` + ``orchestrator.orchestrates`` del manifest.
    También acepta ``topology: axis_orchestrator`` con ``orchestrates`` en raíz.
    """
    wid = (worker_id or "").strip()
    if not wid:
        return None
    canonical = resolve_template_id_global(wid, templates_root) or wid
    try:
        get_worker_dir(canonical, templates_root)
    except FileNotFoundError:
        return None

    manifest_path = get_worker_dir(canonical, templates_root) / "manifest.yaml"
    if not manifest_path.is_file():
        return None

    try:
        import yaml

        data = yaml.safe_load(manifest_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None

    if not isinstance(data, dict):
        return None

    topology = str(data.get("topology") or "").strip().lower()
    orch_block = data.get("orchestrator")
    enabled = topology == "axis_orchestrator"
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
    if not orchestrates and canonical.lower().startswith("axis-maestro"):
        orchestrates = DEFAULT_AXIS_ORCHESTRATES

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


# Heurística de dominio (ESCALATION_PROTOCOL AXIS) cuando el planner no devuelve delegate.
_DELEGATE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(cve|cve-\d|exploit|threat\s*intel|osint|feed|ioc)\b", re.I), "AXIS-Radar"),
    (re.compile(r"\b(red\s*team|purple\s*team|mitre|att&ck|ofensiv|pentest|exploit\s*chain)\b", re.I), "AXIS-Sentinel"),
    (re.compile(r"\b(lab|hacklab|vm|máquina|maquina|phantom|práctica|practica)\b", re.I), "AXIS-Phantom"),
    (re.compile(r"\b(commit|repo|git|código|codigo|python|rust|api|refactor|bug)\b", re.I), "AXIS-Coder"),
    (re.compile(r"\b(perfil|nivel|skill|habilidad|mirror|autoevaluación)\b", re.I), "AXIS-Mirror"),
)


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
    return None
