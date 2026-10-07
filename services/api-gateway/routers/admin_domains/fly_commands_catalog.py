from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from routers.admin_domains.admin_common import require_admin_key

router = APIRouter(tags=["admin-fly-commands"])


@router.get("/fly-commands", dependencies=[Depends(require_admin_key)])
async def list_fly_commands() -> dict[str, Any]:
    from duckclaw.commands.fly_misc import fly_help_entries
    from duckclaw.guardrails.loader import load_guardrail

    header = load_guardrail("fly_commands", "help_header")
    entries = [{"cmd": cmd, "description": desc} for cmd, desc in fly_help_entries()]
    return {"header": header, "commands": entries}
