from __future__ import annotations

from typing import Any

from fastapi import APIRouter

from routers.admin_domains.access_management import router as access_management_router
from routers.admin_domains.agent_spawn import router as agent_spawn_router
from routers.admin_domains.admin_common import (
    actor_from_header as _actor_from_header,
    admin_audit as _admin_audit,
    audit_log_path as _audit_log_path,
    mask_secret as _mask_secret,
    problem as _problem,
    repo_root as _repo_root,
    require_admin_key as _require_admin_key,
)
from routers.admin_domains.audit import router as audit_router
from routers.admin_domains.auth import router as auth_router
from routers.admin_domains.catalog_meta import router as catalog_meta_router
from routers.admin_domains.catalog_skills import router as catalog_skills_router
from routers.admin_domains.chat_suggestions import router as chat_suggestions_router
from routers.admin_domains.crons import router as crons_router
from routers.admin_domains.devices import router as devices_router
from routers.admin_domains.duckdb_explorer import router as duckdb_explorer_router
from routers.admin_domains.env_config import env_file as _env_file
from routers.admin_domains.env_config import router as env_config_router
from routers.admin_domains.fly_commands_catalog import router as fly_commands_catalog_router
from routers.admin_domains.gateway_resources import router as gateway_resources_router
from routers.admin_domains.hitl_admin import router as hitl_admin_router
from routers.admin_domains.integration_catalog import router as integration_catalog_router
from routers.admin_domains.kanban import router as kanban_router
from routers.admin_domains.knowledge import router as knowledge_router
from routers.admin_domains.mcp_connectors import router as mcp_connectors_router
from routers.admin_domains.kanban_runtime import router as kanban_runtime_router
from routers.admin_domains.ops import router as ops_router
from routers.admin_domains.overview import gateway_db_query_rows as _gateway_db_query_rows
from routers.admin_domains.overview import overview_usage_metrics as _overview_usage_metrics
from routers.admin_domains.overview import router as overview_router
from routers.admin_domains.playground_chat import (
    _open_playground_vault_db,
    _pick_playground_worker,
    _playground_team_context,
    _playground_telegram_user_id,
    _playground_vault_db_path,
)
from routers.admin_domains.playground_chat import router as playground_chat_router
from routers.admin_domains.prompt_policies import router as prompt_policies_router
from routers.admin_domains.report_engine import router as report_engine_router
from routers.admin_domains.productivity import router as productivity_router
from routers.admin_domains.runtime_config import router as runtime_config_router
from routers.admin_domains.sandbox_artifacts import router as sandbox_artifacts_router
from routers.admin_domains.sandbox_sessions import router as sandbox_sessions_router
from routers.admin_domains.telegram_routes import router as telegram_routes_router
from routers.admin_domains.train import router as train_router
from routers.admin_domains.template_contexts import router as template_contexts_router
from routers.admin_domains.templates_catalog import router as templates_catalog_router
from routers.admin_domains.template_lifecycle import (
    FileWriteBody,
    TemplateCreateBody,
    VaultBindingPutBody,
    create_template_impl as _create_template_impl,
    create_worker_from_source as _create_worker_from_source,
    delete_template_impl as _delete_template_impl,
    get_template_impl as _get_template_impl,
    get_template_vault_binding_impl as _get_template_vault_binding_impl,
    hard_delete_template_impl as _hard_delete_template_impl,
    list_template_files as _list_template_files,
    list_templates_impl as _list_templates_impl,
    put_template_file_impl as _put_template_file_impl,
    put_template_vault_binding_impl as _put_template_vault_binding_impl,
    reactivate_template_impl as _reactivate_template_impl,
    safe_worker_path as _safe_worker_path,
    template_card_description as _template_card_description,
    template_vault_options_impl as _template_vault_options_impl,
    templates_dir as _templates_dir,
    validate_template_impl as _validate_template_impl,
)
from routers.admin_domains.user_agents import router as user_agents_router
from routers.admin_domains.user_agent_draft import router as user_agent_draft_router
from routers.admin_domains.visual_assets import router as visual_assets_router
from routers.admin_domains.worker_capabilities import router as worker_capabilities_router
from routers.admin_domains.workspace_managed_draft import router as workspace_managed_draft_router
from routers.admin_domains.workspace_projects import router as workspace_projects_router
from routers.admin_domains.write_tasks import router as write_tasks_router

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])
router.include_router(access_management_router)
router.include_router(agent_spawn_router)
router.include_router(audit_router)
router.include_router(auth_router)
router.include_router(catalog_meta_router)
router.include_router(catalog_skills_router)
router.include_router(chat_suggestions_router)
router.include_router(crons_router)
router.include_router(duckdb_explorer_router)
router.include_router(devices_router)
router.include_router(env_config_router)
router.include_router(fly_commands_catalog_router)
router.include_router(gateway_resources_router)
router.include_router(integration_catalog_router)
router.include_router(hitl_admin_router)
router.include_router(kanban_router)
router.include_router(kanban_runtime_router)
router.include_router(mcp_connectors_router)
router.include_router(knowledge_router)
router.include_router(ops_router)
router.include_router(overview_router)
router.include_router(playground_chat_router)
router.include_router(prompt_policies_router)
router.include_router(report_engine_router)
router.include_router(productivity_router)
router.include_router(runtime_config_router)
router.include_router(sandbox_artifacts_router)
router.include_router(sandbox_sessions_router)
router.include_router(telegram_routes_router)
router.include_router(train_router)
router.include_router(template_contexts_router)
router.include_router(templates_catalog_router)
router.include_router(user_agents_router)
router.include_router(user_agent_draft_router)
router.include_router(visual_assets_router)
router.include_router(worker_capabilities_router)
router.include_router(workspace_managed_draft_router)
router.include_router(workspace_projects_router)
router.include_router(write_tasks_router)


def _gateway_effective_tenant_id(request_tenant: str | None) -> str:
    """Misma resolución que ``main._effective_tenant_id`` (p. ej. default → Marco si está en PM2)."""
    import main as gateway_main

    raw = (request_tenant or "").strip() or "default"
    return gateway_main._effective_tenant_id(raw)


from routers.admin_db_first import router as _admin_db_first_router  # noqa: E402
from routers.reports import router as _admin_reports_router  # noqa: E402

router.include_router(_admin_db_first_router)
router.include_router(_admin_reports_router)
