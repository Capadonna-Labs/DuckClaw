"""Admin catalog: integration API keys (seed pack, DB-first)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from core.admin_identity import open_gateway_db
from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.integration_catalog import integration_catalog_api_payload
from routers.admin_domains.admin_common import actor_from_header, require_admin_key

router = APIRouter(prefix="/integrations", tags=["admin-integrations"])


@router.get("/catalog", dependencies=[Depends(require_admin_key)])
async def get_integration_catalog(actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    """Integration secrets catalog with effective configured status for the actor tenant."""
    with open_gateway_db(read_only=True) as db:
        profile = ensure_profile_for_user(db, email=actor)
        return integration_catalog_api_payload(
            db,
            tenant_id=str(profile.get("tenant_id") or "default"),
            actor_email=str(profile.get("email") or actor),
        )
