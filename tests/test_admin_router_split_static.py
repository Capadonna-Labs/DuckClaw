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
    assert 'router = APIRouter(prefix="/auth", tags=["admin-auth"])' in auth
    assert '@router.post("/login")' in auth
    assert '@router.get("/me")' in auth
    assert '@router.post("/logout")' in auth


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
    assert 'router = APIRouter(tags=["admin-playground-chat"])' in playground_chat
    assert '@router.get("/playground/config", dependencies=[Depends(require_admin_key)])' in playground_chat
    assert '@router.put("/playground/vault", dependencies=[Depends(require_admin_key)])' in playground_chat
    assert '@router.put("/playground/worker", dependencies=[Depends(require_admin_key)])' in playground_chat
    assert '@router.put("/playground/model", dependencies=[Depends(require_admin_key)])' in playground_chat
    assert '@router.post("/playground/chat", dependencies=[Depends(require_admin_key)])' in playground_chat
    assert '@router.post("/playground/voice", dependencies=[Depends(require_admin_key)])' in playground_chat
    assert '@router.post("/playground/chat/cancel", dependencies=[Depends(require_admin_key)])' in playground_chat
    assert '@router.get("/chats/history", dependencies=[Depends(require_admin_key)])' in playground_chat
    assert '@router.get("/conversations", dependencies=[Depends(require_admin_key)])' in playground_chat
    assert '@router.post("/conversations", dependencies=[Depends(require_admin_key)])' in playground_chat
    assert '@router.get("/conversations/{session_id}", dependencies=[Depends(require_admin_key)])' in playground_chat
    assert '@router.patch("/conversations/{session_id}", dependencies=[Depends(require_admin_key)])' in playground_chat
    assert '@router.delete("/conversations/{session_id}", dependencies=[Depends(require_admin_key)])' in playground_chat
    assert '@router.post("/conversations/reindex", dependencies=[Depends(require_admin_key)])' in playground_chat


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
