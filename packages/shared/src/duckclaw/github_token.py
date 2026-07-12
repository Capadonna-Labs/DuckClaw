"""DB-first GitHub token resolution."""

from __future__ import annotations

import os
from typing import Any


def resolve_github_token(
    token_env: str | None = None,
    *,
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
) -> str:
    from duckclaw.integration_secrets import resolve_integration_api_key

    env_name = (token_env or "GITHUB_TOKEN").strip() or "GITHUB_TOKEN"
    resolved = resolve_integration_api_key(
        "github",
        db=db,
        tenant_id=tenant_id,
        actor_email=actor_email,
        token_env=env_name,
    )
    if resolved:
        return resolved
    return (os.environ.get(env_name) or "").strip()


def github_token_configured(
    token_env: str | None = None,
    *,
    db: Any | None = None,
    tenant_id: str = "default",
    actor_email: str = "",
) -> bool:
    return bool(
        resolve_github_token(
            token_env,
            db=db,
            tenant_id=tenant_id,
            actor_email=actor_email,
        )
    )
