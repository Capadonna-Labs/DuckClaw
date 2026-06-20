"""
ADF Validator — Agent Definition Framework
Validates that an agent template directory has the required ADF structure.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path

import yaml

REQUIRED_FILES: list[str] = []

REQUIRED_SYSTEM_PROMPT_SECTIONS: list[str] = []

REQUIRED_MANIFEST_FIELDS: list[str] = []


@dataclass
class ValidationResult:
    valid: bool
    agent_id: str
    errors: list[str]
    warnings: list[str]
    hashes: dict[str, str]


def validate_agent(adf_path: Path, *, canonical_agent_id: str | None = None) -> ValidationResult:
    errors: list[str] = []
    warnings: list[str] = []
    hashes: dict[str, str] = {}
    agent_slug = adf_path.name
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
        policy_path = adf_path / "security_policy.yaml"
        if policy_path.is_file():
            policy = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
            if not isinstance(policy, dict):
                errors.append("security_policy.yaml: raíz debe ser un mapa YAML")
            elif "network" in policy or "filesystem" in policy or "max_execution_time_seconds" in policy:
                try:
                    from duckclaw.forge.schema import SecurityPolicy

                    SecurityPolicy.model_validate(policy)
                except Exception as exc:
                    errors.append(f"security_policy.yaml: schema Strix inválido — {exc}")
            else:
                if "can_do" not in policy:
                    errors.append("security_policy.yaml: falta 'can_do' (legacy) o bloque 'network' (Strix)")
                if "cannot_do" not in policy:
                    errors.append("security_policy.yaml: falta 'cannot_do' (legacy) o bloque 'network' (Strix)")
                if "data_egress" not in policy:
                    warnings.append("security_policy.yaml: falta 'data_egress' (recomendado en formato legacy)")
        else:
            warnings.append(
                "security_policy.yaml ausente — la plataforma aplicará zero-trust al ejecutar sandbox"
            )
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
    results: dict[str, ValidationResult] = {}
    templates_root = (
        repo_root / "packages" / "agents" / "src" / "duckclaw" / "forge" / "templates"
    )
    if not templates_root.is_dir():
        return results
    for folder in templates_root.iterdir():
        if folder.is_dir() and (folder / "manifest.yaml").is_file():
            results[folder.name] = validate_agent(folder)
    return results
