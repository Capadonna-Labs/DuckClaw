"""Productividad: storage local durable + índice de artefactos del agente.

spec: docs/architecture/system_overview.md
"""
from __future__ import annotations

import logging
import mimetypes
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)


def storage_root(*, base: Path | None = None) -> Path:
    if base is not None:
        return base
    env = (os.environ.get("DUCKCLAW_PRODUCTIVITY_STORAGE_ROOT") or "").strip()
    if env:
        return Path(env).expanduser().resolve()
    return (Path.cwd() / "storage" / "artifacts").resolve()


def tenant_storage_dir(tenant_id: str, *, base: Path | None = None) -> Path:
    tid = (tenant_id or "default").strip() or "default"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in tid)[:64] or "default"
    path = storage_root(base=base) / safe
    path.mkdir(parents=True, exist_ok=True)
    return path


def _mime_for(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"


def promote_files_to_storage(
    files: list[Path],
    *,
    tenant_id: str,
    owner_email: str,
    source_kind: str,
    source_ref: str,
    title_prefix: str = "",
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Copia ficheros a storage/ y devuelve payloads listos para upsert en el índice."""
    out: list[dict[str, Any]] = []
    dest_root = tenant_storage_dir(tenant_id, base=base)
    for src in files:
        if not src.is_file():
            continue
        artifact_id = f"part_{uuid.uuid4().hex[:12]}"
        dest_name = f"{artifact_id}_{src.name}"
        dest = dest_root / dest_name
        shutil.copy2(src, dest)
        title = (title_prefix or "").strip()
        if title:
            title = f"{title} — {src.name}"
        else:
            title = src.name
        out.append(
            {
                "artifact_id": artifact_id,
                "tenant_id": (tenant_id or "default").strip() or "default",
                "owner_email": (owner_email or "system").strip() or "system",
                "lane": "storage",
                "title": title,
                "filename": src.name,
                "uri": str(dest.resolve()),
                "source_kind": (source_kind or "sandbox").strip() or "sandbox",
                "source_ref": (source_ref or "").strip(),
                "mime": _mime_for(dest),
                "byte_size": int(dest.stat().st_size),
            }
        )
    return out


def enqueue_productivity_upserts(payloads: list[dict[str, Any]], *, actor_email: str) -> list[str]:
    """Encola upserts al db-writer. Devuelve task_ids (best-effort)."""
    if not payloads:
        return []
    try:
        from duckclaw.db_write_queue import enqueue_dict_command
        from duckclaw.gateway_db import get_gateway_db_path
    except Exception as exc:
        _log.warning("productivity enqueue imports failed: %s", exc)
        return []

    task_ids: list[str] = []
    db_path = get_gateway_db_path()
    actor = (actor_email or "system").strip() or "system"
    for row in payloads:
        try:
            tid = enqueue_dict_command(
                {
                    "command_type": "upsert_productivity_artifact",
                    **row,
                    "actor_email": actor,
                },
                db_path=db_path,
                user_id=actor,
            )
            task_ids.append(str(tid))
        except Exception as exc:
            _log.warning("productivity upsert enqueue failed artifact=%s: %s", row.get("artifact_id"), exc)
    return task_ids


def promote_sandbox_run_to_storage(
    *,
    source_files: list[Path],
    tenant_id: str,
    owner_email: str,
    run_id: str,
    chat_id: str = "",
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Copia artefactos de un run sandbox a storage/ e indexa (TTL scratch intacto)."""
    prefix = f"Sandbox {run_id[:8]}" if run_id else "Sandbox"
    if chat_id:
        prefix = f"{prefix} ({chat_id[:24]})"
    payloads = promote_files_to_storage(
        source_files,
        tenant_id=tenant_id,
        owner_email=owner_email,
        source_kind="sandbox",
        source_ref=(run_id or "").strip(),
        title_prefix=prefix,
        base=base,
    )
    enqueue_productivity_upserts(payloads, actor_email=owner_email)
    return payloads


def unlink_storage_uri(uri: str, *, base: Path | None = None) -> bool:
    """Borra archivo solo si está bajo storage_root."""
    raw = (uri or "").strip()
    if not raw:
        return False
    try:
        path = Path(raw).expanduser().resolve()
        root = storage_root(base=base)
        path.relative_to(root)
    except (ValueError, OSError):
        return False
    if path.is_file():
        path.unlink(missing_ok=True)
        return True
    return False


def register_vault_artifact_from_path(
    path: Path | str,
    *,
    tenant_id: str = "",
    owner_email: str = "",
    source_kind: str = "write_output",
    source_ref: str = "",
    title: str = "",
) -> dict[str, Any] | None:
    """Indexa un archivo bajo OUTPUT/vault en lane=vault (idempotente por URI)."""
    import hashlib

    try:
        target = Path(path).expanduser().resolve()
    except OSError:
        return None
    if not target.is_file():
        return None

    uri = str(target)
    digest = hashlib.sha256(uri.encode("utf-8")).hexdigest()[:12]
    artifact_id = f"pvlt_{digest}"
    tid = (tenant_id or "").strip()
    owner = (owner_email or "").strip()
    if not tid or not owner:
        try:
            from duckclaw.forge.skills.knowledge_tool_context import (
                get_knowledge_tool_tenant_id,
                get_session_actor_email,
            )

            tid = tid or get_knowledge_tool_tenant_id()
            owner = owner or get_session_actor_email()
        except Exception:
            tid = tid or "default"
            owner = owner or "system"

    payload = {
        "artifact_id": artifact_id,
        "tenant_id": tid or "default",
        "owner_email": owner or "system",
        "lane": "vault",
        "title": (title or target.name).strip() or target.name,
        "filename": target.name,
        "uri": uri,
        "source_kind": (source_kind or "write_output").strip() or "write_output",
        "source_ref": (source_ref or "").strip() or target.name,
        "mime": _mime_for(target),
        "byte_size": int(target.stat().st_size),
    }
    enqueue_productivity_upserts([payload], actor_email=owner or "system")
    return payload

def promote_storage_file_to_vault(
    *,
    source_uri: str,
    tenant_id: str,
    owner_email: str,
    title: str = "",
    filename: str = "",
    relative_dir: str = "Productividad",
    remove_from_storage: bool = False,
    storage_base: Path | None = None,
) -> dict[str, Any]:
    """Copia un archivo de storage/ a OUTPUT_ROOTS e indexa lane=vault."""
    from duckclaw.forge.rag.knowledge_paths import resolve_knowledge_output_path

    raw = (source_uri or "").strip()
    if not raw:
        raise ValueError("source_uri vacío")
    src = Path(raw).expanduser().resolve()
    root = storage_root(base=storage_base)
    try:
        src.relative_to(root)
    except ValueError as exc:
        raise ValueError("El archivo no está bajo storage/ del repo") from exc
    if not src.is_file():
        raise ValueError(f"Archivo no encontrado: {src}")

    name = (filename or src.name).strip() or src.name
    parts = src.name.split("_", 2)
    if len(parts) >= 3 and parts[0] == "part":
        name = parts[2]

    folder = (relative_dir or "Productividad").strip().strip("/") or "Productividad"
    rel = f"{folder}/{name}".replace("//", "/")
    dest = resolve_knowledge_output_path(relative_path=rel)
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)

    indexed = register_vault_artifact_from_path(
        dest,
        tenant_id=tenant_id,
        owner_email=owner_email,
        source_kind="promote_storage",
        source_ref=str(src),
        title=(title or name).strip() or name,
    )
    if not indexed:
        raise ValueError("No se pudo indexar el archivo en vault")

    if remove_from_storage:
        unlink_storage_uri(str(src), base=storage_base)

    return {
        "vault_artifact_id": indexed["artifact_id"],
        "vault_uri": indexed["uri"],
        "relative_path": rel,
        "filename": name,
        "removed_from_storage": bool(remove_from_storage),
    }
