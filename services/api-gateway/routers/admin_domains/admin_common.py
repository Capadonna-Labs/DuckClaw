"""Helpers compartidos entre routers admin_domains y el agregador admin.py."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Header, HTTPException, status

_REPO_ROOT = Path(__file__).resolve().parents[4]


def repo_root() -> Path:
    raw = (os.environ.get("DUCKCLAW_REPO_ROOT") or "").strip()
    return Path(raw) if raw else _REPO_ROOT


def audit_log_path() -> Path:
    path = repo_root() / ".duckclaw" / "admin-audit.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def admin_audit(
    action: str,
    resource: str,
    detail: str,
    *,
    actor: str = "admin-ui",
    meta: dict[str, Any] | None = None,
) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "actor": (actor or "admin-ui")[:128],
        "action": action[:64],
        "resource": resource[:256],
        "detail": detail[:2000],
        "meta": meta or {},
    }
    try:
        with audit_log_path().open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except Exception:
        pass


def require_admin_key(x_admin_key: str | None = Header(None, alias="X-Admin-Key")) -> None:
    expected = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    if not expected:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="DUCKCLAW_ADMIN_API_KEY no configurada en el gateway",
        )
    if (x_admin_key or "").strip() != expected:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin key inválida")


def problem(status_code: int, title: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"type": "about:blank", "title": title, "status": status_code, "detail": detail},
    )


def actor_from_header(x_actor: str | None = Header(None, alias="X-Duckclaw-Actor")) -> str:
    """Actor email from header, or DUCKCLAW_ADMIN_EMAIL if header is unset."""
    raw = (x_actor or "").strip()[:128]
    if raw and raw != "admin-ui":
        return raw
    admin_email = os.environ.get("DUCKCLAW_ADMIN_EMAIL", "").strip()
    if admin_email and "@" in admin_email:
        return admin_email[:128]
    return raw or "admin-ui"


def mask_secret(value: str) -> str:
    v = (value or "").strip()
    if len(v) <= 4:
        return "****" if v else ""
    return f"{v[:4]}…{'*' * min(12, max(4, len(v) - 4))}"
