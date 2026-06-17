"""POST /api/v1/db/read — consultas SELECT read-only contra bóvedas DuckDB."""

from __future__ import annotations

import asyncio
from typing import Any

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from duckclaw.pm2_gateway_db import dedicated_gateway_db_path_resolved
from duckclaw.vaults import resolve_active_vault, validate_user_db_path, vault_scope_id_for_tenant

router = APIRouter(tags=["db"])


class ReadRequest(BaseModel):
    query: str = Field(..., description="Consulta SQL SELECT parametrizada")
    params: list = Field(default_factory=list, description="Parámetros para la consulta")
    tenant_id: str = Field(default="default", description="ID del tenant")
    user_id: str | None = Field(default=None, description="ID del usuario dueño de la bóveda")
    db_path: str | None = Field(default=None, description="Ruta DuckDB (solo lectura)")


def resolve_db_path_for_vault(req: ReadRequest) -> str:
    """Resuelve db_path para consultas read-only internas."""
    user_id = (req.user_id or "").strip() or "default"
    db_path = (req.db_path or "").strip()
    tid = (req.tenant_id or "").strip() or None
    if not db_path:
        ded = dedicated_gateway_db_path_resolved()
        if ded:
            db_path = ded
        else:
            t_eff = str(tid or "default").strip() or "default"
            _, db_path = resolve_active_vault(user_id, vault_scope_id_for_tenant(t_eff))
    return db_path


@router.post("/api/v1/db/read")
async def db_read(req: ReadRequest) -> dict[str, Any]:
    """Ejecuta SELECT en DuckDB en solo lectura para clientes internos."""
    q = (req.query or "").strip()
    if not q.upper().startswith("SELECT"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Solo se permiten consultas SELECT.",
        )
    user_id = (req.user_id or "").strip() or "default"
    tid = (req.tenant_id or "").strip() or None
    db_path = resolve_db_path_for_vault(req)
    if not validate_user_db_path(user_id, db_path, tenant_id=tid):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="db_path inválido para el usuario.",
        )
    from core.gateway_acl_db import get_gateway_acl_duckdb
    from duckclaw.shared_db_grants import path_is_under_shared_tree, user_may_access_shared_path

    if path_is_under_shared_tree(db_path) and not user_may_access_shared_path(
        get_gateway_acl_duckdb()[0],
        tenant_id=str(tid or "default").strip() or "default",
        user_id=user_id,
        shared_db_path=db_path,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sin permiso para leer esta base de datos compartida.",
        )

    def _exec_read() -> list[dict[str, Any]]:
        from duckclaw.duckdb_read_compat import duckdb_connect_read_with_rw_fallback

        con = duckdb_connect_read_with_rw_fallback(db_path)
        try:
            cur = con.execute(q, req.params or [])
            desc = cur.description
            cols = [d[0] for d in desc] if desc else []
            rows_raw = cur.fetchall()
            out: list[dict[str, Any]] = []
            for row in rows_raw:
                out.append({cols[i]: row[i] for i in range(len(cols))})
            return out
        finally:
            con.close()

    try:
        rows = await asyncio.to_thread(_exec_read)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e
    return {"rows": rows}
