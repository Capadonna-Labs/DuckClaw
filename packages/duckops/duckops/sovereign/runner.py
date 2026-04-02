"""Punto de entrada del Sovereign Wizard v2.0."""

from __future__ import annotations

import shutil
from pathlib import Path

from rich.console import Console

from duckops.sovereign.draft import SovereignDraft
from duckops.sovereign.materialize import (
    load_draft_json,
    load_duckdb_vault_hint_from_repo_env,
    load_gateway_tenant_hint_from_repo_env,
    load_last_duckdb_vault_path_from_wizard_config,
    load_last_gateway_pm2_name_from_wizard_config,
    load_last_gateway_port_from_wizard_config,
    load_last_gateway_tenant_id_from_wizard_config,
    load_last_default_worker_id_from_wizard_config,
    load_gateway_port_hint_from_api_gateways_json,
    load_default_worker_id_hint_from_repo_env,
    load_last_wizard_creator_admin_display_name_from_wizard_config,
    load_last_wizard_creator_telegram_user_id_from_wizard_config,
    load_last_wizard_extra_admin_telegram_ids_from_wizard_config,
    load_pm2_gateway_name_hint_from_repo_env,
    load_telegram_creator_hint_from_repo_env,
    materialize,
)
from duckops.sovereign.ui import run_wizard_loop


def _find_repo_root(start: Path | None) -> Path:
    if start is None:
        start = Path.cwd()
    cur = start.resolve()
    for _ in range(8):
        if (cur / "packages" / "duckops").is_dir() and (cur / "pyproject.toml").is_file():
            return cur
        if cur.parent == cur:
            break
        cur = cur.parent
    return start.resolve()


def run_sovereign_wizard(repo_root: Path | None = None) -> int:
    rr = _find_repo_root(repo_root)
    try:
        w = min(120, shutil.get_terminal_size().columns)
    except Exception:
        w = 100
    console = Console(width=w)
    saved = load_draft_json()
    if saved is not None:
        draft = saved
    else:
        draft = SovereignDraft()
        last = load_last_duckdb_vault_path_from_wizard_config()
        if last:
            draft.duckdb_vault_path = last
        else:
            env_hint = load_duckdb_vault_hint_from_repo_env(rr)
            if env_hint:
                draft.duckdb_vault_path = env_hint
        last_creator = load_last_wizard_creator_telegram_user_id_from_wizard_config()
        if last_creator:
            draft.wizard_creator_telegram_user_id = last_creator
        else:
            tg_hint = load_telegram_creator_hint_from_repo_env(rr)
            if tg_hint:
                draft.wizard_creator_telegram_user_id = tg_hint
        last_admin_name = load_last_wizard_creator_admin_display_name_from_wizard_config()
        if last_admin_name:
            draft.wizard_creator_admin_display_name = last_admin_name
        last_extra = load_last_wizard_extra_admin_telegram_ids_from_wizard_config()
        if last_extra:
            draft.wizard_extra_admin_telegram_ids = last_extra
        last_tenant = load_last_gateway_tenant_id_from_wizard_config()
        if last_tenant:
            draft.tenant_id = last_tenant
        else:
            tenant_hint = load_gateway_tenant_hint_from_repo_env(rr)
            if tenant_hint:
                draft.tenant_id = tenant_hint
        last_pm2_name = load_last_gateway_pm2_name_from_wizard_config()
        if last_pm2_name:
            draft.gateway_pm2_name = last_pm2_name
        else:
            pm2_name_hint = load_pm2_gateway_name_hint_from_repo_env(rr)
            if pm2_name_hint:
                draft.gateway_pm2_name = pm2_name_hint
        last_worker = load_last_default_worker_id_from_wizard_config()
        if last_worker:
            draft.default_worker_id = last_worker
        else:
            worker_hint = load_default_worker_id_hint_from_repo_env(rr)
            if worker_hint:
                draft.default_worker_id = worker_hint
        last_port = load_last_gateway_port_from_wizard_config()
        if last_port is not None:
            draft.gateway_port = last_port
        else:
            port_hint = load_gateway_port_hint_from_api_gateways_json(rr, draft.gateway_pm2_name)
            if port_hint is not None:
                draft.gateway_port = port_hint
    code = run_wizard_loop(rr, console, draft)
    if code == 2:

        def _print(msg: str) -> None:
            console.print(msg)

        return materialize(rr, draft, console_print=_print, deploy_pm2=True)
    return code
