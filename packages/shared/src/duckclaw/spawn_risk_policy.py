"""High-risk tool detection and spawn package import safety."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import yaml

from duckclaw.framework_tool_pack import ensure_baseline_skills, load_framework_tool_pack, should_apply_framework_baseline

HIGH_RISK_TOOL_EXACT = frozenset(
    {
        "admin_sql",
    }
)
HIGH_RISK_TOOL_PREFIXES = ("execute_", "propose_")

_SECRET_PATTERNS = (
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"(?i)(api[_-]?key|secret|token|password)\s*[:=]\s*['\"]?[a-zA-Z0-9_\-]{8,}"),
    re.compile(r"secret_[A-Za-z0-9]{20,}"),
)

_SPAWN_FILE_SUFFIXES = {".yaml", ".yml", ".md", ".sql", ".txt", ".json", ".py"}
_FORBIDDEN_SPAWN_FILES = {".env", ".pem", ".key", ".p12"}


@dataclass
class SpawnPackageAnalysis:
    worker_id: str
    required_tools: list[str] = field(default_factory=list)
    available_tools: list[str] = field(default_factory=list)
    missing_tools: list[str] = field(default_factory=list)
    high_risk_findings: list[str] = field(default_factory=list)
    import_blocked_until_confirm: bool = False
    secret_findings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "worker_id": self.worker_id,
            "required_tools": self.required_tools,
            "available_tools": self.available_tools,
            "missing_tools": self.missing_tools,
            "high_risk_findings": self.high_risk_findings,
            "import_blocked_until_confirm": self.import_blocked_until_confirm,
            "secret_findings": self.secret_findings,
        }


def is_high_risk_tool(tool_name: str) -> bool:
    name = str(tool_name or "").strip().lower()
    if not name:
        return False
    if name in HIGH_RISK_TOOL_EXACT:
        return True
    return any(name.startswith(prefix) for prefix in HIGH_RISK_TOOL_PREFIXES)


def scan_text_for_secrets(text: str, *, label: str) -> list[str]:
    findings: list[str] = []
    for pattern in _SECRET_PATTERNS:
        if pattern.search(text or ""):
            findings.append(label)
            break
    return findings


def scan_files_for_secrets(files: dict[str, str]) -> list[str]:
    findings: list[str] = []
    for rel, content in files.items():
        if any(rel.lower().endswith(ext) for ext in _FORBIDDEN_SPAWN_FILES):
            findings.append(rel)
            continue
        findings.extend(scan_text_for_secrets(content, label=rel))
    return sorted(set(findings))


def _manifest_skill_names(manifest: dict[str, Any]) -> list[str]:
    raw = manifest.get("skills") or []
    if isinstance(raw, str):
        raw = [s.strip() for s in raw.split(",") if s.strip()]
    names: list[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip():
            names.append(item.strip().lower().replace("-", "_"))
        elif isinstance(item, dict):
            key = str(item.get("name") or "").strip()
            if not key:
                for k in item:
                    key = str(k).strip()
                    break
            if key:
                names.append(key.lower().replace("-", "_"))
    if should_apply_framework_baseline(manifest):
        names = ensure_baseline_skills(names, manifest=manifest)
    return names


def _tools_from_manifest(manifest: dict[str, Any]) -> list[str]:
    tools: set[str] = set()
    pack = load_framework_tool_pack()
    always = pack.get("always_registered") or []
    for name in always:
        if str(name).strip():
            tools.add(str(name).strip().lower())
    for skill in _manifest_skill_names(manifest):
        tools.add(skill)
    tool_surface = manifest.get("tool_surface") if isinstance(manifest.get("tool_surface"), dict) else {}
    exposed = tool_surface.get("expose_privileged_mutation_tools") or []
    if isinstance(exposed, list):
        for item in exposed:
            name = str(item or "").strip().lower()
            if name:
                tools.add(name)
    if manifest.get("browser_sandbox") or manifest.get("security", {}).get("browser_sandbox"):
        tools.update({"run_sandbox", "run_browser_sandbox", "execute_sandbox_script"})
    return sorted(tools)


def _high_risk_from_manifest(manifest: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    for tool in _tools_from_manifest(manifest):
        if is_high_risk_tool(tool):
            findings.append(f"tool:{tool}")
    tool_surface = manifest.get("tool_surface") if isinstance(manifest.get("tool_surface"), dict) else {}
    exposed = tool_surface.get("expose_privileged_mutation_tools") or []
    if isinstance(exposed, list) and exposed:
        findings.append(f"manifest:tool_surface.expose_privileged_mutation_tools={exposed}")
    if manifest.get("read_only") is False and "admin_sql" in _tools_from_manifest(manifest):
        if not any(f.startswith("tool:admin_sql") for f in findings):
            findings.append("manifest:read_only=false with admin_sql skill path")
    return sorted(set(findings))


def sanitize_manifest_for_import(manifest: dict[str, Any], *, force_read_only: bool = True) -> dict[str, Any]:
    """Strip privileged mutation exposure; optionally force read_only on import."""
    out = json.loads(json.dumps(manifest or {}, ensure_ascii=False))
    tool_surface = out.get("tool_surface")
    if not isinstance(tool_surface, dict):
        tool_surface = {}
        out["tool_surface"] = tool_surface
    tool_surface["expose_privileged_mutation_tools"] = []
    if force_read_only:
        out["read_only"] = True
    return out


def analyze_spawn_package(
    manifest: dict[str, Any],
    files: dict[str, str],
    *,
    available_tools: list[str] | None = None,
) -> SpawnPackageAnalysis:
    worker_id = str(manifest.get("id") or manifest.get("worker_id") or "imported-worker").strip()
    required = _tools_from_manifest(manifest)
    available = sorted({str(t).strip().lower() for t in (available_tools or []) if str(t).strip()})
    available_set = set(available)
    missing = [t for t in required if t not in available_set and is_high_risk_tool(t) is False]
    # ponytail: only flag non-framework optional skills as missing heuristically
    optional_skills = set((load_framework_tool_pack().get("optional_skills") or {}).keys())
    missing = [
        t
        for t in missing
        if t not in optional_skills and t not in {"read_sql", "inspect_schema", "get_db_path", "get_current_time"}
    ]
    high_risk = _high_risk_from_manifest(manifest)
    secrets = scan_files_for_secrets(files)
    return SpawnPackageAnalysis(
        worker_id=worker_id,
        required_tools=required,
        available_tools=available,
        missing_tools=missing,
        high_risk_findings=high_risk,
        import_blocked_until_confirm=bool(high_risk),
        secret_findings=secrets,
    )


def parse_manifest_from_files(files: dict[str, str]) -> dict[str, Any]:
    raw = files.get("manifest.yaml") or files.get("manifest.yml") or ""
    if not raw.strip():
        raise ValueError("manifest.yaml requerido en el paquete")
    data = yaml.safe_load(raw) or {}
    if not isinstance(data, dict):
        raise ValueError("manifest.yaml inválido")
    if not str(data.get("id") or "").strip():
        raise ValueError("manifest.yaml debe incluir id")
    return data


def filter_spawn_files(files: dict[str, str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel, content in files.items():
        rel_norm = rel.replace("\\", "/").lstrip("/")
        if any(rel_norm.lower().endswith(ext) for ext in _FORBIDDEN_SPAWN_FILES):
            continue
        suffix = "." + rel_norm.rsplit(".", 1)[-1].lower() if "." in rel_norm else ""
        if suffix and suffix not in _SPAWN_FILE_SUFFIXES:
            continue
        out[rel_norm] = content
    return out
