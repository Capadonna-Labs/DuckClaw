"""Mercenary vs browser-worker policy for manager plans."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def _strip_mercenary_spec_for_browser_worker(
    out: dict[str, Any], templates_root: Path | None = None, db: Any = None
) -> bool:
    """
    Workers con ``browser_sandbox`` en manifest usan ``run_browser_sandbox`` (Playwright), no mercenario stub.
    Devuelve True si se eliminó ``mercenary_spec`` del estado del plan.
    """
    wid = (out.get("assigned_worker_id") or "").strip()
    if not out.get("mercenary_spec") or not wid:
        return False
    try:
        from duckclaw.workers.manifest import load_manifest

        spec = load_manifest(wid, templates_root, db=db, tenant_id="default")
        if not getattr(spec, "browser_sandbox", False):
            return False
    except Exception:
        return False
    out.pop("mercenary_spec", None)
    return True


def _should_disable_mercenary_for_admin_ui(chat_id: str | None) -> bool:
    """Consola admin / playground: nunca mercenario stub; delegar al worker con Strix browser."""
    try:
        from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

        return bool(is_admin_ui_chat_session(chat_id))
    except Exception:
        cid = (chat_id or "").strip()
        return cid.startswith(("admin-conv-", "admin-section-", "admin-ui")) or cid == "admin-playground"


_BROWSER_MERCENARY_INTENT_MARKERS = (
    "run_browser_sandbox",
    "playwright",
    "novnc",
    "no vnc",
    "browser sandbox",
    "computer use",
    "abrir ",
    "abre ",
    "navega",
    "navegar",
    "página web",
    "pagina web",
    "sitio web",
    "http://",
    "https://",
    "sandbox para",
    "usa sandbox",
    "usar sandbox",
    "el colombiano",
    "elcolombiano",
)


def _should_disable_mercenary_for_browser_intent(
    incoming: str,
    tasks: list[str] | None,
    plan_title: str | None,
    *,
    chat_id: str | None = None,
) -> bool:
    """
    Planes de navegación / computer use deben ir al worker (run_browser_sandbox), no al stub mercenario.
    """
    if _should_disable_mercenary_for_admin_ui(chat_id):
        return True
    blob = " ".join(
        [
            incoming or "",
            plan_title or "",
            " ".join(str(t) for t in (tasks or []) if t),
        ]
    )
    if not blob.strip():
        return False
    low = blob.lower()
    return any(m in low for m in _BROWSER_MERCENARY_INTENT_MARKERS)


__all__ = [
    "_should_disable_mercenary_for_admin_ui",
    "_should_disable_mercenary_for_browser_intent",
    "_strip_mercenary_spec_for_browser_worker",
]
