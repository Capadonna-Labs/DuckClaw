"""Write handlers for productivity artifact index."""
from __future__ import annotations

from typing import Any


def _apply_upsert_productivity_artifact(conn: Any, payload: dict) -> None:
    artifact_id = str(payload.get("artifact_id") or "").strip()
    if not artifact_id:
        raise ValueError("artifact_id requerido")
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    owner = str(payload.get("owner_email") or payload.get("actor_email") or "system").strip() or "system"
    lane = str(payload.get("lane") or "storage").strip().lower() or "storage"
    if lane not in ("storage", "vault", "report"):
        raise ValueError(f"lane inválido: {lane}")
    title = str(payload.get("title") or payload.get("filename") or artifact_id).strip()
    filename = str(payload.get("filename") or "").strip()
    uri = str(payload.get("uri") or "").strip()
    source_kind = str(payload.get("source_kind") or "").strip()
    source_ref = str(payload.get("source_ref") or "").strip()
    mime = str(payload.get("mime") or "").strip()
    byte_size = int(payload.get("byte_size") or 0)

    existing = conn.execute(
        "SELECT artifact_id FROM main.admin_productivity_artifacts WHERE artifact_id = ?",
        [artifact_id],
    ).fetchone()
    if existing:
        conn.execute(
            """
            UPDATE main.admin_productivity_artifacts
            SET tenant_id = ?, owner_email = ?, lane = ?, title = ?, filename = ?, uri = ?,
                source_kind = ?, source_ref = ?, mime = ?, byte_size = ?, active = true,
                updated_at = CURRENT_TIMESTAMP
            WHERE artifact_id = ?
            """,
            [
                tenant_id,
                owner,
                lane,
                title,
                filename,
                uri,
                source_kind,
                source_ref,
                mime,
                byte_size,
                artifact_id,
            ],
        )
    else:
        conn.execute(
            """
            INSERT INTO main.admin_productivity_artifacts
            (artifact_id, tenant_id, owner_email, lane, title, filename, uri,
             source_kind, source_ref, mime, byte_size, active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, true)
            """,
            [
                artifact_id,
                tenant_id,
                owner,
                lane,
                title,
                filename,
                uri,
                source_kind,
                source_ref,
                mime,
                byte_size,
            ],
        )


def _apply_soft_delete_productivity_artifact(conn: Any, payload: dict) -> None:
    artifact_id = str(payload.get("artifact_id") or "").strip()
    tenant_id = str(payload.get("tenant_id") or "default").strip() or "default"
    actor = str(payload.get("actor_email") or "system").strip().lower() or "system"
    if not artifact_id:
        raise ValueError("artifact_id requerido")

    row = conn.execute(
        """
        SELECT artifact_id, owner_email, lane, uri, active
        FROM main.admin_productivity_artifacts
        WHERE artifact_id = ? AND tenant_id = ?
        LIMIT 1
        """,
        [artifact_id, tenant_id],
    ).fetchone()
    if not row or not row[4]:
        raise ValueError(f"Artefacto no encontrado: {artifact_id}")
    owner = str(row[1] or "").strip().lower()
    if owner and owner != actor and owner != "system":
        raise ValueError("Solo el propietario puede eliminar el artefacto")

    lane = str(row[2] or "")
    uri = str(row[3] or "")
    conn.execute(
        """
        UPDATE main.admin_productivity_artifacts
        SET active = false, updated_at = CURRENT_TIMESTAMP
        WHERE artifact_id = ? AND tenant_id = ?
        """,
        [artifact_id, tenant_id],
    )
    if lane == "storage" and uri:
        try:
            from duckclaw.productivity_artifacts import unlink_storage_uri

            unlink_storage_uri(uri)
        except Exception:
            pass


from duckclaw.write_handlers.registry import register_handler

register_handler("upsert_productivity_artifact", _apply_upsert_productivity_artifact)
register_handler("soft_delete_productivity_artifact", _apply_soft_delete_productivity_artifact)
