from __future__ import annotations

import re
from pathlib import Path


GATEWAY_ROOT = Path("services/api-gateway")


def _py_files() -> list[Path]:
    return sorted(GATEWAY_ROOT.rglob("*.py"))


def _function_name_before(source: str, offset: int) -> str:
    prefix = source[:offset]
    matches = list(re.finditer(r"^def\s+([a-zA-Z0-9_]+)|^async def\s+([a-zA-Z0-9_]+)", prefix, re.MULTILINE))
    if not matches:
        return "<module>"
    match = matches[-1]
    return str(match.group(1) or match.group(2))


def _fly_command_set(source: str, name: str) -> set[str]:
    match = re.search(rf"^{name}\s*=\s*frozenset\(\s*\((.*?)\)\s*\)", source, re.MULTILINE | re.DOTALL)
    assert match is not None
    return set(re.findall(r'"([^"]+)"', match.group(1)))


def test_gateway_structured_writes_have_explicit_read_write_allowlist() -> None:
    allowed: set[tuple[str, str]] = set()
    found: set[tuple[str, str]] = set()
    for path in _py_files():
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r"open_gateway_db\(read_only=False\)", source):
            found.add((path.as_posix(), _function_name_before(source, match.start())))

    assert found == allowed


def test_gateway_manual_transactions_have_explicit_allowlist() -> None:
    allowed: set[tuple[str, str]] = set()
    found: set[tuple[str, str]] = set()
    for path in _py_files():
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r"BEGIN TRANSACTION", source):
            found.add((path.as_posix(), _function_name_before(source, match.start())))

    assert found == allowed


def test_gateway_duckclaw_read_write_is_limited_to_explicit_runtime_compat() -> None:
    allowed: set[tuple[str, str]] = {
        ("services/api-gateway/core/chat_graph_runner.py", "run_chat_graph"),
        ("services/api-gateway/core/chat_history_persist.py", "_touch_loop_activity_if_configured"),
        ("services/api-gateway/core/chat_invoke_finalize.py", "finalize_chat_response"),
    }
    found: set[tuple[str, str]] = set()
    pattern = re.compile(r"DuckClaw\([^)]*read_only=False", re.DOTALL)
    for path in _py_files():
        source = path.read_text(encoding="utf-8")
        for match in pattern.finditer(source):
            found.add((path.as_posix(), _function_name_before(source, match.start())))

    assert found == allowed


def test_gateway_main_delegates_legacy_fly_rw_exception_to_owner() -> None:
    main = (GATEWAY_ROOT / "main.py").read_text(encoding="utf-8")
    graph_owner = (GATEWAY_ROOT / "core" / "chat_graph_runner.py").read_text(encoding="utf-8")
    fly_owner = (GATEWAY_ROOT / "core" / "fly_command_invocation.py").read_text(encoding="utf-8")

    assert "invoke_legacy_fly_command" in graph_owner
    assert "DuckClaw(" not in main
    assert "DuckClaw(vault_db_path, read_only=read_only" in fly_owner
    assert "return DuckClaw(vault_db_path, read_only=read_only, engine=\"python\")" in fly_owner


def test_gateway_fly_rw_exception_excludes_read_only_safe_commands() -> None:
    fly_owner = (GATEWAY_ROOT / "core" / "fly_command_invocation.py").read_text(encoding="utf-8")

    assert "READ_ONLY_SAFE_FLY_COMMANDS" in fly_owner
    assert '"context"' in fly_owner
    assert '"workers"' in fly_owner
    assert '"forget"' in fly_owner
    assert '"comfyui"' in fly_owner
    assert '"goals"' in fly_owner
    assert '"meditate"' in fly_owner
    assert '"reject-code"' in fly_owner
    assert '"reject_code"' in fly_owner
    assert '"approve-code"' in fly_owner
    assert '"approve_code"' in fly_owner
    assert '"resolve-uncertainty"' in fly_owner
    assert '"resolve_uncertainty"' in fly_owner
    assert "LEGACY_RW_FLY_COMMANDS" in fly_owner
    legacy_rw_segment = fly_owner.split("LEGACY_RW_FLY_COMMANDS", 1)[1].split(")", 1)[0]
    assert '"context"' not in legacy_rw_segment
    assert '"workers"' not in legacy_rw_segment
    assert '"forget"' not in legacy_rw_segment
    assert '"comfyui"' not in legacy_rw_segment
    assert '"goals"' not in legacy_rw_segment
    assert '"meditate"' not in legacy_rw_segment
    assert '"reject-code"' not in legacy_rw_segment
    assert '"reject_code"' not in legacy_rw_segment
    assert '"resolve-uncertainty"' not in legacy_rw_segment
    assert '"resolve_uncertainty"' not in legacy_rw_segment


def test_gateway_fly_rw_exception_lists_only_current_pending_commands() -> None:
    fly_owner = (GATEWAY_ROOT / "core" / "fly_command_invocation.py").read_text(encoding="utf-8")
    pending_legacy_rw: set[str] = set()

    assert _fly_command_set(fly_owner, "LEGACY_RW_FLY_COMMANDS") == pending_legacy_rw
    assert pending_legacy_rw.isdisjoint(
        _fly_command_set(fly_owner, "_CORE_READ_ONLY_SAFE_FLY_COMMANDS")
    )


def test_gateway_raw_query_payloads_are_limited_to_compat_enqueue() -> None:
    allowed = {("services/api-gateway/routers/db_write_compat.py", "enqueue_write")}
    found: set[tuple[str, str]] = set()
    for path in _py_files():
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r'"query"\s*:', source):
            found.add((path.as_posix(), _function_name_before(source, match.start())))

    assert found == allowed


def test_legacy_raw_query_enqueue_has_audited_compat_comment() -> None:
    compat_router = (GATEWAY_ROOT / "routers" / "db_write_compat.py").read_text(encoding="utf-8")
    segment = compat_router.split("async def enqueue_write(", 1)[1].split("\n\n", 1)[0]

    assert "DB-first compat allowlist: /api/v1/db/write" in segment
    assert "Prefer typed WriteCommand payloads for structured admin mutations" in segment


def test_gateway_main_no_longer_owns_legacy_raw_query_enqueue() -> None:
    main = (GATEWAY_ROOT / "main.py").read_text(encoding="utf-8")

    assert "async def enqueue_write(" not in main
    assert "DB-first compat allowlist: /api/v1/db/write" not in main
    assert "db_write_compat_router" in main


def test_gateway_main_delegates_lifespan_to_core_module() -> None:
    main = (GATEWAY_ROOT / "main.py").read_text(encoding="utf-8")
    lifespan_owner = (GATEWAY_ROOT / "core" / "lifespan.py").read_text(encoding="utf-8")

    assert "from core.lifespan import lifespan" in main
    assert "async def lifespan" not in main
    assert "assert_gateway_startup_ready" not in main
    assert "async def lifespan" in lifespan_owner
    assert "assert_gateway_startup_ready" in lifespan_owner


def test_gateway_main_delegates_health_to_core_module() -> None:
    main = (GATEWAY_ROOT / "main.py").read_text(encoding="utf-8")
    health_owner = (GATEWAY_ROOT / "core" / "health.py").read_text(encoding="utf-8")

    assert "from core.health import router as health_router" in main
    assert "app.include_router(health_router)" in main
    assert "async def root()" not in main
    assert "async def health()" not in main
    assert "async def system_health()" not in main
    assert "_telegram_path_route_count" not in main
    assert '@router.get("/health")' in health_owner
    assert "async def system_health" in health_owner


def test_gateway_main_delegates_homeostasis_to_core_module() -> None:
    main = (GATEWAY_ROOT / "main.py").read_text(encoding="utf-8")
    homeostasis_owner = (GATEWAY_ROOT / "core" / "homeostasis.py").read_text(encoding="utf-8")

    assert "from core.homeostasis import router as homeostasis_router" in main
    assert "app.include_router(homeostasis_router)" in main
    assert "async def homeostasis_status" not in main
    assert "async def homeostasis_ask_task" not in main
    assert "class AskTaskBody" not in main
    assert '@router.get("/api/v1/homeostasis/status")' in homeostasis_owner
    assert "async def homeostasis_ask_task" in homeostasis_owner


def test_gateway_main_delegates_middleware_to_core_module() -> None:
    main = (GATEWAY_ROOT / "main.py").read_text(encoding="utf-8")
    middleware_owner = (GATEWAY_ROOT / "core" / "middleware.py").read_text(encoding="utf-8")

    assert "from core.middleware import register_gateway_middleware" in main
    assert "register_gateway_middleware(app)" in main
    assert "async def observability_context_middleware" not in main
    assert "async def tailscale_auth_middleware" not in main
    assert "async def telegram_http_ingress_probe_middleware" not in main
    assert "def register_gateway_middleware" in middleware_owner
    assert "async def observability_context_middleware" in middleware_owner


def test_gateway_main_delegates_agent_routes_to_core_module() -> None:
    main = (GATEWAY_ROOT / "main.py").read_text(encoding="utf-8")
    agent_owner = (GATEWAY_ROOT / "core" / "agent_routes.py").read_text(encoding="utf-8")

    assert "from core.agent_routes import effective_tenant_id, router as agent_routes_router" in main
    assert "app.include_router(agent_routes_router)" in main
    assert "async def agent_workers" not in main
    assert "async def agent_history" not in main
    assert '@router.get("/api/v1/agent/workers")' in agent_owner
    assert "def effective_tenant_id" in agent_owner


def test_gateway_main_delegates_chat_locks_to_core_module() -> None:
    main = (GATEWAY_ROOT / "main.py").read_text(encoding="utf-8")
    graph_owner = (GATEWAY_ROOT / "core" / "chat_graph_runner.py").read_text(encoding="utf-8")
    locks_owner = (GATEWAY_ROOT / "core" / "chat_locks.py").read_text(encoding="utf-8")

    assert "from core.chat_locks import maybe_chat_lock_for_request" in graph_owner
    assert "async def _chat_lock" not in main
    assert "async def _maybe_chat_lock_for_request" not in main
    assert "def chat_parallel_invocations_enabled" in locks_owner
    assert "async def maybe_chat_lock_for_request" in locks_owner


def test_gateway_main_delegates_telegram_delivery_to_core_module() -> None:
    main = (GATEWAY_ROOT / "main.py").read_text(encoding="utf-8")
    delivery_owner = (GATEWAY_ROOT / "core" / "telegram_delivery.py").read_text(encoding="utf-8")

    assert "from core.telegram_delivery import" in main
    assert "def _outbound_deliver_chat_text_sync" not in main
    assert "def _deliver_outbound_by_channel" not in main
    assert "def outbound_deliver_chat_text_sync" in delivery_owner
    assert "def deliver_outbound_by_channel" in delivery_owner


def test_gateway_main_delegates_db_read_to_core_module() -> None:
    main = (GATEWAY_ROOT / "main.py").read_text(encoding="utf-8")
    db_read_owner = (GATEWAY_ROOT / "core" / "db_read_route.py").read_text(encoding="utf-8")

    assert "from core.db_read_route import router as db_read_router" in main
    assert "app.include_router(db_read_router)" in main
    assert "class ReadRequest" not in main
    assert "async def db_read" not in main
    assert "def resolve_db_path_for_vault" not in main
    assert '@router.post("/api/v1/db/read")' in db_read_owner


def test_gateway_main_delegates_agent_chat_to_core_module() -> None:
    main = (GATEWAY_ROOT / "main.py").read_text(encoding="utf-8")
    chat_owner = (GATEWAY_ROOT / "core" / "agent_chat.py").read_text(encoding="utf-8")
    routes_owner = (GATEWAY_ROOT / "core" / "chat_http_routes.py").read_text(encoding="utf-8")
    auth_owner = (GATEWAY_ROOT / "core" / "chat_auth.py").read_text(encoding="utf-8")
    format_owner = (GATEWAY_ROOT / "core" / "chat_reply_format.py").read_text(encoding="utf-8")

    assert "from core.agent_chat import invoke_chat, resolve_chat_session_id, router as agent_chat_router" in main
    assert "app.include_router(agent_chat_router)" in main
    assert "invoke_agent_chat=invoke_chat" in main
    assert "async def agent_chat" not in main
    assert "async def _invoke_chat" not in main
    assert "async def invoke_chat" in chat_owner
    assert '@router.post("/api/v1/agent/chat")' in routes_owner
    assert "_AUTHORIZED_USERS_TABLE_DDL" in auth_owner
    assert "async def authorize_or_reject" in auth_owner
    assert "def clean_agent_response" in format_owner
    assert "def clean_agent_response" not in main


def test_gateway_main_delegates_chat_auth_format_visual_to_core_modules() -> None:
    main = (GATEWAY_ROOT / "main.py").read_text(encoding="utf-8")
    visual_owner = (GATEWAY_ROOT / "core" / "chat_visual_artifacts.py").read_text(encoding="utf-8")
    vault_owner = (GATEWAY_ROOT / "core" / "gateway_vault.py").read_text(encoding="utf-8")

    assert "from core.chat_auth import authorize_or_reject" in main
    assert "from core.chat_reply_format import clean_agent_response" in main
    assert "from core.chat_visual_artifacts import" in main
    assert "from core.gateway_vault import dedicated_gateway_vault_db_path" in main
    assert "def admin_visual_fields_from_invoke_result" in visual_owner
    assert "def dedicated_gateway_vault_db_path" in vault_owner
    assert "async def _lookup_whitelist_role" not in main
    assert "def _persist_admin_fly_charts" not in main


def test_admin_domains_do_not_call_legacy_raw_write_queue() -> None:
    offenders = []
    for path in sorted((GATEWAY_ROOT / "routers" / "admin_domains").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "enqueue_duckdb_write_sync" in source:
            offenders.append(path.as_posix())

    assert offenders == []


def test_gateway_core_has_no_capadonna_plugin_imports() -> None:
    offenders: list[str] = []
    for path in _py_files():
        source = path.read_text(encoding="utf-8")
        if "duckclaw.capadonna_plugin" in source or "capadonna_plugin" in source:
            offenders.append(path.as_posix())
    assert offenders == []
