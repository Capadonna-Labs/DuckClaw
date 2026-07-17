"""Productividad — bandeja unificada de artefactos del agente."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from routers.admin_domains.admin_common import actor_from_header, problem, require_admin_key

router = APIRouter(tags=["admin-productivity"])


def _actor_profile(actor: str) -> dict[str, str]:
    from core.admin_identity import open_gateway_db
    from duckclaw.admin_user_profiles import ensure_profile_for_user

    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)
    return {"tenant_id": str(profile["tenant_id"]), "email": str(profile["email"])}


def _enqueue(payload: dict[str, Any], *, actor_email: str) -> str:
    from duckclaw.db_write_queue import enqueue_dict_command
    from duckclaw.gateway_db import get_gateway_db_path

    return enqueue_dict_command(
        payload,
        db_path=get_gateway_db_path(),
        user_id=actor_email or "default",
    )


def _sql_fetchall(db: Any, sql: str, params: list[Any] | None = None) -> list[Any]:
    result = db.execute(sql, params) if params is not None else db.execute(sql)
    if isinstance(result, list):
        return result
    fetchall = getattr(result, "fetchall", None)
    if callable(fetchall):
        return fetchall()
    return list(result or [])


@router.get("/productivity/artifacts", dependencies=[Depends(require_admin_key)])
async def list_productivity_artifacts(
    lane: str = "",
    limit: int = 100,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    profile = _actor_profile(actor)
    tid = profile["tenant_id"]
    email = profile["email"]
    cap = max(1, min(int(limit), 200))
    lane_f = (lane or "").strip().lower()

    items: list[dict[str, Any]] = []
    from core.admin_identity import open_gateway_db

    with open_gateway_db(read_only=True) as db:
        try:
            params: list[Any] = [tid, email]
            lane_clause = ""
            if lane_f in ("storage", "vault", "report"):
                lane_clause = " AND lane = ?"
                params.append(lane_f)
            params.append(cap)
            rows = _sql_fetchall(
                db,
                f"""
                SELECT artifact_id, lane, title, filename, uri, source_kind, source_ref,
                       mime, byte_size, updated_at
                FROM main.admin_productivity_artifacts
                WHERE tenant_id = ?
                  AND active = true
                  AND (
                    lower(owner_email) = lower(?)
                    OR lower(owner_email) = 'system'
                  )
                  {lane_clause}
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                params,
            )
            for row in rows:
                items.append(
                    {
                        "artifact_id": str(row[0]),
                        "lane": str(row[1]),
                        "title": str(row[2]),
                        "filename": str(row[3] or ""),
                        "uri": str(row[4] or ""),
                        "source_kind": str(row[5] or ""),
                        "source_ref": str(row[6] or ""),
                        "mime": str(row[7] or ""),
                        "byte_size": int(row[8] or 0),
                        "updated_at": str(row[9] or ""),
                    }
                )
        except Exception:
            # Migración aún no aplicada
            items = []

        # Informes activos sin fila en índice (legacy)
        if lane_f in ("", "report"):
            known_refs = {i["source_ref"] for i in items if i["lane"] == "report"}
            try:
                from duckclaw.report_engine.admin_report_read import list_report_instances

                reports = list_report_instances(
                    db, tenant_id=tid, actor_email=email, limit=cap
                )
                for r in reports:
                    iid = str(r.get("instance_id") or "")
                    if not iid or iid in known_refs:
                        continue
                    items.append(
                        {
                            "artifact_id": f"prep_{iid}",
                            "lane": "report",
                            "title": str(r.get("title") or iid),
                            "filename": "",
                            "uri": str(r.get("rendered_docx_uri") or ""),
                            "source_kind": "report_engine",
                            "source_ref": iid,
                            "mime": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                            "byte_size": 0,
                            "updated_at": str(r.get("updated_at") or ""),
                            "progress_percent": (r.get("progress") or {}).get(
                                "completion_percent"
                            ),
                        }
                    )
            except Exception:
                pass

    items.sort(key=lambda x: str(x.get("updated_at") or ""), reverse=True)
    return {"artifacts": items[:cap], "count": len(items[:cap])}


@router.delete(
    "/productivity/artifacts/{artifact_id}",
    dependencies=[Depends(require_admin_key)],
)
async def delete_productivity_artifact(
    artifact_id: str,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    profile = _actor_profile(actor)
    aid = (artifact_id or "").strip()
    if not aid:
        raise problem(400, "artifact_id requerido", "productivity_artifact")

    # Informes: redirigir a soft_delete_report_instance
    if aid.startswith("prep_"):
        instance_id = aid[5:]
        from duckclaw.report_engine.admin_report_read import (
            actor_can_access_instance,
            get_report_instance,
        )
        from core.admin_identity import open_gateway_db

        with open_gateway_db(read_only=True) as db:
            instance = get_report_instance(
                db, instance_id=instance_id, tenant_id=profile["tenant_id"]
            )
            if not instance:
                raise problem(404, "Informe no encontrado", "report_instance")
            if not actor_can_access_instance(
                db, instance=instance, actor_email=profile["email"]
            ):
                raise HTTPException(status_code=403, detail="Acceso denegado")
        task_id = _enqueue(
            {
                "command_type": "soft_delete_report_instance",
                "instance_id": instance_id,
                "tenant_id": profile["tenant_id"],
                "actor_email": profile["email"],
            },
            actor_email=profile["email"],
        )
        return {"ok": True, "task_id": task_id, "artifact_id": aid, "lane": "report"}

    from core.admin_identity import open_gateway_db

    with open_gateway_db(read_only=True) as db:
        rows = _sql_fetchall(
            db,
            """
            SELECT artifact_id, owner_email, lane
            FROM main.admin_productivity_artifacts
            WHERE artifact_id = ? AND tenant_id = ? AND active = true
            LIMIT 1
            """,
            [aid, profile["tenant_id"]],
        )
        if not rows:
            raise problem(404, "Artefacto no encontrado", "productivity_artifact")
        owner = str(rows[0][1] or "").strip().lower()
        if owner not in (profile["email"].strip().lower(), "system", ""):
            raise HTTPException(status_code=403, detail="Solo el propietario puede eliminar")
        lane = str(rows[0][2] or "storage")

    task_id = _enqueue(
        {
            "command_type": "soft_delete_productivity_artifact",
            "artifact_id": aid,
            "tenant_id": profile["tenant_id"],
            "actor_email": profile["email"],
        },
        actor_email=profile["email"],
    )
    return {"ok": True, "task_id": task_id, "artifact_id": aid, "lane": lane}


class PromoteToVaultBody(BaseModel):
    relative_dir: str = "Productividad"
    remove_from_storage: bool = False


@router.post(
    "/productivity/artifacts/{artifact_id}/promote-to-vault",
    dependencies=[Depends(require_admin_key)],
)
async def promote_artifact_to_vault(
    artifact_id: str,
    body: PromoteToVaultBody | None = None,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.productivity_artifacts import promote_storage_file_to_vault

    profile = _actor_profile(actor)
    aid = (artifact_id or "").strip()
    if not aid:
        raise problem(400, "artifact_id requerido", "productivity_artifact")
    opts = body or PromoteToVaultBody()

    from core.admin_identity import open_gateway_db

    with open_gateway_db(read_only=True) as db:
        rows = _sql_fetchall(
            db,
            """
            SELECT artifact_id, owner_email, lane, uri, title, filename
            FROM main.admin_productivity_artifacts
            WHERE artifact_id = ? AND tenant_id = ? AND active = true
            LIMIT 1
            """,
            [aid, profile["tenant_id"]],
        )
        if not rows:
            raise problem(404, "Artefacto no encontrado", "productivity_artifact")
        owner = str(rows[0][1] or "").strip().lower()
        if owner not in (profile["email"].strip().lower(), "system", ""):
            raise HTTPException(status_code=403, detail="Solo el propietario puede promover")
        lane = str(rows[0][2] or "")
        if lane != "storage":
            raise problem(400, "Solo se pueden promover artefactos lane=storage", "productivity_artifact")
        uri = str(rows[0][3] or "")
        title = str(rows[0][4] or "")
        filename = str(rows[0][5] or "")

    try:
        result = promote_storage_file_to_vault(
            source_uri=uri,
            tenant_id=profile["tenant_id"],
            owner_email=profile["email"],
            title=title,
            filename=filename,
            relative_dir=(opts.relative_dir or "Productividad").strip() or "Productividad",
            remove_from_storage=bool(opts.remove_from_storage),
        )
    except ValueError as exc:
        raise problem(400, str(exc), "productivity_promote") from exc

    if opts.remove_from_storage:
        _enqueue(
            {
                "command_type": "soft_delete_productivity_artifact",
                "artifact_id": aid,
                "tenant_id": profile["tenant_id"],
                "actor_email": profile["email"],
            },
            actor_email=profile["email"],
        )

    return {"ok": True, "source_artifact_id": aid, **result}


class IndexVaultPathBody(BaseModel):
    path: str
    title: str = ""


@router.post("/productivity/vault/index", dependencies=[Depends(require_admin_key)])
async def index_vault_path(
    body: IndexVaultPathBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from duckclaw.forge.rag.knowledge_paths import knowledge_output_roots, path_under_any_root
    from duckclaw.productivity_artifacts import register_vault_artifact_from_path
    from pathlib import Path

    profile = _actor_profile(actor)
    raw = (body.path or "").strip()
    if not raw:
        raise problem(400, "path requerido", "productivity_vault")
    target = Path(raw).expanduser().resolve()
    roots = knowledge_output_roots()
    if not roots or not path_under_any_root(target, roots):
        raise problem(400, "Ruta fuera de OUTPUT_ROOTS", "productivity_vault")
    if not target.is_file():
        raise problem(400, "La ruta debe ser un archivo", "productivity_vault")

    indexed = register_vault_artifact_from_path(
        target,
        tenant_id=profile["tenant_id"],
        owner_email=profile["email"],
        source_kind="vault_browser",
        source_ref=str(target),
        title=(body.title or target.name).strip() or target.name,
    )
    if not indexed:
        raise problem(500, "No se pudo indexar", "productivity_vault")
    return {"ok": True, **indexed}


@router.get("/productivity/vault/browse", dependencies=[Depends(require_admin_key)])
async def browse_productivity_vault(path: str = "", files: str = "*") -> dict[str, Any]:
    """Browse OUTPUT_ROOTS (Finder del vault de salida). files=* lista todos los archivos."""
    from core.heavy_work import run_heavy_work
    from duckclaw.forge.rag.knowledge_paths import browse_knowledge_directories

    # files=* → todas las extensiones comunes; vacío → solo carpetas
    raw_files = (files or "").strip()
    if raw_files == "*":
        suffixes = ["*"]
    elif raw_files:
        suffixes = [part.strip() for part in raw_files.split(",") if part.strip()]
    else:
        suffixes = None

    try:
        return await run_heavy_work(
            lambda: browse_knowledge_directories(
                path,
                include_suffixes=suffixes,
                root_set="output",
            )
        )
    except Exception as exc:
        raise problem(400, str(exc), "productivity_vault_browse") from exc
