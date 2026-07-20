"""Registro efímero de artefactos del Strix sandbox (scratch, TTL, sin RAG).

spec: docs/architecture/system_overview.md
"""

from __future__ import annotations

import csv
import json
import logging
import mimetypes
import os
import re
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_log = logging.getLogger(__name__)

MANIFEST_NAME = "manifest.json"
_DEFAULT_TTL_S = 259200
_PREVIEW_JSON_MAX_CHARS = 32_000
_PREVIEW_TEXT_MAX_CHARS = 64_000
_PREVIEW_CSV_MAX_ROWS = 100
_PREVIEW_PARQUET_MAX_ROWS = 50


class PathTraversalError(ValueError):
    """Ruta relativa inválida dentro de un run sandbox."""


class ArtifactNotFoundError(FileNotFoundError):
    """Artefacto no encontrado para el chat dado."""


class RunNotFoundError(FileNotFoundError):
    """Run sandbox no encontrado."""


class PreviewNotSupportedError(ValueError):
    """Preview no disponible para este MIME/tipo."""


@dataclass
class PreviewResult:
    kind: str
    mime: str = ""
    data: bytes = b""
    payload: dict[str, Any] = field(default_factory=dict)


def sandbox_artifact_ttl_s() -> int:
    raw = (os.environ.get("DUCKCLAW_SANDBOX_ARTIFACT_TTL_S") or "").strip()
    try:
        ttl = int(raw) if raw else _DEFAULT_TTL_S
    except ValueError:
        ttl = _DEFAULT_TTL_S
    return max(60, ttl)


def artifacts_base(*, base: Path | None = None) -> Path:
    if base is not None:
        return base
    env_root = (os.environ.get("DUCKCLAW_SANDBOX_ARTIFACTS_ROOT") or "").strip()
    if env_root:
        return Path(env_root)
    return Path.cwd() / "output" / "sandbox"


def sandbox_output_root() -> Path:
    return artifacts_base()


def sanitize_chat_to_session_id(chat_id: str) -> str:
    """Debe coincidir con ``duckclaw.graphs.novnc_registry.sanitize_chat_to_session_id``."""
    raw = (chat_id or "").strip() or "default"
    s = re.sub(r"[^a-zA-Z0-9_]", "_", raw)
    s = s.strip("_") or "default"
    if len(s) > 48:
        s = s[:48]
    return s


def chat_session_dir(chat_id: str, *, base: Path | None = None) -> Path:
    return artifacts_base(base=base) / sanitize_chat_to_session_id(chat_id)


def _detect_mime(path: Path) -> str:
    guessed, _ = mimetypes.guess_type(path.name)
    if guessed:
        return guessed
    ext = path.suffix.lower()
    if ext == ".md":
        return "text/markdown"
    if ext == ".csv":
        return "text/csv"
    if ext == ".parquet":
        return "application/vnd.apache.parquet"
    if ext == ".docx":
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    return "application/octet-stream"


def is_previewable(mime: str, filename: str) -> bool:
    m = (mime or "").lower()
    name = (filename or "").lower()
    if m.startswith("image/"):
        return True
    if m.startswith("text/") or name.endswith(".md"):
        return True
    if name.endswith(".csv") or m == "text/csv":
        return True
    if name.endswith(".json") or m == "application/json":
        return True
    if name.endswith(".parquet"):
        return True
    if name.endswith(".docx"):
        return True
    return False


def _safe_artifact_path(run_dir: Path, relative_path: str) -> Path:
    rel = (relative_path or "").strip().replace("\\", "/")
    if not rel or rel.startswith("/") or ".." in rel.split("/"):
        raise PathTraversalError("invalid relative_path")
    candidate = (run_dir / rel).resolve()
    run_resolved = run_dir.resolve()
    if candidate != run_resolved and not str(candidate).startswith(f"{run_resolved}{os.sep}"):
        raise PathTraversalError("path traversal blocked")
    return candidate


def _read_manifest(run_dir: Path) -> dict[str, Any] | None:
    manifest_path = run_dir / MANIFEST_NAME
    if not manifest_path.is_file():
        return None
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _write_manifest_file(run_dir: Path, manifest: dict[str, Any]) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / MANIFEST_NAME).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def write_run_manifest(
    *,
    chat_id: str,
    run_id: str,
    artifacts: list[dict[str, Any]],
    tenant_id: str = "default",
    worker_id: str = "default",
    exit_code: int = 0,
    expires_at: float | None = None,
    created_at: float | None = None,
    base: Path | None = None,
) -> dict[str, Any]:
    """Escribe manifest (tests / seed). Los archivos deben existir ya en run_dir."""
    rid = (run_id or "").strip()
    if not rid:
        raise ValueError("run_id required")
    now = float(created_at if created_at is not None else time.time())
    exp = float(expires_at if expires_at is not None else now + float(sandbox_artifact_ttl_s()))
    session_id = sanitize_chat_to_session_id(chat_id)
    run_dir = chat_session_dir(chat_id, base=base) / rid
    manifest: dict[str, Any] = {
        "run_id": rid,
        "chat_id": (chat_id or "").strip() or "default",
        "chat_session_id": session_id,
        "tenant_id": (tenant_id or "default").strip() or "default",
        "worker_id": (worker_id or "default").strip() or "default",
        "created_at": now,
        "expires_at": exp,
        "exit_code": int(exit_code),
        "artifacts": artifacts,
    }
    _write_manifest_file(run_dir, manifest)
    return manifest


def register_run_artifacts(
    chat_id: str,
    tenant_id: str,
    worker_id: str,
    run_id: str,
    exit_code: int,
    artifact_files: list[Path],
) -> dict[str, Any]:
    """Copia artefactos a ``output/sandbox/{chat_session_id}/{run_id}/`` y escribe manifest."""
    rid = (run_id or "").strip()
    if not rid:
        raise ValueError("run_id required")
    files = [p for p in artifact_files if p.is_file()]
    run_dir = chat_session_dir(chat_id) / rid
    run_dir.mkdir(parents=True, exist_ok=True)

    now = time.time()
    artifacts_meta: list[dict[str, Any]] = []
    for src in files:
        dest_name = src.name
        if not dest_name or dest_name == MANIFEST_NAME:
            continue
        dest = run_dir / dest_name
        shutil.copy2(src, dest)
        mime = _detect_mime(dest)
        artifacts_meta.append(
            {
                "artifact_id": str(uuid.uuid4()),
                "filename": dest_name,
                "relative_path": dest_name,
                "mime": mime,
                "byte_size": int(dest.stat().st_size),
                "previewable": is_previewable(mime, dest_name),
            }
        )

    manifest = write_run_manifest(
        chat_id=chat_id,
        run_id=rid,
        artifacts=artifacts_meta,
        tenant_id=tenant_id,
        worker_id=worker_id,
        exit_code=exit_code,
        created_at=now,
        expires_at=now + float(sandbox_artifact_ttl_s()),
    )
    return manifest


def _summarize_run(manifest: dict[str, Any]) -> dict[str, Any]:
    arts = manifest.get("artifacts") or []
    count = len(arts) if isinstance(arts, list) else 0
    return {
        "run_id": manifest.get("run_id"),
        "chat_id": manifest.get("chat_id"),
        "chat_session_id": manifest.get("chat_session_id"),
        "tenant_id": manifest.get("tenant_id"),
        "worker_id": manifest.get("worker_id"),
        "created_at": manifest.get("created_at"),
        "expires_at": manifest.get("expires_at"),
        "exit_code": manifest.get("exit_code"),
        "artifact_count": count,
    }


def list_runs(chat_id: str, limit: int = 20, *, base: Path | None = None) -> list[dict[str, Any]]:
    session = chat_session_dir(chat_id, base=base)
    if not session.is_dir():
        return []
    runs: list[dict[str, Any]] = []
    for run_path in session.iterdir():
        if not run_path.is_dir():
            continue
        manifest = _read_manifest(run_path)
        if manifest:
            runs.append(manifest)
    runs.sort(key=lambda m: float(m.get("created_at") or 0), reverse=True)
    cap = max(1, int(limit))
    return runs[:cap]


def list_runs_for_chat(chat_id: str, limit: int = 20, *, base: Path | None = None) -> list[dict[str, Any]]:
    return [_summarize_run(m) for m in list_runs(chat_id, limit=limit, base=base)]


def get_run(run_id: str, chat_id: str, *, base: Path | None = None) -> dict[str, Any] | None:
    rid = (run_id or "").strip()
    if not rid:
        return None
    manifest = _read_manifest(chat_session_dir(chat_id, base=base) / rid)
    if not manifest:
        return None
    if str(manifest.get("run_id") or "").strip() != rid:
        return None
    return manifest


def get_run_detail(chat_id: str, run_id: str, *, base: Path | None = None) -> dict[str, Any]:
    manifest = get_run(run_id, chat_id, base=base)
    if not manifest:
        raise RunNotFoundError(f"run not found: {run_id}")
    return manifest


def find_artifact(
    chat_id: str,
    artifact_id: str,
    *,
    base: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    aid = (artifact_id or "").strip()
    if not aid:
        raise ArtifactNotFoundError("artifact_id required")
    session = chat_session_dir(chat_id, base=base)
    if not session.is_dir():
        raise ArtifactNotFoundError(f"artifact not found: {aid}")
    for run_path in session.iterdir():
        if not run_path.is_dir():
            continue
        manifest = _read_manifest(run_path)
        if not manifest:
            continue
        for art in manifest.get("artifacts") or []:
            if not isinstance(art, dict):
                continue
            if str(art.get("artifact_id") or "").strip() != aid:
                continue
            rel = str(art.get("relative_path") or art.get("filename") or "").strip()
            try:
                path = _safe_artifact_path(run_path, rel)
            except PathTraversalError:
                raise
            if not path.is_file():
                raise ArtifactNotFoundError(f"artifact file missing: {aid}")
            return manifest, art, path
    raise ArtifactNotFoundError(f"artifact not found: {aid}")


def resolve_artifact(
    artifact_id: str,
    chat_id: str,
    *,
    base: Path | None = None,
) -> tuple[Path, dict[str, Any]]:
    manifest, art, path = find_artifact(chat_id, artifact_id, base=base)
    run_dir = chat_session_dir(chat_id, base=base) / str(manifest.get("run_id") or "")
    return run_dir, art


def read_artifact_bytes(
    artifact_id: str,
    chat_id: str,
    *,
    base: Path | None = None,
) -> tuple[bytes, str, str]:
    """Devuelve (bytes, mime, filename) para descarga."""
    _manifest, art, path = find_artifact(chat_id, artifact_id, base=base)
    mime = str(art.get("mime") or _detect_mime(path))
    filename = str(art.get("filename") or path.name)
    return path.read_bytes(), mime, filename


def preview_content(path: Path, *, mime: str, filename: str) -> PreviewResult:
    """Preview según MIME para el router admin."""
    m = (mime or "").lower()
    name = (filename or path.name).lower()

    if m.startswith("image/"):
        data = path.read_bytes()
        return PreviewResult(kind="binary", mime=m or _detect_mime(path), data=data)

    if m.startswith("text/") or name.endswith(".md"):
        text = path.read_text(encoding="utf-8", errors="replace")
        if len(text) > _PREVIEW_TEXT_MAX_CHARS:
            text = text[:_PREVIEW_TEXT_MAX_CHARS] + "\n… [truncado]"
        preview_kind = "markdown" if name.endswith(".md") or m == "text/markdown" else "text"
        return PreviewResult(
            kind="json",
            payload={"preview_kind": preview_kind, "content": text, "filename": path.name},
        )

    if name.endswith(".csv") or m == "text/csv":
        rows: list[dict[str, str]] = []
        with path.open(encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh)
            for i, row in enumerate(reader):
                if i >= _PREVIEW_CSV_MAX_ROWS:
                    break
                rows.append({k: (v if v is not None else "") for k, v in row.items()})
        return PreviewResult(
            kind="json",
            payload={"preview_kind": "csv", "rows": rows, "filename": path.name},
        )

    if name.endswith(".json") or m == "application/json":
        try:
            obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
            pretty = json.dumps(obj, ensure_ascii=False, indent=2)
        except json.JSONDecodeError:
            pretty = path.read_text(encoding="utf-8", errors="replace")
        if len(pretty) > _PREVIEW_JSON_MAX_CHARS:
            pretty = pretty[:_PREVIEW_JSON_MAX_CHARS] + "\n… [truncado]"
        return PreviewResult(
            kind="json",
            payload={"preview_kind": "json", "content": pretty, "filename": path.name},
        )

    if name.endswith(".parquet"):
        try:
            import pyarrow.parquet as pq  # noqa: PLC0415

            table = pq.read_table(path)
            schema = [{"name": f.name, "type": str(f.type)} for f in table.schema]
            preview_rows = table.slice(0, _PREVIEW_PARQUET_MAX_ROWS).to_pylist()
            return PreviewResult(
                kind="json",
                payload={
                    "preview_kind": "parquet",
                    "schema": schema,
                    "rows": preview_rows,
                    "filename": path.name,
                },
            )
        except Exception as exc:
            raise PreviewNotSupportedError(str(exc)) from exc

    if name.endswith(".docx"):
        text = _docx_preview_text(path)
        if text is None:
            raise PreviewNotSupportedError("docx preview unavailable")
        return PreviewResult(
            kind="json",
            payload={"preview_kind": "text", "content": text, "filename": path.name},
        )

    raise PreviewNotSupportedError(f"preview not supported for {filename}")


def _docx_preview_text(path: Path) -> str | None:
    try:
        from duckclaw.document_toolbox.extract import extract_document_text_from_path

        text, _fmt = extract_document_text_from_path(path)
    except Exception:
        try:
            from markitdown import MarkItDown  # noqa: PLC0415

            text = MarkItDown().convert(str(path)).text_content or ""
        except Exception as exc:
            _log.debug("docx preview failed %s: %s", path, exc)
            return None
    if len(text) > _PREVIEW_TEXT_MAX_CHARS:
        text = text[:_PREVIEW_TEXT_MAX_CHARS] + "\n… [truncado]"
    return text


def preview_artifact(
    artifact_id: str,
    chat_id: str,
    *,
    base: Path | None = None,
) -> dict[str, Any] | None:
    """Preview legacy (dict) usado por tests unitarios del registry."""
    try:
        _manifest, art, path = find_artifact(chat_id, artifact_id, base=base)
    except ArtifactNotFoundError:
        raise
    if not art.get("previewable"):
        return None
    mime = str(art.get("mime") or _detect_mime(path))
    filename = str(art.get("filename") or path.name)
    try:
        result = preview_content(path, mime=mime, filename=filename)
    except PreviewNotSupportedError:
        return None
    if result.kind == "binary":
        import base64

        return {
            "kind": "image",
            "mime": result.mime,
            "filename": path.name,
            "data_base64": base64.standard_b64encode(result.data).decode("ascii"),
        }
    payload = result.payload or {}
    if payload.get("preview_kind") == "markdown":
        return {"kind": "text", "mime": mime, "filename": path.name, "text": payload.get("content", "")}
    if payload.get("preview_kind") == "text":
        return {"kind": "text", "mime": mime, "filename": path.name, "text": payload.get("content", "")}
    if payload.get("preview_kind") == "csv":
        return {"kind": "csv", "mime": mime, "filename": path.name, "rows": payload.get("rows", [])}
    if payload.get("preview_kind") == "json":
        return {"kind": "json", "mime": mime, "filename": path.name, "text": payload.get("content", "")}
    if payload.get("preview_kind") == "parquet":
        return {
            "kind": "parquet",
            "mime": mime,
            "filename": path.name,
            "schema": payload.get("schema", []),
            "rows": payload.get("rows", []),
        }
    if payload.get("preview_kind") == "text" and filename.endswith(".docx"):
        return {"kind": "docx", "mime": mime, "filename": path.name, "text": payload.get("content", "")}
    return None


def purge_expired_runs(*, base: Path | None = None) -> dict[str, Any]:
    """Elimina directorios ``run_id`` cuyo ``expires_at`` del manifest ya pasó."""
    root = artifacts_base(base=base)
    if not root.is_dir():
        return {"purged": 0, "run_ids": []}
    now = time.time()
    purged_ids: list[str] = []
    for session_dir in root.iterdir():
        if not session_dir.is_dir():
            continue
        for run_dir in session_dir.iterdir():
            if not run_dir.is_dir():
                continue
            manifest = _read_manifest(run_dir)
            if not manifest:
                continue
            try:
                expires_at = float(manifest.get("expires_at") or 0)
            except (TypeError, ValueError):
                expires_at = 0.0
            if expires_at > 0 and now >= expires_at:
                rid = str(manifest.get("run_id") or run_dir.name)
                shutil.rmtree(run_dir, ignore_errors=True)
                purged_ids.append(rid)
    return {"purged": len(purged_ids), "run_ids": purged_ids}


def list_all_runs(
    limit: int = 50,
    *,
    chat_id_filter: str = "",
    base: Path | None = None,
) -> list[dict[str, Any]]:
    """Lista runs de todas las sesiones chat (vista global del workspace sandbox)."""
    root = artifacts_base(base=base)
    if not root.is_dir():
        return []
    filter_cid = (chat_id_filter or "").strip()
    runs: list[dict[str, Any]] = []
    for session_dir in root.iterdir():
        if not session_dir.is_dir():
            continue
        for run_dir in session_dir.iterdir():
            if not run_dir.is_dir():
                continue
            manifest = _read_manifest(run_dir)
            if not manifest:
                continue
            if filter_cid and str(manifest.get("chat_id") or "").strip() != filter_cid:
                continue
            runs.append(_summarize_run(manifest))
    runs.sort(key=lambda m: float(m.get("created_at") or 0), reverse=True)
    return runs[: max(1, int(limit))]


def find_artifact_global(
    artifact_id: str,
    *,
    base: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    """Busca un artefacto en cualquier sesión (admin workspace)."""
    aid = (artifact_id or "").strip()
    if not aid:
        raise ArtifactNotFoundError("artifact_id required")
    root = artifacts_base(base=base)
    if not root.is_dir():
        raise ArtifactNotFoundError(f"artifact not found: {aid}")
    for session_dir in root.iterdir():
        if not session_dir.is_dir():
            continue
        for run_dir in session_dir.iterdir():
            if not run_dir.is_dir():
                continue
            manifest = _read_manifest(run_dir)
            if not manifest:
                continue
            for art in manifest.get("artifacts") or []:
                if not isinstance(art, dict):
                    continue
                if str(art.get("artifact_id") or "").strip() != aid:
                    continue
                rel = str(art.get("relative_path") or art.get("filename") or "").strip()
                path = _safe_artifact_path(run_dir, rel)
                if not path.is_file():
                    raise ArtifactNotFoundError(f"artifact file missing: {aid}")
                return manifest, art, path
    raise ArtifactNotFoundError(f"artifact not found: {aid}")


def _resolve_artifact_lookup(
    artifact_id: str,
    chat_id: str,
    *,
    base: Path | None = None,
) -> tuple[dict[str, Any], dict[str, Any], Path]:
    cid = (chat_id or "").strip()
    if cid:
        return find_artifact(cid, artifact_id, base=base)
    return find_artifact_global(artifact_id, base=base)


def delete_run(
    run_id: str,
    chat_id: str,
    *,
    base: Path | None = None,
) -> dict[str, Any]:
    """Elimina un run completo (directorio + manifest)."""
    rid = (run_id or "").strip()
    if not rid:
        raise ValueError("run_id required")
    run_dir = chat_session_dir(chat_id, base=base) / rid
    if not run_dir.is_dir():
        raise RunNotFoundError(f"run not found: {rid}")
    shutil.rmtree(run_dir, ignore_errors=True)
    return {"deleted": True, "run_id": rid, "chat_id": chat_id}


def delete_artifact(
    artifact_id: str,
    chat_id: str = "",
    *,
    base: Path | None = None,
) -> dict[str, Any]:
    """Elimina un artefacto del scratch y actualiza el manifest."""
    manifest, art, path = _resolve_artifact_lookup(artifact_id, chat_id, base=base)
    cid = str(manifest.get("chat_id") or chat_id or "").strip()
    rid = str(manifest.get("run_id") or "").strip()
    run_dir = chat_session_dir(cid, base=base) / rid
    path.unlink(missing_ok=True)
    remaining = [
        a
        for a in (manifest.get("artifacts") or [])
        if isinstance(a, dict) and str(a.get("artifact_id") or "").strip() != artifact_id.strip()
    ]
    if not remaining:
        shutil.rmtree(run_dir, ignore_errors=True)
        return {
            "deleted": True,
            "artifact_id": artifact_id,
            "run_removed": True,
            "run_id": rid,
            "chat_id": cid,
        }
    manifest["artifacts"] = remaining
    _write_manifest_file(run_dir, manifest)
    return {
        "deleted": True,
        "artifact_id": artifact_id,
        "run_removed": False,
        "run_id": rid,
        "chat_id": cid,
    }


def promote_artifact_to_output(
    artifact_id: str,
    chat_id: str = "",
    *,
    relative_dest: str = "",
    sync_rag: bool = True,
    tenant_id: str = "default",
    project_id: str = "",
    base: Path | None = None,
) -> dict[str, Any]:
    """Copia artefacto sandbox a KNOWLEDGE_OUTPUT_ROOTS (Drive/vault). Opcional RAG sync."""
    manifest, art, path = _resolve_artifact_lookup(artifact_id, chat_id, base=base)
    from duckclaw.forge.rag.knowledge_paths import resolve_knowledge_output_path

    filename = str(art.get("filename") or path.name)
    dest_rel = (relative_dest or "").strip().replace("\\", "/").lstrip("/")
    if not dest_rel:
        dest_rel = f"SandboxPromoted/{filename}"
    target = resolve_knowledge_output_path(relative_path=dest_rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(path, target)

    payload: dict[str, Any] = {
        "ok": True,
        "artifact_id": artifact_id,
        "source_filename": filename,
        "relative_path": dest_rel,
        "path": str(target),
        "byte_size": int(target.stat().st_size),
        "run_id": manifest.get("run_id"),
        "chat_id": manifest.get("chat_id"),
    }
    if sync_rag:
        try:
            from duckclaw.forge.rag.knowledge_auto_sync import auto_sync_enabled, sync_file_after_write

            if auto_sync_enabled():
                payload["rag_sync"] = sync_file_after_write(
                    file_path=target,
                    tenant_id=(tenant_id or "default").strip() or "default",
                    project_id=(project_id or "").strip(),
                )
            else:
                payload["rag_sync"] = {"synced": False, "reason": "auto_sync_disabled"}
        except Exception as exc:
            payload["rag_sync"] = {"synced": False, "reason": str(exc)}
    return payload
