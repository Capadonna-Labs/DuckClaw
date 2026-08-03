from __future__ import annotations

import asyncio
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import HTMLResponse
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
    limit: int | None = Field(default=None, ge=1, le=500)
    offset: int | None = Field(default=None, ge=0)


class DuckdbVectorSearchBody(BaseModel):
    query: str = ""
    limit: int = Field(default=10, ge=1, le=40)
    vault_path: str | None = None


class DuckdbPgqVaultBody(BaseModel):
    vault_path: str | None = None


_PGQ_HTML_CSP = (
    "default-src 'self' https: data:; "
    "script-src 'self' https: cdn.jsdelivr.net cdnjs.cloudflare.com unpkg.com 'unsafe-inline'; "
    "style-src 'self' https: 'unsafe-inline'"
)

_PGQ_HTML_PLACEHOLDER = """<!DOCTYPE html>
<html lang="es">
<head><meta charset="utf-8"><title>Grafo PGQ</title></head>
<body style="font-family:system-ui;padding:2rem;color:#334155;background:#0f172a;color:#e2e8f0">
<h3>Grafo HTML no generado</h3>
<p>Pulsa <strong>Actualizar grafo</strong> en el panel PGQ para exportar la memoria a HTML.</p>
</body></html>"""


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


def _duckdb_writable_session(vault_path: str | None, *, actor: str | None = None):
    from routers.admin import _open_playground_vault_db

    _con, path, scope = _duckdb_readonly_session(vault_path, actor=actor)
    _con.close()
    db = _open_playground_vault_db(path, read_only=False)
    return db, path, scope


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
    from core.admin_duckdb_readonly import (
        classify_admin_explorer_sql,
        execute_admin_dml,
        execute_select,
    )

    try:
        sql_kind = classify_admin_explorer_sql(body.query)
    except ValueError as exc:
        raise _problem(400, "Consulta no permitida", str(exc)) from exc

    try:
        con, resolved, scope = _duckdb_readonly_session(body.vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise _problem(403, "Vault no autorizado", str(exc)) from exc

    if sql_kind == "write":
        con.close()
        try:
            result = execute_admin_dml(
                resolved,
                body.query,
                vault_user_id=scope["vault_user_id"],
                tenant_id=scope["tenant_id"],
            )
        except ValueError as exc:
            raise _problem(400, "Escritura no permitida", str(exc)) from exc
        except Exception as exc:
            raise _problem(400, "Error SQL", str(exc)) from exc
        _admin_audit(
            "duckdb.query.write",
            resolved,
            body.query.strip()[:500],
            actor=actor,
            meta={
                "tenant_id": scope["tenant_id"],
                "task_id": result.get("task_id"),
                "vault_user_id": scope["vault_user_id"],
            },
        )
        return {"vault_path": resolved, **result}

    try:
        try:
            result = execute_select(con, body.query, limit=body.limit, offset=body.offset)
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
    from duckclaw.db_write_queue import enqueue_typed_command

    task_id = enqueue_typed_command(command, db_path=resolved, user_id=scope["vault_user_id"])
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


@router.post("/pgq/bootstrap", dependencies=[Depends(require_admin_key)])
async def duckdb_pgq_bootstrap(
    body: DuckdbPgqVaultBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.admin_duckdb_readonly import _table_exists
    from duckclaw.graphs.graph_rag import ensure_graph_rag_schema

    try:
        db, resolved, scope = _duckdb_writable_session(body.vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise _problem(403, "Vault no autorizado", str(exc)) from exc
    try:
        had_nodes = _table_exists(db, "memory_nodes")
        had_edges = _table_exists(db, "memory_edges")
        pgq_available = ensure_graph_rag_schema(db)
        tables_created = [
            name
            for name, existed in (("memory_nodes", had_nodes), ("memory_edges", had_edges))
            if not existed
        ]
    finally:
        try:
            db.close()
        except Exception:
            pass

    _admin_audit(
        "duckdb.pgq.bootstrap",
        resolved,
        f"pgq_available={pgq_available}",
        actor=actor,
        meta={
            "tenant_id": scope["tenant_id"],
            "vault_user_id": scope["vault_user_id"],
            "tables_created": tables_created,
            "pgq_available": pgq_available,
        },
    )
    return {
        "ok": True,
        "vault_path": resolved,
        "pgq_available": pgq_available,
        "tables_created": tables_created,
    }


@router.post("/pgq/rebuild", dependencies=[Depends(require_admin_key)])
async def duckdb_pgq_rebuild(
    body: DuckdbPgqVaultBody,
    actor: str = Depends(actor_from_header),
) -> dict[str, Any]:
    from core.pgq_graph_cache import (
        memory_graph_generator_script,
        memory_graph_html_path,
        pgq_repo_root,
    )

    try:
        _con, resolved, scope = _duckdb_readonly_session(body.vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise _problem(403, "Vault no autorizado", str(exc)) from exc
    finally:
        _con.close()

    repo = pgq_repo_root()
    out_path = memory_graph_html_path(resolved)
    script = memory_graph_generator_script()

    def _run() -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [
                "uv",
                "run",
                "python",
                str(script),
                "--vault-path",
                resolved,
                "--out",
                str(out_path),
            ],
            cwd=str(repo),
            capture_output=True,
            text=True,
            timeout=120,
        )

    try:
        proc = await asyncio.to_thread(_run)
    except subprocess.TimeoutExpired:
        raise _problem(408, "Timeout generando grafo HTML", resolved) from None
    except Exception as exc:
        raise _problem(500, "Error generando grafo HTML", str(exc)) from exc

    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "generate_memory_graph failed")[-2000:]
        raise _problem(500, "Error generando grafo HTML", detail)

    _admin_audit(
        "duckdb.pgq.rebuild",
        resolved,
        str(out_path),
        actor=actor,
        meta={
            "tenant_id": scope["tenant_id"],
            "vault_user_id": scope["vault_user_id"],
            "html_path": str(out_path),
            "stdout": (proc.stdout or "")[-500:],
        },
    )
    return {
        "ok": True,
        "vault_path": resolved,
        "html_path": str(out_path),
        "cache_key": out_path.parent.name,
    }


@router.get("/pgq-graph/html", response_class=HTMLResponse, dependencies=[Depends(require_admin_key)])
async def duckdb_pgq_graph_html(
    vault_path: str | None = Query(None),
    _t: str | None = Query(None, description="Cache-bust token"),
    actor: str = Depends(actor_from_header),
) -> HTMLResponse:
    from core.pgq_graph_cache import memory_graph_html_path

    try:
        _con, resolved, _scope = _duckdb_readonly_session(vault_path, actor=actor)
    except FileNotFoundError as exc:
        raise _problem(404, "Vault no encontrado", str(exc)) from exc
    except PermissionError as exc:
        raise _problem(403, "Vault no autorizado", str(exc)) from exc
    finally:
        _con.close()

    html_path = memory_graph_html_path(resolved)
    if not html_path.is_file():
        return HTMLResponse(
            content=_PGQ_HTML_PLACEHOLDER,
            status_code=404,
            headers={"Content-Security-Policy": _PGQ_HTML_CSP},
        )

    html = html_path.read_text(encoding="utf-8")
    return HTMLResponse(content=html, headers={"Content-Security-Policy": _PGQ_HTML_CSP})


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
