"""Build spawn package zip/tar with full ADF + A2A agent card."""

from __future__ import annotations

import io
import zipfile
from typing import Any

from duckclaw.agent_card_builder import build_a2a_agent_card
from duckclaw.spawn_risk_policy import SpawnPackageAnalysis, analyze_spawn_package, filter_spawn_files, scan_files_for_secrets
from duckclaw.worker_adf_snapshot import load_worker_adf_snapshot

_README_TEMPLATE = """# Spawn de {worker_name}

Este paquete permite recrear el worker **{worker_name}** en cualquier instancia DuckClaw.

## Requisitos

- DuckClaw instalado: https://github.com/Capadonna-Labs/duckclaw
- Tools declaradas en el manifest (ver `agent-card.json` → skills)

## Instalación (DB-first)

1. Admin → **Agentes** → **Importar worker desde paquete**
2. O API: `POST /api/v1/admin/agents/spawn-package/import` (multipart, admin auth)
3. Revisa el preview de tools de alto riesgo y confirma explícitamente si aplica
4. Tras import, el worker queda en el catálogo DuckDB (`admin_worker_catalog`)

## Advertencia de seguridad

Este worker fue exportado desde una instancia privada. Verifica `system_prompt.md` y
`domain_closure.md` antes de activarlo. Un manifest puede referenciar tools sensibles
(`admin_sql`, `execute_*`, señales de broker) que requieren revisión manual en destino.

## Contenido

- `agent-card.json` — metadata pública A2A v1.0 (sin prompts)
- `manifest.yaml`, `soul.md`, `system_prompt.md`, `domain_closure.md` — ADF completo
"""


def _ensure_adf_files(files: dict[str, str], manifest: dict[str, Any]) -> dict[str, str]:
    import yaml

    out = dict(filter_spawn_files(files))
    if "manifest.yaml" not in out and "manifest.yml" in out:
        out["manifest.yaml"] = out.pop("manifest.yml")
    if "manifest.yaml" not in out:
        out["manifest.yaml"] = yaml.safe_dump(manifest, allow_unicode=True, sort_keys=False)
    return out


def build_spawn_readme(worker_name: str) -> str:
    return _README_TEMPLATE.format(worker_name=worker_name)


def build_spawn_package_bytes(
    db: Any,
    worker_id: str,
    *,
    tenant_id: str = "default",
    public_base_url: str | None = None,
    gateway_a2a_url: str | None = None,
) -> bytes:
    manifest, files, _cat = load_worker_adf_snapshot(db, worker_id, tenant_id=tenant_id)
    files = _ensure_adf_files(files, manifest)
    secrets = scan_files_for_secrets(files)
    if secrets:
        raise ValueError(f"Export blocked: possible secrets in {', '.join(secrets[:5])}")

    card = build_a2a_agent_card(
        worker_id,
        manifest=manifest,
        files=files,
        public_base_url=public_base_url,
        gateway_a2a_url=gateway_a2a_url,
    )
    worker_name = str(manifest.get("display_name") or manifest.get("id") or worker_id)
    readme = build_spawn_readme(worker_name)

    buf = io.BytesIO()
    root = f"{worker_id}-spawn-package"
    with zipfile.ZipFile(buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        import json

        zf.writestr(f"{root}/agent-card.json", json.dumps(card, ensure_ascii=False, indent=2) + "\n")
        zf.writestr(f"{root}/README.md", readme)
        for rel, content in sorted(files.items()):
            zf.writestr(f"{root}/{rel}", content)
    return buf.getvalue()


def analyze_spawn_package_from_bytes(
    package_bytes: bytes,
    *,
    available_tools: list[str] | None = None,
) -> tuple[SpawnPackageAnalysis, dict[str, Any], dict[str, str]]:
    from duckclaw.spawn_package_extract import extract_spawn_package
    from duckclaw.spawn_risk_policy import parse_manifest_from_files

    files = extract_spawn_package(package_bytes)
    manifest = parse_manifest_from_files(files)
    files = filter_spawn_files(files)
    analysis = analyze_spawn_package(manifest, files, available_tools=available_tools)
    return analysis, manifest, files
