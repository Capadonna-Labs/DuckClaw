from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from pydantic import BaseModel, Field

from duckclaw import db_write_queue
from duckclaw.write_commands import DropLegacyDuckDbObjectsCommand

router = APIRouter(prefix="/duckdb", tags=["admin-duckdb"])

_REPO_ROOT = Path(__file__).resolve().parents[4]
_DUCKDB_EXPLORER_LEGACY_MAIN_TABLES = frozenset()
_DROP_LEGACY_SCHEMAS_CONFIRM = "DROP_LEGACY_SCHEMAS"


class DuckdbQueryBody(BaseModel):
    query: str = Field(..., min_length=1)
    vault_path: str | None = None


class DuckdbVectorSearchBody(BaseModel):
    query: str = ""
    limit: int = Field(default=10, ge=1, le=40)
    vault_path: str | None = None


class DuckdbLegacySchemaDropBody(BaseModel):
    schemas: list[str] = Field(default_factory=list)
    main_tables: list[str] = Field(default_factory=list)
    vault_path: str | None = None
    confirm: str = ""


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    expected = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DUCKCLAW_ADMIN_API_KEY no configurada en el gateway",
        )
    if (x_admin_key or "").strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin key inválida")


def actor_from_header(x_actor: str | None = Header(None, alias="X-Duckclaw-Actor")) -> str:
    raw = (x_actor or "").strip()[:128]
    if raw and raw != "admin-ui":
        return raw
    admin_email = os.environ.get("DUCKCLAW_ADMIN_EMAIL", "").strip()
    if admin_email and "@" in admin_email:
        return admin_email[:128]
    return raw or "admin-ui"


def _repo_root() -> Path:
    raw = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    return Path(raw) if raw else _REPO_ROOT


def _problem(status_code: int, title: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"type": "about:blank", "title": title, "status": status_code, "detail": detail},
    )


def _admin_audit(
    action: str,
    resource: str,
    detail: str,
    *,
    actor: str = "admin-ui",
    meta: dict[str, Any] | None = None,
) -> None:
    from routers import admin as admin_router

    admin_router._admin_audit(action, resource, detail, actor=actor, meta=meta)


def _gateway_effective_tenant_id(request_tenant: str | None) -> str:
    from routers import admin as admin_router

    return admin_router._gateway_effective_tenant_id(request_tenant)


def _default_vault_user_id(vault_user_id: str | None = None) -> str:
    from routers import admin as admin_router

    return admin_router._playground_telegram_user_id(vault_user_id) or "default"


def _quote_duckdb_ident(value: str) -> str:
    ident = (value or "").strip()
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", ident):
        raise ValueError(f"Identificador inválido: {value}")
    return '"' + ident.replace('"', '""') + '"'


def _duckdb_explorer_legacy_schema_names(
    *,
    tenant_id: str | None = None,
    actor_email: str | None = None,
) -> set[str]:
    """Schemas legacy configurados explícitamente; DB-first con fallback env."""
    raw = os.environ.get("DUCKCLAW_ADMIN_DUCKDB_LEGACY_SCHEMAS", "")
    if tenant_id and actor_email:
        try:
            from core.admin_identity import open_gateway_db
            from duckclaw.admin_runtime_settings import resolve_runtime_setting

            with open_gateway_db(read_only=True) as db:
                resolved = resolve_runtime_setting(
                    db,
                    tenant_id=tenant_id,
                    actor_email=actor_email,
                    domain="duckdb",
                    key="legacy_schemas",
                    env_key="DUCKCLAW_ADMIN_DUCKDB_LEGACY_SCHEMAS",
                    default="",
                )
            raw = str(resolved.get("value") or raw or "")
        except Exception:
            raw = os.environ.get("DUCKCLAW_ADMIN_DUCKDB_LEGACY_SCHEMAS", "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def _duckdb_explorer_legacy_main_table_names(
    *,
    tenant_id: str | None = None,
    actor_email: str | None = None,
) -> set[str]:
    """Main tables configured for cleanup; DB-first with env fallback."""
    raw = os.environ.get("DUCKCLAW_ADMIN_DUCKDB_LEGACY_MAIN_TABLES", "")
    if tenant_id and actor_email:
        try:
            from core.admin_identity import open_gateway_db
            from duckclaw.admin_runtime_settings import resolve_runtime_setting

            with open_gateway_db(read_only=True) as db:
                resolved = resolve_runtime_setting(
                    db,
                    tenant_id=tenant_id,
                    actor_email=actor_email,
                    domain="duckdb",
                    key="legacy_main_tables",
                    env_key="DUCKCLAW_ADMIN_DUCKDB_LEGACY_MAIN_TABLES",
                    default="",
                )
            raw = str(resolved.get("value") or raw or "")
        except Exception:
            raw = os.environ.get("DUCKCLAW_ADMIN_DUCKDB_LEGACY_MAIN_TABLES", "")
    configured = {item.strip().lower() for item in raw.split(",") if item.strip()}
    return set(_DUCKDB_EXPLORER_LEGACY_MAIN_TABLES) | configured


def _duckdb_actor_scope(actor: str | None, vault_uid: str) -> dict[str, str]:
    actor_email = (actor or "admin-ui").strip().lower() or "admin-ui"
    tenant_id = _gateway_effective_tenant_id("default")
    if "@" in actor_email:
        from duckclaw.admin_user_profiles import tenant_id_for_email

        tenant_id = tenant_id_for_email(actor_email)
        try:
            from core.admin_identity import open_gateway_db
            from duckclaw.admin_user_profiles import ensure_profile_for_user

            with open_gateway_db(read_only=True) as db:
                profile = ensure_profile_for_user(db, email=actor_email)
            tenant_id = str(profile.get("tenant_id") or tenant_id)
        except Exception:
            pass
    return {
        "actor_email": actor_email,
        "vault_user_id": vault_uid,
        "tenant_id": tenant_id,
    }


def _duckdb_readonly_session(vault_path: str | None, *, actor: str | None = None):
    from core.admin_duckdb_readonly import connect_readonly, resolve_vault_path
    from core.admin_identity import (
        resolve_actor_default_vault_path,
        validate_vault_path_for_actor,
        vault_user_id_for_actor,
    )

    vault_uid = ""
    raw_vp = (vault_path or "").strip()
    if raw_vp:
        if actor and actor != "admin-ui":
            path = validate_vault_path_for_actor(actor, raw_vp)
            vault_uid = vault_user_id_for_actor(actor)
        else:
            path = resolve_vault_path(raw_vp)
            vault_uid = _default_vault_user_id()
    elif actor:
        path, vault_uid = resolve_actor_default_vault_path(actor)
    else:
        path = resolve_vault_path(vault_path)
        vault_uid = _default_vault_user_id()
    con = connect_readonly(path)
    return con, path, _duckdb_actor_scope(actor, vault_uid)


@router.get("/tables", dependencies=[Depends(require_admin_key)])
async def duckdb_list_tables(
    vault_path: str | None = Query(None, description="Ruta .duckdb; default gateway vault"),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_duckdb_readonly import fetch_table_catalog

    try:
        con, resolved, scope = _duckdb_readonly_session(vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise _problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        catalog = fetch_table_catalog(con)
        schemas = catalog.get("schemas") or {}
        table_count = sum(len(tables) for tables in schemas.values() if isinstance(tables, list))
        return {
            "vault_path": resolved,
            "vault_user_id": scope["vault_user_id"],
            "actor_email": scope["actor_email"],
            "tenant_id": scope["tenant_id"],
            "table_count": table_count,
            **catalog,
        }
    finally:
        con.close()


@router.post("/query", dependencies=[Depends(require_admin_key)])
async def duckdb_run_query(
    body: DuckdbQueryBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_duckdb_readonly import execute_select

    try:
        con, resolved, _scope = _duckdb_readonly_session(body.vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise _problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        try:
            result = execute_select(con, body.query)
        except ValueError as exc:
            raise _problem(400, "Consulta no permitida", str(exc)) from exc
        except Exception as exc:
            raise _problem(400, "Error SQL", str(exc)) from exc
        return {"vault_path": resolved, **result}
    finally:
        con.close()


@router.get("/legacy-schemas", dependencies=[Depends(require_admin_key)])
async def duckdb_legacy_schemas(
    vault_path: str | None = Query(None),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_duckdb_readonly import fetch_table_catalog

    try:
        con, resolved, scope = _duckdb_readonly_session(vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise _problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        catalog = fetch_table_catalog(con)
        schemas = catalog.get("schemas") or {}
        candidates = _duckdb_explorer_legacy_schema_names(
            tenant_id=scope["tenant_id"],
            actor_email=scope["actor_email"],
        )
        main_table_candidates = _duckdb_explorer_legacy_main_table_names(
            tenant_id=scope["tenant_id"],
            actor_email=scope["actor_email"],
        )
        out = [
            {
                "schema": str(schema),
                "table_count": len(tables) if isinstance(tables, list) else 0,
                "tables": list(tables) if isinstance(tables, list) else [],
            }
            for schema, tables in sorted(schemas.items())
            if str(schema).lower() in candidates
        ]
        main_tables = [
            {"schema": "main", "table": str(table)}
            for table in sorted(schemas.get("main") or [])
            if str(table).lower() in main_table_candidates
        ]
        return {
            "vault_path": resolved,
            "vault_user_id": scope["vault_user_id"],
            "actor_email": scope["actor_email"],
            "tenant_id": scope["tenant_id"],
            "schemas": out,
            "main_tables": main_tables,
            "confirm": _DROP_LEGACY_SCHEMAS_CONFIRM,
        }
    finally:
        con.close()


@router.post("/legacy-schemas/drop", dependencies=[Depends(require_admin_key)])
async def duckdb_drop_legacy_schemas(
    body: DuckdbLegacySchemaDropBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    if body.confirm != _DROP_LEGACY_SCHEMAS_CONFIRM:
        raise _problem(400, "Confirmación requerida", _DROP_LEGACY_SCHEMAS_CONFIRM)
    try:
        con, resolved, scope = _duckdb_readonly_session(body.vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise _problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        candidates = _duckdb_explorer_legacy_schema_names(
            tenant_id=scope["tenant_id"],
            actor_email=scope["actor_email"],
        )
        main_table_candidates = _duckdb_explorer_legacy_main_table_names(
            tenant_id=scope["tenant_id"],
            actor_email=scope["actor_email"],
        )
        requested = []
        for raw in body.schemas:
            schema = (raw or "").strip().lower()
            if not schema:
                continue
            if schema not in candidates:
                raise _problem(400, "Schema no permitido para cleanup legacy", schema)
            requested.append(schema)
        requested = sorted(set(requested))
        requested_main_tables = []
        for raw in body.main_tables:
            table = (raw or "").strip().lower()
            if not table:
                continue
            if table not in main_table_candidates:
                raise _problem(400, "Tabla main no permitida para cleanup legacy", table)
            requested_main_tables.append(table)
        requested_main_tables = sorted(set(requested_main_tables))
        if not requested and not requested_main_tables:
            raise _problem(400, "cleanup vacío", "Selecciona al menos un schema o tabla main legacy")
        existing = {
            str(row[0]).lower()
            for row in con.execute(
                "SELECT schema_name FROM information_schema.schemata"
            ).fetchall()
        }
        existing_main_tables = {
            str(row[0]).lower()
            for row in con.execute(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
            ).fetchall()
        }
    finally:
        con.close()
    dropped = [schema for schema in requested if schema in existing]
    dropped_main_tables = [table for table in requested_main_tables if table in existing_main_tables]
    command = DropLegacyDuckDbObjectsCommand(
        tenant_id=scope["tenant_id"],
        actor_email=scope["actor_email"],
        user_id=scope["vault_user_id"],
        db_path=resolved,
        schemas=dropped,
        main_tables=dropped_main_tables,
    )
    task_id = db_write_queue.enqueue_typed_command(command, db_path=resolved, user_id=scope["vault_user_id"])
    command_status = db_write_queue.poll_task_status_sync(task_id, timeout_sec=0.5, interval_sec=0.05)
    if command_status and command_status.status == "failed":
        raise _problem(400, "Cleanup legacy rechazado por DB-writer", command_status.detail or task_id)
    _admin_audit(
        "duckdb.legacy_schema.drop",
        resolved,
        ",".join(dropped + [f"main.{table}" for table in dropped_main_tables]),
        actor=actor,
        meta={
            "tenant_id": scope["tenant_id"],
            "schemas": dropped,
            "main_tables": dropped_main_tables,
            "task_id": task_id,
        },
    )
    return {
        "ok": True,
        "task_id": task_id,
        "vault_path": resolved,
        "vault_user_id": scope["vault_user_id"],
        "tenant_id": scope["tenant_id"],
        "dropped": dropped,
        "dropped_main_tables": dropped_main_tables,
    }


@router.get("/pgq-graph", dependencies=[Depends(require_admin_key)])
async def duckdb_pgq_graph(
    vault_path: str | None = Query(None),
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_duckdb_readonly import fetch_pgq_graph

    try:
        con, resolved, _scope = _duckdb_readonly_session(vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise _problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        graph = fetch_pgq_graph(con)
        return {"vault_path": resolved, **graph}
    finally:
        con.close()


@router.post("/vector-search", dependencies=[Depends(require_admin_key)])
async def duckdb_vector_search(
    body: DuckdbVectorSearchBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_duckdb_readonly import (
        SemanticMemoryNotInitializedError,
        run_vector_search,
    )

    try:
        con, resolved, _scope = _duckdb_readonly_session(body.vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise _problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        try:
            payload = run_vector_search(con, body.query, body.limit)
        except SemanticMemoryNotInitializedError as exc:
            raise _problem(400, "Memoria vectorial no inicializada", str(exc)) from exc
        except Exception as exc:
            raise _problem(400, "Error en búsqueda vectorial", str(exc)) from exc
        return {"vault_path": resolved, **payload}
    finally:
        con.close()
