from __future__ import annotations

import json
import os
from typing import Any

from fastapi import APIRouter, Depends, Header, HTTPException, status

router = APIRouter(prefix="/devices", tags=["admin-devices"])


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    expected = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DUCKCLAW_ADMIN_API_KEY no configurada en el gateway",
        )
    if (x_admin_key or "").strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin key inválida")


@router.get("/android-status", dependencies=[Depends(require_admin_key)])
async def android_device_status() -> dict[str, Any]:
    from duckclaw.mcp_android_adb import android_device_status as probe

    return probe()
