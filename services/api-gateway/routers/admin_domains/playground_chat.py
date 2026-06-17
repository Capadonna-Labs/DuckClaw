"""
Fachada legacy de admin playground.

El código vive en ``routers.admin_domains.playground.*``; este módulo reexporta
símbolos con prefijo ``_`` para compatibilidad con ``admin.py`` y tests.
"""

from __future__ import annotations

from routers.admin_domains.playground.llm_settings import resolved_llm_for_playground as _resolved_llm_for_playground
from routers.admin_domains.playground.router import router
from routers.admin_domains.playground.team_context import playground_team_context as _playground_team_context
from routers.admin_domains.playground.tenant_resolution import playground_telegram_user_id as _playground_telegram_user_id
from routers.admin_domains.playground.vault_access import open_playground_vault_db as _open_playground_vault_db
from routers.admin_domains.playground.vault_access import playground_vault_db_path as _playground_vault_db_path
from routers.admin_domains.playground.worker_selection import pick_playground_worker as _pick_playground_worker

__all__ = [
    "router",
    "_open_playground_vault_db",
    "_pick_playground_worker",
    "_playground_team_context",
    "_playground_telegram_user_id",
    "_playground_vault_db_path",
    "_resolved_llm_for_playground",
]
