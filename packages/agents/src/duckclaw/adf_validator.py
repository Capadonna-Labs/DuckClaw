"""
ADF Validator — Agent Definition Framework
Valida que la estructura ADF de un agente sea completa y correcta.
Usado en: setup.sh, Janitor nocturno, arranque de AXIS.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

# Seis agentes AXIS (ADF); viven bajo forge/templates/<agent_id>/ (FORGE = paquete, no agente).
AXIS_ADF_AGENT_IDS: frozenset[str] = frozenset(
    ( "maestro","coder", "mirror", "radar", "sentinel", "phantom")
)

REQUIRED_FILES = [
    "manifest.yaml",
    "system_prompt.md",
    "schema.sql",
    "security_policy.yaml",
    "domain_closure.md",
    "homeostasis.yaml",
    "README.md",
]

REQUIRED_SYSTEM_PROMPT_SECTIONS = [
    "# IDENTITY",
    "# DOMAIN",
    "# CONSTRAINTS",
    "# ESCALATION_PROTOCOL",
    "# OUTPUT_FORMAT",
]

REQUIRED_MANIFEST_FIELDS = [
    "agent_id",
    "display_name",
    "version",
    "phase",
    "status",
    "description",
    "llm_config",
    "memory",
    "dependencies",
    "events_produced",
    "events_consumed",
]


@dataclass
class ValidationResult:
    valid: bool
    agent_id: str
    errors: list[str]
    warnings: list[str]
    hashes: dict[str, str]


def _agent_slug_from_adf_path(adf_path: Path) -> str:
    """ADF path: .../forge/templates/<agent_id> (nombre de carpeta = agent_id)."""
    return adf_path.name


def axis_adf_dir_name(agent_id: str) -> str:
    """Carpeta en disco: ``AXIS-Coder``, ``AXIS-Maestro``, … (``agent_id`` canónico en minúsculas)."""
    return f"AXIS-{agent_id[0].upper()}{agent_id[1:]}" if agent_id else agent_id


def resolve_axis_adf_path(templates_root: Path, agent_id: str) -> Path | None:
    """Resuelve ``forge/templates/<agent_id>/`` o ``forge/templates/AXIS-<Name>/``."""
    direct = templates_root / agent_id
    if direct.is_dir():
        return direct
    axis = templates_root / axis_adf_dir_name(agent_id)
    if axis.is_dir():
        return axis
    return None


def validate_agent(adf_path: Path, *, canonical_agent_id: str | None = None) -> ValidationResult:
    """Valida la carpeta ADF de un agente completa."""
    errors: list[str] = []
    warnings: list[str] = []
    hashes: dict[str, str] = {}
    agent_slug = _agent_slug_from_adf_path(adf_path)
    expected_id = (canonical_agent_id or agent_slug).strip()

    for filename in REQUIRED_FILES:
        filepath = adf_path / filename
        if not filepath.exists():
            errors.append(f"Archivo faltante: {filename}")
        else:
            content = filepath.read_bytes()
            hashes[filename] = hashlib.sha256(content).hexdigest()

    if errors:
        return ValidationResult(
            valid=False,
            agent_id=expected_id,
            errors=errors,
            warnings=warnings,
            hashes=hashes,
        )

    allowed = set(REQUIRED_FILES)
    for child in adf_path.iterdir():
        if child.name.startswith("."):
            continue
        if child.is_file() and child.name not in allowed:
            warnings.append(f"Archivo extra en ADF (solo 7 esperados): {child.name}")
        if child.is_dir():
            warnings.append(f"Carpeta extra en ADF: {child.name}/")

    try:
        manifest = yaml.safe_load((adf_path / "manifest.yaml").read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            errors.append("manifest.yaml: raíz debe ser un mapa YAML")
        else:
            for field in REQUIRED_MANIFEST_FIELDS:
                if field not in manifest:
                    errors.append(f"manifest.yaml: campo faltante '{field}'")
            mid = manifest.get("agent_id")
            if mid is not None and mid != expected_id:
                errors.append(
                    f"manifest.yaml: agent_id '{mid}' "
                    f"no coincide con id canónico '{expected_id}' (carpeta '{agent_slug}')"
                )
    except Exception as e:
        errors.append(f"manifest.yaml: error de parseo — {e}")

    try:
        prompt_content = (adf_path / "system_prompt.md").read_text(encoding="utf-8")
        for section in REQUIRED_SYSTEM_PROMPT_SECTIONS:
            if section not in prompt_content:
                errors.append(f"system_prompt.md: sección faltante '{section}'")
    except Exception as e:
        errors.append(f"system_prompt.md: error de lectura — {e}")

    try:
        policy = yaml.safe_load((adf_path / "security_policy.yaml").read_text(encoding="utf-8"))
        if not isinstance(policy, dict):
            errors.append("security_policy.yaml: raíz debe ser un mapa YAML")
        else:
            if "can_do" not in policy:
                errors.append("security_policy.yaml: falta 'can_do'")
            if "cannot_do" not in policy:
                errors.append("security_policy.yaml: falta 'cannot_do'")
            if "data_egress" not in policy:
                warnings.append("security_policy.yaml: falta 'data_egress' (recomendado)")
    except Exception as e:
        errors.append(f"security_policy.yaml: error de parseo — {e}")

    try:
        schema_content = (adf_path / "schema.sql").read_text(encoding="utf-8")
        lines_with_create = [ln for ln in schema_content.split("\n") if "CREATE TABLE" in ln.upper()]
        for line in lines_with_create:
            lower = line.lower()
            if expected_id not in lower and "gold_" not in lower:
                warnings.append(f"schema.sql: tabla sin prefijo '{expected_id}_' ni gold_: {line.strip()}")
    except Exception as e:
        errors.append(f"schema.sql: error de lectura — {e}")

    return ValidationResult(
        valid=len(errors) == 0,
        agent_id=expected_id,
        errors=errors,
        warnings=warnings,
        hashes=hashes,
    )


def validate_all_agents(repo_root: Path) -> dict[str, ValidationResult]:
    """Valida los 6 agentes AXIS bajo packages/agents/src/duckclaw/forge/templates/."""
    results: dict[str, ValidationResult] = {}
    templates_root = (
        repo_root / "packages" / "agents" / "src" / "duckclaw" / "forge" / "templates"
    )
    if not templates_root.is_dir():
        return results

    for agent_id in sorted(AXIS_ADF_AGENT_IDS):
        adf_path = resolve_axis_adf_path(templates_root, agent_id)
        if adf_path is not None:
            results[agent_id] = validate_agent(adf_path, canonical_agent_id=agent_id)

    return results


if __name__ == "__main__":
    repo_root = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else Path.cwd().resolve()
    results = validate_all_agents(repo_root)

    all_valid = True
    for agent_id, result in sorted(results.items()):
        status = "OK" if result.valid else "FAIL"
        print(f"{status} {agent_id}")
        for error in result.errors:
            print(f"   ERROR: {error}")
        for warning in result.warnings:
            print(f"   WARN:  {warning}")
        if not result.valid:
            all_valid = False

    if not results:
        print(
            "WARN: no se encontraron carpetas ADF AXIS bajo "
            "packages/agents/src/duckclaw/forge/templates/{coder,mirror,...}"
        )
        sys.exit(1)

    missing = sorted(AXIS_ADF_AGENT_IDS - set(results))
    if missing:
        print(f"FAIL: faltan agentes AXIS esperados: {', '.join(missing)}")
        sys.exit(1)

    sys.exit(0 if all_valid else 1)
