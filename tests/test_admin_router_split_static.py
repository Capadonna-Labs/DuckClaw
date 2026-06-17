from __future__ import annotations

from pathlib import Path


def test_admin_auth_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    auth = Path("services/api-gateway/routers/admin_domains/auth.py").read_text(encoding="utf-8")

    assert "from routers.admin_domains.auth import router as auth_router" in admin
    assert "router.include_router(auth_router)" in admin
    assert '@router.post("/auth/login")' not in admin
    assert '@router.get("/auth/me")' not in admin
    assert '@router.post("/auth/logout")' not in admin
    assert "_admin_auth_login_impl" not in admin
    assert "AdminLoginBody" not in admin
    assert 'router = APIRouter(prefix="/auth", tags=["admin-auth"])' in auth
    assert '@router.post("/login")' in auth
    assert '@router.get("/me")' in auth
    assert '@router.post("/logout")' in auth
    assert "async def admin_auth_login_impl" in auth
    assert "class AdminLoginBody" in auth


def test_project_bootstrap_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    bootstrap = Path(
        "services/api-gateway/routers/admin_domains/project_bootstrap_routes.py"
    ).read_text(encoding="utf-8")

    assert "from routers.admin_domains.project_bootstrap_routes import router as project_bootstrap_router" in admin
    assert "router.include_router(project_bootstrap_router)" in admin
    assert '@router.post("/projects"' not in admin
    assert "class ProjectCreateBody" not in admin
    assert "async def create_project" not in admin
    assert 'router = APIRouter(tags=["admin-project-bootstrap"])' in bootstrap
    assert '@router.post("/projects", dependencies=[Depends(require_admin_key)])' in bootstrap
    assert "class ProjectCreateBody" in bootstrap


def test_admin_template_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    templates = Path("services/api-gateway/routers/admin_domains/templates_catalog.py").read_text(encoding="utf-8")

    assert "from routers.admin_domains.templates_catalog import router as templates_catalog_router" in admin
    assert "router.include_router(templates_catalog_router)" in admin
    assert '@router.get("/templates"' not in admin
    assert '@router.post("/templates"' not in admin
    assert '@router.delete("/templates/{worker_id}"' not in admin
    assert 'router = APIRouter(prefix="/templates", tags=["admin-templates"])' in templates
    assert '@router.get("", dependencies=[Depends(require_admin_key)])' in templates
    assert '@router.get("/{worker_id}", dependencies=[Depends(require_admin_key)])' in templates
    assert '@router.put("/{worker_id}/files/{file_path:path}", dependencies=[Depends(require_admin_key)])' in templates
    assert '@router.delete("/{worker_id}", dependencies=[Depends(require_admin_key)])' in templates


def test_admin_duckdb_explorer_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    explorer = Path("services/api-gateway/routers/admin_domains/duckdb_explorer.py").read_text(
        encoding="utf-8"
    )

    assert "from routers.admin_domains.duckdb_explorer import router as duckdb_explorer_router" in admin
    assert "router.include_router(duckdb_explorer_router)" in admin
    assert '@router.get("/duckdb/tables"' not in admin
    assert '@router.post("/duckdb/query"' not in admin
    assert '@router.post("/duckdb/vector-search"' not in admin
    assert 'router = APIRouter(prefix="/duckdb", tags=["admin-duckdb"])' in explorer
    assert '@router.get("/tables", dependencies=[Depends(require_admin_key)])' in explorer
    assert '@router.post("/query", dependencies=[Depends(require_admin_key)])' in explorer
    assert '@router.post("/vector-search", dependencies=[Depends(require_admin_key)])' in explorer


def test_admin_runtime_config_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    runtime_config = Path("services/api-gateway/routers/admin_domains/runtime_config.py").read_text(
        encoding="utf-8"
    )

    assert "from routers.admin_domains.runtime_config import router as runtime_config_router" in admin
    assert "router.include_router(runtime_config_router)" in admin
    assert '@router.get("/runtime/vaults"' not in admin
    assert '@router.get("/runtime/config"' not in admin
    assert '@router.put("/runtime/config"' not in admin
    assert '@router.delete("/runtime/config"' not in admin
    assert 'router = APIRouter(prefix="/runtime", tags=["admin-runtime-config"])' in runtime_config
    assert '@router.get("/vaults", dependencies=[Depends(require_admin_key)])' in runtime_config
    assert '@router.get("/config", dependencies=[Depends(require_admin_key)])' in runtime_config
    assert '@router.put("/config", dependencies=[Depends(require_admin_key)])' in runtime_config
    assert '@router.delete("/config", dependencies=[Depends(require_admin_key)])' in runtime_config


def test_runtime_settings_mutators_use_typed_write_commands() -> None:
    db_first = Path("services/api-gateway/routers/admin_db_first.py").read_text(encoding="utf-8")
    telegram = Path("services/api-gateway/routers/admin_domains/telegram_routes.py").read_text(encoding="utf-8")

    patch_segment = db_first.split('async def patch_runtime_settings(', 1)[1].split(
        '@router.get("/knowledge/sources"',
        1,
    )[0]
    telegram_helper_segment = telegram.split(
        "def upsert_telegram_webhook_routes_runtime_setting(",
        1,
    )[1].split("\n\ndef get_telegram_routes", 1)[0]
    telegram_put_segment = telegram.split("async def put_telegram_routes(", 1)[1]

    assert "open_gateway_db(read_only=False)" not in patch_segment
    assert "upsert_runtime_setting(" not in patch_segment
    assert "enqueue_typed_command" in patch_segment
    assert "UpsertRuntimeSettingCommand" in patch_segment
    assert '"task_id"' in patch_segment

    assert "open_gateway_db(read_only=False)" not in telegram_helper_segment
    assert "upsert_runtime_setting(" not in telegram_helper_segment
    assert "enqueue_typed_command" in telegram_helper_segment
    assert "UpsertRuntimeSettingCommand" in telegram_helper_segment
    assert '"task_id"' in telegram_put_segment


def test_runtime_config_routes_do_not_enqueue_raw_sql() -> None:
    runtime_config = Path("services/api-gateway/routers/admin_domains/runtime_config.py").read_text(
        encoding="utf-8"
    )

    assert "_enqueue_agent_config_write" not in runtime_config
    assert '"query"' not in runtime_config
    assert "INSERT INTO agent_config" not in runtime_config
    assert "DELETE FROM agent_config" not in runtime_config
    assert "UpsertAgentConfigEntriesCommand" in runtime_config
    assert "DeleteAgentConfigEntriesCommand" in runtime_config


def test_admin_access_management_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    access_management = Path("services/api-gateway/routers/admin_domains/access_management.py").read_text(
        encoding="utf-8"
    )

    assert "from routers.admin_domains.access_management import router as access_management_router" in admin
    assert "router.include_router(access_management_router)" in admin
    assert '@router.get("/access/overview"' not in admin
    assert '@router.get("/access/shared-grants"' not in admin
    assert '@router.post("/access/shared-grants"' not in admin
    assert '@router.delete("/access/shared-grants"' not in admin
    assert '@router.get("/console-users"' not in admin
    assert '@router.post("/console-users"' not in admin
    assert '@router.patch("/console-users"' not in admin
    assert '@router.delete("/console-users"' not in admin
    assert '@router.get("/telegram/whitelist"' not in admin
    assert '@router.post("/telegram/whitelist"' not in admin
    assert '@router.delete("/telegram/whitelist"' not in admin
    assert 'router = APIRouter(tags=["admin-access-management"])' in access_management
    assert '@router.get("/access/overview", dependencies=[Depends(require_admin_key)])' in access_management
    assert '@router.get("/access/shared-grants", dependencies=[Depends(require_admin_key)])' in access_management
    assert '@router.post("/access/shared-grants", dependencies=[Depends(require_admin_key)])' in access_management
    assert '@router.delete("/access/shared-grants", dependencies=[Depends(require_admin_key)])' in access_management
    assert '@router.get("/console-users", dependencies=[Depends(require_admin_key)])' in access_management
    assert '@router.post("/console-users", dependencies=[Depends(require_admin_key)])' in access_management
    assert '@router.patch("/console-users", dependencies=[Depends(require_admin_key)])' in access_management
    assert '@router.delete("/console-users", dependencies=[Depends(require_admin_key)])' in access_management
    assert '@router.get("/telegram/whitelist", dependencies=[Depends(require_admin_key)])' in access_management
    assert '@router.post("/telegram/whitelist", dependencies=[Depends(require_admin_key)])' in access_management
    assert '@router.delete("/telegram/whitelist", dependencies=[Depends(require_admin_key)])' in access_management


def test_admin_sandbox_session_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    sandbox_sessions = Path(
        "services/api-gateway/routers/admin_domains/sandbox_sessions.py"
    ).read_text(encoding="utf-8")

    assert "from routers.admin_domains.sandbox_sessions import router as sandbox_sessions_router" in admin
    assert "router.include_router(sandbox_sessions_router)" in admin
    assert "class NovncPrepareBody" not in admin
    assert "class SandboxNetworkBody" not in admin
    assert "def _worker_has_browser_sandbox" not in admin
    assert "def _sandbox_chat_policy_payload" not in admin
    assert '@router.get("/sandbox/chat-policy"' not in admin
    assert '@router.post("/sandbox/network"' not in admin
    assert '@router.get("/sandbox/status"' not in admin
    assert '@router.get("/sandbox/sessions"' not in admin
    assert '@router.post("/sandbox/novnc/prepare"' not in admin
    assert 'router = APIRouter(prefix="/sandbox", tags=["admin-sandbox-sessions"])' in sandbox_sessions
    assert '@router.get("/chat-policy", dependencies=[Depends(require_admin_key)])' in sandbox_sessions
    assert '@router.post("/network", dependencies=[Depends(require_admin_key)])' in sandbox_sessions
    assert '@router.get("/status", dependencies=[Depends(require_admin_key)])' in sandbox_sessions
    assert '@router.get("/sessions", dependencies=[Depends(require_admin_key)])' in sandbox_sessions
    assert '@router.post("/novnc/prepare", dependencies=[Depends(require_admin_key)])' in sandbox_sessions


def test_admin_playground_chat_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    playground_chat = Path(
        "services/api-gateway/routers/admin_domains/playground_chat.py"
    ).read_text(encoding="utf-8")
    playground_pkg = Path("services/api-gateway/routers/admin_domains/playground")
    playground_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(playground_pkg.glob("*.py"))
        if path.name != "__init__.py"
    )

    assert "from routers.admin_domains.playground_chat import router as playground_chat_router" in admin
    assert "router.include_router(playground_chat_router)" in admin
    assert "class PlaygroundChatBody" not in admin
    assert "class PlaygroundVoiceBody" not in admin
    assert "class AdminConversationCreateBody" not in admin
    assert "def _playground_worker_allowed_in_team" not in admin
    assert '@router.get("/playground/config"' not in admin
    assert '@router.put("/playground/vault"' not in admin
    assert '@router.put("/playground/worker"' not in admin
    assert '@router.put("/playground/model"' not in admin
    assert '@router.post("/playground/chat"' not in admin
    assert '@router.post("/playground/voice"' not in admin
    assert '@router.post("/playground/chat/cancel"' not in admin
    assert '@router.get("/chats/history"' not in admin
    assert '@router.get("/conversations"' not in admin
    assert '@router.post("/conversations"' not in admin
    assert '@router.get("/conversations/{session_id}"' not in admin
    assert '@router.patch("/conversations/{session_id}"' not in admin
    assert '@router.delete("/conversations/{session_id}"' not in admin
    assert '@router.post("/conversations/reindex"' not in admin
    assert '@router.get("/playground/config"' not in playground_chat
    assert '@router.post("/playground/chat"' not in playground_chat
    assert 'router = APIRouter(tags=["admin-playground-chat"])' in playground_sources
    assert '@router.get("/playground/config", dependencies=[Depends(require_admin_key)])' in playground_sources
    assert '@router.put("/playground/vault", dependencies=[Depends(require_admin_key)])' in playground_sources
    assert '@router.put("/playground/worker", dependencies=[Depends(require_admin_key)])' in playground_sources
    assert '@router.put("/playground/model", dependencies=[Depends(require_admin_key)])' in playground_sources
    assert '@router.post("/playground/chat", dependencies=[Depends(require_admin_key)])' in playground_sources
    assert '@router.post("/playground/voice", dependencies=[Depends(require_admin_key)])' in playground_sources
    assert '@router.post("/playground/chat/cancel", dependencies=[Depends(require_admin_key)])' in playground_sources
    assert '@router.get("/chats/history", dependencies=[Depends(require_admin_key)])' in playground_sources
    assert '@router.get("/conversations", dependencies=[Depends(require_admin_key)])' in playground_sources
    assert '@router.post("/conversations", dependencies=[Depends(require_admin_key)])' in playground_sources
    assert '@router.get("/conversations/{session_id}", dependencies=[Depends(require_admin_key)])' in playground_sources
    assert '@router.patch("/conversations/{session_id}", dependencies=[Depends(require_admin_key)])' in playground_sources
    assert '@router.delete("/conversations/{session_id}", dependencies=[Depends(require_admin_key)])' in playground_sources
    assert '@router.post("/conversations/reindex", dependencies=[Depends(require_admin_key)])' in playground_sources


def test_playground_model_settings_use_runtime_setting_commands_only() -> None:
    config_routes = Path(
        "services/api-gateway/routers/admin_domains/playground/config_routes.py"
    ).read_text(encoding="utf-8")
    segment = config_routes.split("async def playground_set_model(", 1)[1]

    assert "open_gateway_db(read_only=False)" not in segment
    assert "DuckClaw(gw, read_only=False" not in segment
    assert "DuckClaw(vault_path, read_only=False" not in segment
    assert "execute_model(" not in segment
    assert "UpsertRuntimeSettingCommand" in segment
    assert "RUNTIME_SESSION_DOMAIN" in segment
    assert "runtime_session_actor" in segment
    assert "enqueue_typed_command" in segment
    assert "task_id" in segment


def test_admin_visual_assets_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    visual_assets = Path(
        "services/api-gateway/routers/admin_domains/visual_assets.py"
    ).read_text(encoding="utf-8")

    assert "from routers.admin_domains.visual_assets import router as visual_assets_router" in admin
    assert "router.include_router(visual_assets_router)" in admin
    assert "class ComfyuiGenerateBody" not in admin
    assert "def _list_comfyui_templates" not in admin
    assert '@router.get("/comfyui/status"' not in admin
    assert '@router.get("/comfyui/templates"' not in admin
    assert '@router.post("/comfyui/generate"' not in admin
    assert 'router = APIRouter(prefix="/comfyui", tags=["admin-visual-assets"])' in visual_assets
    assert '@router.get("/status", dependencies=[Depends(require_admin_key)])' in visual_assets
    assert '@router.get("/templates", dependencies=[Depends(require_admin_key)])' in visual_assets
    assert '@router.post("/generate", dependencies=[Depends(require_admin_key)])' in visual_assets


def test_admin_kanban_runtime_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    kanban_runtime = Path(
        "services/api-gateway/routers/admin_domains/kanban_runtime.py"
    ).read_text(encoding="utf-8")

    assert "from routers.admin_domains.kanban_runtime import router as kanban_runtime_router" in admin
    assert "router.include_router(kanban_runtime_router)" in admin
    assert "def _kanban_status_from_audit" not in admin
    assert "def _resolve_kanban_worker_ids" not in admin
    assert "def _kanban_audit_states_by_worker" not in admin
    assert "def _kanban_latest_tasks_by_worker" not in admin
    assert "def _kanban_instance_key" not in admin
    assert '@router.get("/kanban/worker-states"' not in admin
    assert '@router.get("/kanban/swarm-slots"' not in admin
    assert 'router = APIRouter(prefix="/kanban", tags=["admin-kanban-runtime"])' in kanban_runtime
    assert '@router.get("/worker-states", dependencies=[Depends(require_admin_key)])' in kanban_runtime
    assert '@router.get("/swarm-slots", dependencies=[Depends(require_admin_key)])' in kanban_runtime


def test_admin_kanban_card_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    db_first = Path("services/api-gateway/routers/admin_db_first.py").read_text(encoding="utf-8")
    kanban = Path("services/api-gateway/routers/admin_domains/kanban.py").read_text(
        encoding="utf-8"
    )

    assert "from routers.admin_domains.kanban import router as kanban_router" in admin
    assert "router.include_router(kanban_router)" in admin
    assert "class KanbanCreateBody" not in db_first
    assert "class KanbanUpdateBody" not in db_first
    assert "def _kanban_db_status" not in db_first
    assert "def _kanban_tags" not in db_first
    assert "def _kanban_card_from_row" not in db_first
    assert "def _kanban_existing_card" not in db_first
    assert "def _enqueue_kanban_command" not in db_first
    assert '@router.get("/kanban"' not in db_first
    assert '@router.post("/kanban"' not in db_first
    assert '@router.patch("/kanban"' not in db_first
    assert '@router.delete("/kanban"' not in db_first
    assert 'router = APIRouter(prefix="/kanban", tags=["admin-kanban"])' in kanban
    assert '@router.get("", dependencies=[Depends(require_admin_key)])' in kanban
    assert '@router.post("", dependencies=[Depends(require_admin_key)])' in kanban
    assert '@router.patch("", dependencies=[Depends(require_admin_key)])' in kanban
    assert '@router.delete("", dependencies=[Depends(require_admin_key)])' in kanban


def test_admin_kanban_card_router_does_not_write_profiles_directly() -> None:
    kanban = Path("services/api-gateway/routers/admin_domains/kanban.py").read_text(
        encoding="utf-8"
    )

    assert "open_gateway_db(read_only=False)" not in kanban
    assert kanban.count("open_gateway_db(read_only=True)") == 4


def test_admin_prompt_policy_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    db_first = Path("services/api-gateway/routers/admin_db_first.py").read_text(encoding="utf-8")
    prompt_policies = Path(
        "services/api-gateway/routers/admin_domains/prompt_policies.py"
    ).read_text(encoding="utf-8")

    assert "from routers.admin_domains.prompt_policies import router as prompt_policies_router" in admin
    assert "router.include_router(prompt_policies_router)" in admin
    assert "class PromptPolicyUpsertBody" not in db_first
    assert "def _normalize_prompt_policy_type" not in db_first
    assert "def _normalize_prompt_policy_status" not in db_first
    assert "def _prompt_policy_id" not in db_first
    assert "def _prompt_policy_row" not in db_first
    assert "def _prompt_policy_requirement_row" not in db_first
    assert "def _enqueue_prompt_policy_command" not in db_first
    assert '@router.get("/prompt-policies"' not in db_first
    assert '@router.get("/prompt-policies/health"' not in db_first
    assert '@router.put("/prompt-policies"' not in db_first
    assert '@router.delete("/prompt-policies/{policy_type}/{policy_name}"' not in db_first
    assert 'router = APIRouter(prefix="/prompt-policies", tags=["admin-prompt-policies"])' in prompt_policies
    assert '@router.get("", dependencies=[Depends(require_admin_key)])' in prompt_policies
    assert '@router.get("/health", dependencies=[Depends(require_admin_key)])' in prompt_policies
    assert '@router.put("", dependencies=[Depends(require_admin_key)])' in prompt_policies
    assert '@router.delete("/{policy_type}/{policy_name}", dependencies=[Depends(require_admin_key)])' in prompt_policies


def test_admin_template_context_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    db_first = Path("services/api-gateway/routers/admin_db_first.py").read_text(encoding="utf-8")
    template_contexts = Path(
        "services/api-gateway/routers/admin_domains/template_contexts.py"
    ).read_text(encoding="utf-8")

    assert "from routers.admin_domains.template_contexts import router as template_contexts_router" in admin
    assert "router.include_router(template_contexts_router)" in admin
    assert "class TemplateImportBody" not in db_first
    assert "class TemplateContextBody" not in db_first
    assert "class ContextReorderBody" not in db_first
    assert '@router.post("/templates/import"' not in db_first
    assert '@router.post("/templates/{worker_id}/contexts"' not in db_first
    assert '@router.patch("/templates/{worker_id}/contexts/reorder"' not in db_first
    assert '@router.delete("/templates/{worker_id}/contexts/{context_id}"' not in db_first
    assert 'router = APIRouter(tags=["admin-template-contexts"])' in template_contexts
    assert '@router.post("/templates/import", dependencies=[Depends(require_admin_key)])' in template_contexts
    assert '@router.post("/templates/{worker_id}/contexts", dependencies=[Depends(require_admin_key)])' in template_contexts
    assert '@router.patch("/templates/{worker_id}/contexts/reorder", dependencies=[Depends(require_admin_key)])' in template_contexts
    assert '@router.delete("/templates/{worker_id}/contexts/{context_id}", dependencies=[Depends(require_admin_key)])' in template_contexts
    assert "open_gateway_db(read_only=False)" not in template_contexts
    assert "task_id" in template_contexts


def test_admin_workspace_project_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    db_first = Path("services/api-gateway/routers/admin_db_first.py").read_text(encoding="utf-8")
    workspace_projects = Path(
        "services/api-gateway/routers/admin_domains/workspace_projects.py"
    ).read_text(encoding="utf-8")

    assert "from routers.admin_domains.workspace_projects import router as workspace_projects_router" in admin
    assert "router.include_router(workspace_projects_router)" in admin
    assert "class WorkspaceProjectBody" not in db_first
    assert "class ProjectAgentBody" not in db_first
    assert '@router.get("/workspace/projects"' not in db_first
    assert '@router.post("/workspace/projects"' not in db_first
    assert '@router.get("/workspace/projects/{project_id}"' not in db_first
    assert '@router.delete("/workspace/projects/{project_id}"' not in db_first
    assert '@router.post("/workspace/projects/{project_id}/deactivate"' not in db_first
    assert '@router.post("/workspace/projects/{project_id}/reactivate"' not in db_first
    assert '@router.get("/workspace/projects/{project_id}/agents"' not in db_first
    assert '@router.post("/workspace/projects/{project_id}/agents"' not in db_first
    assert '@router.delete("/workspace/projects/{project_id}/agents/{worker_id}"' not in db_first
    assert 'router = APIRouter(tags=["admin-workspace-projects"])' in workspace_projects
    assert '@router.get("/workspace/projects", dependencies=[Depends(require_admin_key)])' in workspace_projects
    assert '@router.post("/workspace/projects", dependencies=[Depends(require_admin_key)])' in workspace_projects
    assert '@router.get("/workspace/projects/{project_id}", dependencies=[Depends(require_admin_key)])' in workspace_projects
    assert '@router.delete("/workspace/projects/{project_id}", dependencies=[Depends(require_admin_key)])' in workspace_projects
    assert (
        '@router.post("/workspace/projects/{project_id}/deactivate", dependencies=[Depends(require_admin_key)])'
        in workspace_projects
    )
    assert (
        '@router.post("/workspace/projects/{project_id}/reactivate", dependencies=[Depends(require_admin_key)])'
        in workspace_projects
    )
    assert (
        '@router.get("/workspace/projects/{project_id}/agents", dependencies=[Depends(require_admin_key)])'
        in workspace_projects
    )
    assert (
        '@router.post("/workspace/projects/{project_id}/agents", dependencies=[Depends(require_admin_key)])'
        in workspace_projects
    )
    assert (
        '@router.delete("/workspace/projects/{project_id}/agents/{worker_id}", dependencies=[Depends(require_admin_key)])'
        in workspace_projects
    )


def test_workspace_project_router_uses_typed_commands_only() -> None:
    workspace_projects = Path(
        "services/api-gateway/routers/admin_domains/workspace_projects.py"
    ).read_text(encoding="utf-8")

    assert "open_gateway_db(read_only=False)" not in workspace_projects
    assert "BEGIN TRANSACTION" not in workspace_projects
    assert "enqueue_typed_command" in workspace_projects
    assert "CreateProjectCommand" in workspace_projects
    assert "SetProjectStatusCommand" in workspace_projects
    assert "DeleteProjectCommand" in workspace_projects
    assert "AssignAgentToProjectCommand" in workspace_projects
    assert "DetachAgentFromProjectCommand" in workspace_projects
    assert "task_id" in workspace_projects


def test_managed_workspace_draft_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    db_first = Path("services/api-gateway/routers/admin_db_first.py").read_text(encoding="utf-8")
    managed_draft = Path(
        "services/api-gateway/routers/admin_domains/workspace_managed_draft.py"
    ).read_text(encoding="utf-8")

    assert "from routers.admin_domains.workspace_managed_draft import router as workspace_managed_draft_router" in admin
    assert "router.include_router(workspace_managed_draft_router)" in admin
    assert "class WorkspaceManagedDraftBody" not in db_first
    assert "class WorkspaceManagedDraftConfirmBody" not in db_first
    assert "def _workspace_managed_draft_policy" not in db_first
    assert "def _workspace_managed_fallback_draft" not in db_first
    assert "def _workspace_managed_model_draft_or_fallback" not in db_first
    assert "def _workspace_managed_skill_suggestions" not in db_first
    assert '@router.post("/workspace/orchestrator/draft"' not in db_first
    assert '@router.post("/workspace/orchestrator/confirm"' not in db_first
    assert 'router = APIRouter(tags=["admin-workspace-managed-draft"])' in managed_draft
    assert '@router.post("/workspace/orchestrator/draft", dependencies=[Depends(require_admin_key)])' in managed_draft
    assert '@router.post("/workspace/orchestrator/confirm", dependencies=[Depends(require_admin_key)])' in managed_draft
    assert "WorkspaceManagedDraft" in managed_draft


def test_managed_workspace_draft_router_uses_typed_commands_only() -> None:
    managed_draft = Path(
        "services/api-gateway/routers/admin_domains/workspace_managed_draft.py"
    ).read_text(encoding="utf-8")

    assert "open_gateway_db(read_only=False)" not in managed_draft
    assert "BEGIN TRANSACTION" not in managed_draft
    assert "enqueue_typed_command" in managed_draft
    assert "ConfirmWorkspaceManagedDraftCommand" in managed_draft
    assert "task_id" in managed_draft


def test_admin_user_agent_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    db_first = Path("services/api-gateway/routers/admin_db_first.py").read_text(encoding="utf-8")
    user_agents_path = Path("services/api-gateway/routers/admin_domains/user_agents.py")

    assert user_agents_path.exists()
    user_agents = user_agents_path.read_text(encoding="utf-8")
    assert "from routers.admin_domains.user_agents import router as user_agents_router" in admin
    assert "router.include_router(user_agents_router)" in admin
    assert "class UserAgentCreateBody" not in db_first
    assert "create_user_agent" not in db_first
    assert '@router.post("/user-agents"' not in db_first
    assert 'router = APIRouter(tags=["admin-user-agents"])' in user_agents
    assert '@router.post("/user-agents", dependencies=[Depends(require_admin_key)])' in user_agents


def test_admin_user_agent_router_uses_typed_commands_only() -> None:
    user_agents_path = Path("services/api-gateway/routers/admin_domains/user_agents.py")

    assert user_agents_path.exists()
    user_agents = user_agents_path.read_text(encoding="utf-8")

    assert "open_gateway_db(read_only=False)" not in user_agents
    assert "BEGIN TRANSACTION" not in user_agents
    assert "enqueue_typed_command" in user_agents
    assert "UpsertUserAgentCommand" in user_agents
    assert "task_id" in user_agents


def test_catalog_skill_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    catalog_skills_path = Path("services/api-gateway/routers/admin_domains/catalog_skills.py")

    assert catalog_skills_path.exists()
    catalog_skills = catalog_skills_path.read_text(encoding="utf-8")
    assert "from routers.admin_domains.catalog_skills import router as catalog_skills_router" in admin
    assert "router.include_router(catalog_skills_router)" in admin
    assert "class CatalogSkillCreateBody" not in admin
    assert "create_catalog_skill" not in admin
    assert '@router.get("/catalog/skills"' not in admin
    assert '@router.post("/catalog/skills"' not in admin
    assert 'router = APIRouter(prefix="/catalog", tags=["admin-catalog-skills"])' in catalog_skills
    assert '@router.get("/skills", dependencies=[Depends(require_admin_key)])' in catalog_skills
    assert '@router.post("/skills", dependencies=[Depends(require_admin_key)])' in catalog_skills
    assert '@router.delete("/skills/{name}", dependencies=[Depends(require_admin_key)])' in catalog_skills


def test_catalog_skill_router_uses_typed_commands_only() -> None:
    catalog_skills_path = Path("services/api-gateway/routers/admin_domains/catalog_skills.py")

    assert catalog_skills_path.exists()
    catalog_skills = catalog_skills_path.read_text(encoding="utf-8")

    assert "open_gateway_db(read_only=False)" not in catalog_skills
    assert "BEGIN TRANSACTION" not in catalog_skills
    assert "enqueue_typed_command" in catalog_skills
    assert "UpsertCatalogSkillCommand" in catalog_skills
    assert "DeactivateCatalogSkillCommand" in catalog_skills
    assert "task_id" in catalog_skills


def test_template_catalog_router_uses_typed_commands_for_mutators() -> None:
    templates = Path("services/api-gateway/routers/admin_domains/templates_catalog.py").read_text(
        encoding="utf-8"
    )

    for handler_name in (
        "put_template_file",
        "delete_template",
        "reactivate_template",
        "hard_delete_template",
    ):
        segment = templates.split(f"async def {handler_name}(", 1)[1].split("\n\n@", 1)[0]
        assert "admin_router._" not in segment
        assert "open_gateway_db(read_only=False)" not in segment
        assert "BEGIN TRANSACTION" not in segment
        assert "_enqueue_template_catalog_command" in segment
        assert "task_id" in segment

    assert "enqueue_typed_command" in templates
    assert "UpdateCatalogWorkerFileCommand" in templates
    assert "DeactivateCatalogWorkerCommand" in templates
    assert "ReactivateCatalogWorkerCommand" in templates
    assert "HardDeleteCatalogWorkerCommand" in templates


def test_admin_template_helpers_no_longer_own_structured_writes() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    lifecycle = Path("services/api-gateway/routers/admin_domains/template_lifecycle.py").read_text(
        encoding="utf-8"
    )
    helper_block = lifecycle.split("async def put_template_file_impl(", 1)[1].split(
        "\n\nasync def validate_template_impl",
        1,
    )[0]

    assert "async def _put_template_file_impl(" not in admin
    assert "async def put_template_file_impl(" not in admin
    assert "open_gateway_db(read_only=False)" not in helper_block
    assert "BEGIN TRANSACTION" not in helper_block
    assert "update_catalog_worker_file(" not in helper_block
    assert "deactivate_visible_worker_for_actor(" not in helper_block
    assert "reactivate_visible_worker_for_actor(" not in helper_block
    assert "hard_delete_visible_worker_for_actor(" not in helper_block


def test_admin_audit_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    audit = Path("services/api-gateway/routers/admin_domains/audit.py").read_text(encoding="utf-8")
    common = Path("services/api-gateway/routers/admin_domains/admin_common.py").read_text(encoding="utf-8")

    assert "from routers.admin_domains.audit import router as audit_router" in admin
    assert "router.include_router(audit_router)" in admin
    assert '@router.get("/audit"' not in admin
    assert "async def get_admin_audit" not in admin
    assert "def admin_audit(" in common
    assert "def audit_log_path(" in common
    assert 'router = APIRouter(prefix="/audit", tags=["admin-audit"])' in audit
    assert '@router.get("", dependencies=[Depends(require_admin_key)])' in audit
    assert "async def get_admin_audit" in audit
    assert "def _load_audit_entries" in audit


def test_admin_ops_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    ops = Path("services/api-gateway/routers/admin_domains/ops.py").read_text(encoding="utf-8")

    assert "from routers.admin_domains.ops import router as ops_router" in admin
    assert "router.include_router(ops_router)" in admin
    assert "class OpsRunBody" not in admin
    assert "_OPS_ALLOWLIST" not in admin
    assert "def _pm2_restart_interrupted" not in admin
    assert "def _normalize_ops_result" not in admin
    assert '@router.get("/ops/commands"' not in admin
    assert '@router.post("/ops/run"' not in admin
    assert 'router = APIRouter(prefix="/ops", tags=["admin-ops"])' in ops
    assert '@router.get("/commands", dependencies=[Depends(require_admin_key)])' in ops
    assert '@router.post("/run", dependencies=[Depends(require_admin_key)])' in ops


def test_admin_overview_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    overview = Path("services/api-gateway/routers/admin_domains/overview.py").read_text(encoding="utf-8")

    assert "from routers.admin_domains.overview import router as overview_router" in admin
    assert "router.include_router(overview_router)" in admin
    assert "from routers.admin_domains.overview import overview_usage_metrics as _overview_usage_metrics" in admin
    assert '@router.get("/health"' not in admin
    assert '@router.get("/overview/metrics"' not in admin
    assert "def _gateway_db_query_rows" not in admin
    assert "def _overview_usage_metrics" not in admin
    assert 'router = APIRouter(tags=["admin-overview"])' in overview
    assert '@router.get("/health", dependencies=[Depends(require_admin_key)])' in overview
    assert '@router.get("/overview/metrics", dependencies=[Depends(require_admin_key)])' in overview
    assert "def overview_usage_metrics(" in overview
    assert "def gateway_db_query_rows(" in overview


def test_duckdb_legacy_cleanup_router_uses_typed_command() -> None:
    explorer = Path("services/api-gateway/routers/admin_domains/duckdb_explorer.py").read_text(
        encoding="utf-8"
    )
    segment = explorer.split("async def duckdb_drop_legacy_schemas(", 1)[1].split(
        "\n\n@router.get(\"/pgq-graph\"",
        1,
    )[0]

    assert "_duckdb_writable_session" not in segment
    assert "duckdb.connect" not in segment
    assert "BEGIN TRANSACTION" not in segment
    assert "DropLegacyDuckDbObjectsCommand" in segment
    assert "enqueue_typed_command" in segment
    assert "task_id" in segment


def test_admin_common_hosts_shared_helpers() -> None:
    common = Path("services/api-gateway/routers/admin_domains/admin_common.py").read_text(encoding="utf-8")
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")

    assert "def admin_audit(" in common
    assert "def audit_log_path(" in common
    assert "def require_admin_key(" in common
    assert "def problem(" in common
    assert "def actor_from_header(" in common
    assert "from routers.admin_domains.admin_common import" in admin
    assert "def _admin_audit(" not in admin
    assert "def _audit_log_path(" not in admin


def test_admin_env_config_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    env_config = Path("services/api-gateway/routers/admin_domains/env_config.py").read_text(encoding="utf-8")

    assert "from routers.admin_domains.env_config import router as env_config_router" in admin
    assert "router.include_router(env_config_router)" in admin
    assert '@router.get("/env"' not in admin
    assert '@router.patch("/env"' not in admin
    assert '@router.get("/env", dependencies=[Depends(require_admin_key)])' in env_config
    assert '@router.patch("/env", dependencies=[Depends(require_admin_key)])' in env_config
    assert "def merge_env_lines(" in env_config


def test_admin_telegram_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    telegram = Path("services/api-gateway/routers/admin_domains/telegram_routes.py").read_text(encoding="utf-8")

    assert "from routers.admin_domains.telegram_routes import router as telegram_routes_router" in admin
    assert "router.include_router(telegram_routes_router)" in admin
    assert '@router.get("/telegram/routes"' not in admin
    assert '@router.put("/telegram/routes"' not in admin
    assert 'router = APIRouter(prefix="/telegram", tags=["admin-telegram-routes"])' in telegram
    assert '@router.get("/routes", dependencies=[Depends(require_admin_key)])' in telegram
    assert '@router.put("/routes", dependencies=[Depends(require_admin_key)])' in telegram


def test_admin_catalog_meta_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    catalog_meta = Path("services/api-gateway/routers/admin_domains/catalog_meta.py").read_text(encoding="utf-8")

    assert "from routers.admin_domains.catalog_meta import router as catalog_meta_router" in admin
    assert "router.include_router(catalog_meta_router)" in admin
    assert '@router.get("/catalog/mcp"' not in admin
    assert '@router.get("/catalog/industries"' not in admin
    assert '@router.get("/catalog/topologies"' not in admin
    assert '@router.get("/catalog/source-preview"' not in admin
    assert 'router = APIRouter(prefix="/catalog", tags=["admin-catalog-meta"])' in catalog_meta
    assert '@router.get("/mcp", dependencies=[Depends(require_admin_key)])' in catalog_meta
    assert '@router.get("/industries", dependencies=[Depends(require_admin_key)])' in catalog_meta
    assert '@router.get("/topologies", dependencies=[Depends(require_admin_key)])' in catalog_meta
    assert '@router.get("/source-preview", dependencies=[Depends(require_admin_key)])' in catalog_meta


def test_admin_forge_projects_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    forge_projects = Path("services/api-gateway/routers/admin_domains/forge_projects.py").read_text(encoding="utf-8")

    assert "from routers.admin_domains.forge_projects import router as forge_projects_router" in admin
    assert "router.include_router(forge_projects_router)" in admin
    assert '@router.get("/forge-projects"' not in admin
    assert '@router.post("/forge-projects"' not in admin
    assert 'router = APIRouter(prefix="/forge-projects", tags=["admin-forge-projects"])' in forge_projects
    assert '@router.get("", dependencies=[Depends(require_admin_key)])' in forge_projects
    assert '@router.post("", dependencies=[Depends(require_admin_key)])' in forge_projects


def test_admin_hitl_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    hitl = Path("services/api-gateway/routers/admin_domains/hitl_admin.py").read_text(encoding="utf-8")

    assert "from routers.admin_domains.hitl_admin import router as hitl_admin_router" in admin
    assert "router.include_router(hitl_admin_router)" in admin
    assert '@router.post("/code/approve"' not in admin
    assert '@router.post("/code/reject"' not in admin
    assert '@router.get("/code/decisions"' not in admin
    assert '@router.get("/uncertainty/events"' not in admin
    assert '@router.post("/uncertainty/resolve"' not in admin
    assert '@router.get("/meditate/status"' not in admin
    assert '@router.post("/meditate/tick"' not in admin
    assert 'router = APIRouter(tags=["admin-hitl"])' in hitl
    assert "duckclaw.hitl.code_decision_service" in hitl
    assert "duckclaw.hitl.uncertainty_service" in hitl
    assert "capadonna" not in hitl


def test_admin_fly_commands_routes_live_in_domain_module() -> None:
    admin = Path("services/api-gateway/routers/admin.py").read_text(encoding="utf-8")
    fly_commands = Path("services/api-gateway/routers/admin_domains/fly_commands_catalog.py").read_text(encoding="utf-8")

    assert "from routers.admin_domains.fly_commands_catalog import router as fly_commands_catalog_router" in admin
    assert "router.include_router(fly_commands_catalog_router)" in admin
    assert '@router.get("/fly-commands"' not in admin
    assert 'router = APIRouter(tags=["admin-fly-commands"])' in fly_commands
    assert '@router.get("/fly-commands", dependencies=[Depends(require_admin_key)])' in fly_commands
