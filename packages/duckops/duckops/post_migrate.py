"""Post-migrate housekeeping for ``duckops up`` (idempotent, no HTTP gateway)."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

PrintFn = Callable[[str], None]


def _resolve_hub_path(repo_root: Path) -> Path | None:
    from duckclaw.gateway_db import get_gateway_db_path

    raw = (get_gateway_db_path() or "").strip()
    if not raw:
        return None
    path = Path(raw)
    if not path.is_absolute():
        path = (repo_root / path).resolve()
    return path if path.is_file() else None


def run_post_migrate_housekeeping(repo_root: Path, print_fn: PrintFn) -> None:
    """
    Materializa policies framework degradadas y sincroniza ``system_prompt`` del catálogo.

    Evita que un dev nuevo tenga que descubrir sync-catalog en admin tras el primer migrate.
    """
    hub = _resolve_hub_path(repo_root)
    if hub is None:
        return

    from duckops.admin_bootstrap import _flat_env
    from duckops.policy_health import check_catalog_worker_system_prompts, check_framework_prompt_policies

    env = _flat_env(repo_root)
    actor = (env.get("DUCKCLAW_ADMIN_EMAIL") or "system@duckclaw.local").strip()

    import duckdb

    con = duckdb.connect(str(hub), read_only=False)
    try:
        framework = check_framework_prompt_policies(con)
        if framework.degraded or not framework.ok:
            from duckclaw.framework_policy_pack import apply_framework_policy_pack

            applied = apply_framework_policy_pack(con)
            if applied:
                print_fn(
                    f"  post-migrate: policies framework → {len(applied)} fila(s) en DuckDB"
                )

        catalog = check_catalog_worker_system_prompts(con)
        if not catalog.ok:
            from duckclaw.catalog_prompt_sync import sync_all_catalog_worker_prompts

            result = sync_all_catalog_worker_prompts(con, actor_email=actor, force=False)
            synced = list(result.get("synced") or [])
            if synced:
                preview = ", ".join(synced[:5])
                suffix = "…" if len(synced) > 5 else ""
                print_fn(f"  post-migrate: system_prompt sync → {preview}{suffix}")
            else:
                print_fn(
                    "  hint: prompts de agentes en uso pendientes — "
                    "crea un agente en Plantillas o importa catálogo"
                )
    finally:
        con.close()
