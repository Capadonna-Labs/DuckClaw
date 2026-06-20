"""Framework tool pack v1 — baseline skills merged into every worker unless opted out."""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

PACK_FILENAME = "framework_tool_pack_v1.json"
PACK_SEED = "framework_tool_pack_v1"


def framework_tool_pack_path() -> Path:
    return Path(__file__).resolve().parent / "seeds" / PACK_FILENAME


@lru_cache(maxsize=1)
def load_framework_tool_pack() -> dict[str, Any]:
    path = framework_tool_pack_path()
    if not path.is_file():
        raise FileNotFoundError(f"framework tool pack not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("framework tool pack must be a JSON object")
    baseline = data.get("baseline_skills")
    if not isinstance(baseline, list) or not baseline:
        raise ValueError("framework tool pack requires non-empty baseline_skills")
    return data


def baseline_skills_for_profile(profile: str) -> list[str]:
    pack = load_framework_tool_pack()
    key = (profile or "general").strip().lower()
    profiles = pack.get("profiles") or {}
    if key not in profiles:
        key = "general"
    resolved = profiles.get(key)
    if resolved == "baseline_skills":
        return [str(s).strip() for s in pack["baseline_skills"] if str(s).strip()]
    if isinstance(resolved, list):
        return [str(s).strip() for s in resolved if str(s).strip()]
    return [str(s).strip() for s in pack["baseline_skills"] if str(s).strip()]


def _env_present(names: list[str]) -> bool:
    for name in names:
        if str(os.environ.get(name) or "").strip():
            return True
    return False


def optional_skill_configs(manifest: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    """Return optional skill configs to merge when env prerequisites are met."""
    if manifest and manifest.get("baseline") is False:
        return {}
    pack = load_framework_tool_pack()
    optional = pack.get("optional_skills") or {}
    if not isinstance(optional, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for skill_name, spec in optional.items():
        if not isinstance(spec, dict):
            continue
        env_any = spec.get("env_any") or spec.get("env_required") or []
        if env_any and not _env_present([str(x) for x in env_any]):
            continue
        cfg = spec.get("default_config")
        if isinstance(cfg, dict) and cfg:
            out[str(skill_name).strip().lower().replace("-", "_")] = dict(cfg)
    return out


def should_apply_framework_baseline(manifest: dict[str, Any] | None) -> bool:
    if not manifest:
        return True
    if manifest.get("baseline") is False:
        return False
    if manifest.get("internal_scaffold") is True:
        return False
    return True


def ensure_baseline_skills(
    skills: list[str],
    *,
    manifest: dict[str, Any] | None = None,
) -> list[str]:
    """Merge framework baseline skills; preserve order (declared first, then baseline)."""
    if not should_apply_framework_baseline(manifest):
        return list(skills)
    profile = str((manifest or {}).get("tool_profile") or "general").strip().lower()
    baseline = baseline_skills_for_profile(profile)
    seen: set[str] = set()
    merged: list[str] = []
    for raw in list(skills) + baseline:
        key = str(raw or "").strip().lower().replace("-", "_")
        if not key or key in seen:
            continue
        seen.add(key)
        merged.append(key)
    for name in optional_skill_configs(manifest):
        key = str(name).strip().lower().replace("-", "_")
        if key and key not in seen:
            seen.add(key)
            merged.append(key)
    return merged


def ensure_baseline_skill_configs(
    skill_configs: dict[str, dict[str, Any]],
    *,
    skills: list[str],
    manifest: dict[str, Any] | None = None,
) -> dict[str, dict[str, Any]]:
    if not should_apply_framework_baseline(manifest):
        return dict(skill_configs)
    out = {k: dict(v) for k, v in (skill_configs or {}).items() if isinstance(v, dict)}
    optional = optional_skill_configs(manifest)
    for name, cfg in optional.items():
        if name in skills and name not in out:
            out[name] = dict(cfg)
    return out


def default_security_policy_yaml() -> str:
    return """network:
  default: deny
  allow_list: []
filesystem:
  readonly_mounts: []
  ephemeral_volumes:
    - /workspace/output
secrets:
  in_memory_only: true
  allowed_secrets: []
max_execution_time_seconds: 120
"""


def default_seed_dir() -> Path:
    packages_root = Path(__file__).resolve().parents[3]
    return (
        packages_root
        / "agents"
        / "src"
        / "duckclaw"
        / "forge"
        / "seed"
        / "default"
    )


def ensure_baseline_worker_files(worker_dir: Path) -> None:
    """Copy security_policy.yaml into a worker dir when missing."""
    policy_path = worker_dir / "security_policy.yaml"
    if policy_path.is_file():
        return
    seed_policy = default_seed_dir() / "security_policy.yaml"
    if seed_policy.is_file():
        policy_path.write_text(seed_policy.read_text(encoding="utf-8"), encoding="utf-8")
        return
    policy_path.write_text(default_security_policy_yaml(), encoding="utf-8")
