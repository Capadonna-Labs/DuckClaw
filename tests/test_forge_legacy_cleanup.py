from __future__ import annotations

import ast
import re
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
FORGE_ROOT = REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "forge"

REMOVED_LEGACY_PACKAGES = (
    FORGE_ROOT / "industries",
    FORGE_ROOT / "crm",
    FORGE_ROOT / "quotes",
    FORGE_ROOT / "sft",
    FORGE_ROOT / "models",
    FORGE_ROOT / "atoms",
)
REMOVED_LEGACY_ATOMS = (
    FORGE_ROOT / "atoms" / "macro_pgq_seed.py",
    FORGE_ROOT / "atoms" / "macro_regime_detector.py",
    FORGE_ROOT / "atoms" / "moc_allocation.py",
    FORGE_ROOT / "atoms" / "moc_allocation_v2.py",
    FORGE_ROOT / "atoms" / "moc_intraday_hints.py",
    FORGE_ROOT / "atoms" / "pqrsd_radicacion_playwright.py",
    FORGE_ROOT / "atoms" / "reddit_listing_to_nl.py",
    FORGE_ROOT / "atoms" / "subagents.py",
)
REMOVED_LEGACY_MODELS = (
    FORGE_ROOT / "models" / "__init__.py",
    FORGE_ROOT / "models" / "core_satellite.py",
)
REMOVED_VERTICAL_CORE_MODULES = (
    REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "egress" / "job_hunter_output_validator.py",
    REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "github" / "workflow.py",
    FORGE_ROOT / "skills" / "github_bridge.py",
    REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "guardrails" / "capabilities" / "job_hunter.md",
    REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "guardrails" / "manager_tasks" / "job_application_tracking.md",
    REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "guardrails" / "manager_tasks" / "job_income_injection.md",
    REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "guardrails" / "manager_tasks" / "job_opportunity_tracking.md",
)

BACKEND_SCAN_ROOTS = (
    REPO_ROOT / "packages" / "agents",
    REPO_ROOT / "packages" / "duckops",
    REPO_ROOT / "packages" / "shared" / "src",
    REPO_ROOT / "services",
    REPO_ROOT / "scripts",
    REPO_ROOT / "tests",
    REPO_ROOT / "config",
)

RUNTIME_PYTHON_SCAN_ROOTS = (
    REPO_ROOT / "packages" / "agents" / "src" / "duckclaw",
    REPO_ROOT / "services",
)

BANNED_BACKEND_REFERENCES = (
    "duckclaw.forge.industries",
    "duckclaw.forge.atoms",
    "duckclaw/forge/industries",
    "duckclaw/forge/atoms",
    "forge/industries",
    "forge/atoms",
    "INDUSTRIES_TEMPLATES_DIR",
    "industries_data",
    "duckclaw.forge.atoms.macro_pgq_seed",
    "duckclaw.forge.atoms.macro_regime_detector",
    "duckclaw.forge.atoms.moc_allocation",
    "duckclaw.forge.atoms.moc_allocation_v2",
    "duckclaw.forge.atoms.moc_intraday_hints",
    "duckclaw.forge.atoms.pqrsd_radicacion_playwright",
    "duckclaw.forge.atoms.reddit_listing_to_nl",
    "duckclaw.forge.atoms.subagents",
    "duckclaw.forge.models",
    "forge/atoms/macro_pgq_seed.py",
    "forge/atoms/macro_regime_detector.py",
    "forge/atoms/moc_allocation.py",
    "forge/atoms/moc_allocation_v2.py",
    "forge/atoms/moc_intraday_hints.py",
    "forge/atoms/pqrsd_radicacion_playwright.py",
    "forge/atoms/reddit_listing_to_nl.py",
    "forge/atoms/subagents.py",
    "forge/models/core_satellite.py",
    "forge/models",
    "HRPMandateRow",
    "TargetAllocationDict",
    "MOCPipelineSignalSummary",
    "WeeklyHRPNotice",
    "MacroRegimeSnapshot",
    "MOCTargetAllocationV2",
    "duckclaw.egress.job_hunter_output_validator",
    "duckclaw.github.workflow",
    "duckclaw.forge.skills.github_bridge",
    "guardrails/capabilities/job_hunter.md",
    "guardrails/manager_tasks/job_application_tracking.md",
    "guardrails/manager_tasks/job_income_injection.md",
    "guardrails/manager_tasks/job_opportunity_tracking.md",
)

REMOVED_LEGACY_MODULE_PREFIXES = (
    "duckclaw.forge.crm",
    "duckclaw.forge.quotes",
    "duckclaw.forge.sft",
    "duckclaw.forge.models",
    "duckclaw.forge.industries",
    "duckclaw.forge.atoms",
    "duckclaw.egress.job_hunter_output_validator",
    "duckclaw.github.workflow",
    "duckclaw.forge.skills.github_bridge",
)
REMOVED_LEGACY_MODULE_NAMES = frozenset(
    prefix.rsplit(".", 1)[-1] for prefix in REMOVED_LEGACY_MODULE_PREFIXES
)
REMOVED_LEGACY_ATOM_MODULE_NAMES = frozenset(path.stem for path in REMOVED_LEGACY_ATOMS)

DB_FIRST_DDL_ALLOWLIST_REASONS = {
    "packages/agents/src/duckclaw/adf_validator.py": "validator creates isolated test/validation tables",
    "packages/agents/src/duckclaw/commands/chat_state.py": "legacy chat command agent_config bootstrap split from graph god file",
    "packages/agents/src/duckclaw/forge/rag/catalog.py": "derived RAG catalog bootstrap DDL",
    "packages/agents/src/duckclaw/forge/skills/quant_cfd_bridge.py": "quant control-plane table bootstrap",
    "packages/agents/src/duckclaw/graphs/graph_rag.py": "graph memory bootstrap DDL",
    "packages/agents/src/duckclaw/graphs/on_the_fly_commands.py": "chat command control-plane bootstrap",
    "packages/agents/src/duckclaw/graphs/telegram_bot.py": "telegram runtime bootstrap",
    "packages/agents/src/duckclaw/graphs/tools.py": "legacy tool schema bootstrap",
    "packages/agents/src/duckclaw/workers/db_runtime.py": "worker schema bootstrap",
    "packages/agents/src/duckclaw/workers/factory.py": "worker-local runtime bootstrap",
    "packages/agents/src/duckclaw/workers/loader.py": "worker belief bootstrap",
    "services/api-gateway/routers/admin.py": "authorized admin maintenance/bootstrap endpoints",
    "services/api-gateway/routers/admin_domains/runtime_config.py": "authorized admin runtime config bootstrap",
    "services/db-writer/context_injection_handler.py": "DB-writer context command schema",
    "services/db-writer/meditate_state_delta_handler.py": "DB-writer meditate command schema",
    "services/db-writer/quant_state_delta_handler.py": "DB-writer quant command schema",
    "services/db-writer/reports_state_delta_handler.py": "DB-writer reports command schema",
    "services/db-writer/visual_state_delta_handler.py": "DB-writer visual command schema",
}
DB_FIRST_DDL_ALLOWLIST = frozenset(DB_FIRST_DDL_ALLOWLIST_REASONS)

DB_FIRST_READ_WRITE_ALLOWLIST_REASONS = {
    "packages/agents/src/duckclaw/graphs/graph_server.py": "legacy graph command handler awaiting DB-writer migration",
    "packages/agents/src/duckclaw/forge/code_decision_service.py": "authorized code decision control-plane mutations",
    "services/api-gateway/main.py": "authorized command-plane bridge",
    "services/api-gateway/routers/admin.py": "authorized admin control-plane mutations",
    "services/api-gateway/routers/admin_db_first.py": "authorized DB-first admin mutators",
    "services/api-gateway/routers/admin_domains/duckdb_explorer.py": "authorized admin DuckDB maintenance mutators",
    "services/api-gateway/routers/admin_domains/playground_chat.py": "authorized admin playground conversation mutators",
    "services/db-writer/context_injection_handler.py": "DB-writer context mutations",
    "services/db-writer/main.py": "singleton DB-writer",
    "services/db-writer/meditate_state_delta_handler.py": "DB-writer meditate mutations",
    "services/db-writer/quant_state_delta_handler.py": "DB-writer quant mutations",
    "services/db-writer/reports_state_delta_handler.py": "DB-writer reports mutations",
    "services/db-writer/visual_state_delta_handler.py": "DB-writer visual mutations",
}
DB_FIRST_READ_WRITE_ALLOWLIST = frozenset(DB_FIRST_READ_WRITE_ALLOWLIST_REASONS)

SCAN_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".toml"}
IGNORED_DIRS = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__", "node_modules"}
CREATE_TABLE_RE = re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE)
REMOVED_LABOR_VERTICAL_MARKERS_RE = re.compile(
    r"(?i)(job[_ -]?hunter|jobhunter|empleo|trabajo|vacante|postul|career|TELEGRAM_JOB_HUNTER_TOKEN)"
)
DOMAIN_DB_PATH_ENV_RE = re.compile(
    r"\bDUCKCLAW_(FINANZ|JOB_HUNTER|SIATA|QUANT_TRADER|WAR_ROOM_ACL)_DB_PATH\b"
)
REMOVED_TENANT_DEMO_TABLE_NAMES = frozenset({"leila_orders", "leila_products"})
REMOVED_TENANT_DOMAIN_SCHEMA_MARKERS = frozenset(
    {
        "TENANT_EXTRA_" "SCHEMAS",
        '"leila"',
        '"quant"',
        '"quant_core"',
        '"war_room"',
        '"war_room_core"',
    }
)
REMOVED_TEAM_ENV_TENANT_INFERENCE_MARKERS = frozenset(
    {
        "BI-Analyst",
        "SIATA",
        "bi_analyst",
        "siatadb",
    }
)
REMOVED_GATEWAY_WAR_ROOM_MARKERS = frozenset(
    {
        "war_room",
        "war_rooms",
        "wr_",
        "wr_members",
        "wr_audit_log",
        "war room",
    }
)
REMOVED_DOMAIN_VERTICAL_MARKERS_RE = re.compile(
    r"(?i)(?<![a-z0-9])("
    r"quant(?:[_-]?(?:trader|core|state|tool|market|price|bracket|trading|cfd|hrp|moc|visual))?"
    r"|finanz(?:as)?"
    r"|finance(?:_worker|_ledger)?"
    r"|pqrsd"
    r"|pqrs"
    r"|leila"
    r"|war_room"
    r"|wr_"
    r")(?![a-z0-9])"
)
DOMAIN_VERTICAL_RUNTIME_ALLOWLIST_REASONS = {
    "packages/agents/src/duckclaw/capadonna_plugin.py": "external Capadonna compatibility; not part of this cut unless vertical tokens appear in core",
    "packages/agents/src/duckclaw/finance/__init__.py": "pending domain package removal after factory cut",
    "packages/agents/src/duckclaw/finance/runtime_policy.py": "pending domain package removal after factory cut",
    "packages/agents/src/duckclaw/forge/code_decision_service.py": "pending domain-specific control-plane extraction",
    "packages/agents/src/duckclaw/forge/skills/comfyui_bridge.py": "pending visual bridge context genericization",
    "packages/agents/src/duckclaw/forge/skills/edge_bridge.py": "pending state-delta queue genericization",
    "packages/agents/src/duckclaw/forge/skills/fal_bridge.py": "Capadonna bridge pending generic context rename",
    "packages/agents/src/duckclaw/forge/skills/google_trends_bridge.py": "pending market-specific bridge extraction",
    "packages/agents/src/duckclaw/forge/skills/reddit_bridge.py": "pending spec comment cleanup",
    "packages/agents/src/duckclaw/forge/skills/reports_state_delta.py": "pending shared writer utility extraction",
    "packages/agents/src/duckclaw/forge/skills/visual_state_delta.py": "pending shared writer utility extraction",
    "packages/agents/src/duckclaw/forge/team_env.py": "pending legacy env example cleanup",
    "packages/agents/src/duckclaw/graphs/agent_resilience.py": "pending generic tool-pressure policy",
    "packages/agents/src/duckclaw/graphs/dreamer_job.py": "pending domain-specific dreamer extraction",
    "packages/agents/src/duckclaw/graphs/router.py": "pending retail intent language cleanup",
    "packages/agents/src/duckclaw/quant/__init__.py": "pending domain package removal after factory cut",
    "packages/agents/src/duckclaw/quant/runtime_policy.py": "pending domain package removal after factory cut",
    "packages/agents/src/duckclaw/workers/field_reflection.py": "pending field reflection naming cleanup",
    "packages/agents/src/duckclaw/workers/loader.py": "pending worker metadata naming cleanup",
    "packages/agents/src/duckclaw/workers/manifest.py": "pending capability schema rename",
    "packages/agents/src/duckclaw/workers/run_worker.py": "pending CLI example cleanup",
    "packages/agents/src/duckclaw/workers/tool_invocation_policy.py": "pending capability policy rename",
    "services/api-gateway/routers/admin.py": "pending admin quant diagnostics removal",
    "services/api-gateway/routers/admin_domains/visual_assets.py": "pending Capadonna context genericization",
    "services/api-gateway/routers/telegram_inbound_webhook.py": "pending auto-execution text genericization",
    "services/db-writer/quant_state_delta_handler.py": "domain-specific writer handler; disabled from core loop in this cut",
    "services/db-writer/models/quant_state_delta.py": "domain-specific writer DTO; disabled from core loop in this cut",
}
DOMAIN_VERTICAL_RUNTIME_ALLOWLIST = frozenset(DOMAIN_VERTICAL_RUNTIME_ALLOWLIST_REASONS)
ON_THE_FLY_COMMAND_GRAPH = (
    REPO_ROOT
    / "packages"
    / "agents"
    / "src"
    / "duckclaw"
    / "graphs"
    / "on_the_fly_commands.py"
)
ON_THE_FLY_VERTICAL_MARKERS_RE = re.compile(
    r"(?i)(?<![a-z0-9])("
    r"quant(?:[_-]?(?:trader|core|trading|market|cfd|hrp|moc|auto))?"
    r"|finanz(?:as)?"
    r"|finance"
    r"|ibkr"
    r"|trader"
    r"|broker"
    r"|drawdown"
    r"|pnl"
    r"|trading[_ -]?session"
    r"|propose_trade_signal"
    r"|get_ibkr_portfolio"
    r"|fetch_ib_gateway_ohlcv"
    r"|tickers?"
    r")(?![a-z0-9])"
)
HEARTBEAT_BASE = REPO_ROOT / "services" / "heartbeat" / "main.py"
HEARTBEAT_VERTICAL_MARKERS_RE = re.compile(
    r"(?i)(?<![a-z0-9])("
    r"quant(?:[_-]?(?:trader|core|trading|market|cfd|hrp|moc|auto|state))?"
    r"|finanz(?:as)?"
    r"|finance(?:_worker|_ledger)?"
    r"|ibkr"
    r"|trader"
    r"|broker"
    r"|drawdown"
    r"|trading[_ -]?session"
    r"|trading_session_[a-z0-9_]+"
    r"|trade[_ -]?signal"
    r"|signals_proposed"
    r"|tickers"
    r"|trading[_ -]?tick"
    r"|maximize_pnl"
    r"|pnl"
    r")(?![a-z0-9])"
)
HOMEOSTASIS_GOALS_ALIGNMENT = (
    REPO_ROOT
    / "packages"
    / "agents"
    / "src"
    / "duckclaw"
    / "homeostasis"
    / "goals_alignment.py"
)
HOMEOSTASIS_CANONICAL_ROOT = (
    REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "homeostasis"
)
HOMEOSTASIS_OPERATION_DOCS = (
    REPO_ROOT / "docs" / "operations" / "Homeostasis-Heartbeat.md",
    REPO_ROOT / "docs" / "operations" / "Meditate-Homeostasis.md",
)
MEDITATE_HARNESS_SOURCE_TABLE_FILES = (
    REPO_ROOT / "harness_core" / "states" / "meditate_state.py",
    REPO_ROOT / "harness_core" / "skills" / "emit_correction_delta.py",
)
LEGACY_SINGLETON_WRITER = (
    FORGE_ROOT / "homeostasis" / "singleton_writer.py"
)
DOCS_SINGLETON_WRITER_SCAN_ROOTS = (
    REPO_ROOT / "docs" / "core",
    REPO_ROOT / "docs" / "architecture",
    REPO_ROOT / "docs" / "api",
    REPO_ROOT / "docs" / "operations",
)
LEGACY_SINGLETON_WRITER_DOC_PATTERNS = (
    "duckclaw.forge.homeostasis.singleton_writer",
    "forge/homeostasis/singleton_writer.py",
    "python -m duckclaw.forge.homeostasis.singleton_writer",
    "singleton_writer.run_consumer()",
)
HOMEOSTASIS_VERTICAL_MARKERS_RE = re.compile(
    r"(?i)(?<![a-z0-9])("
    r"quant(?:[_-]?(?:trader|core|trading|market|cfd|hrp|moc|auto|state))?"
    r"|finanz(?:as)?"
    r"|finance(?:_worker|_ledger)?"
    r"|ibkr"
    r"|trader"
    r"|broker"
    r"|drawdown"
    r"|trading[_ -]?session"
    r"|trading_session_[a-z0-9_]+"
    r"|trade[_ -]?signal"
    r"|tickers?"
    r"|pnl"
    r")(?![a-z0-9])"
)
HOMEOSTASIS_DOC_VERTICAL_MARKERS_RE = re.compile(
    r"(?i)(?<![a-z0-9])("
    r"quant(?:[_-]?(?:trader|core|trading|market|cfd|hrp|moc|auto|state))?"
    r"|finanz(?:as)?"
    r"|finance(?:_worker|_ledger)?"
    r"|ibkr"
    r"|trader"
    r"|broker"
    r"|drawdown"
    r"|trading[_ -]?session"
    r"|trading_session_[a-z0-9_]+"
    r"|trade[_ -]?signal"
    r"|pnl"
    r")(?![a-z0-9])"
)
SANDBOX_VERTICAL_MARKERS_RE = re.compile(
    r"(?i)(?<![a-z0-9])("
    r"mql5"
    r"|ml4t"
    r"|pypfopt"
    r"|pyportfolioopt"
    r"|quant"
    r"|finanz"
    r"|trading"
    r"|broker"
    r")(?![a-z0-9])"
)
REMOVED_DOMAIN_WORKER_ID_SHIMS = frozenset(
    {
        "WORKER_FINANZ",
        "WORKER_QUANT_TRADER",
        "WORKER_JOB_HUNTER",
        "WORKER_SIATA_ANALYST",
        "MARKET_WORKERS",
        "PLOT_CAPABLE_WORKERS",
    }
)
LABOR_VERTICAL_RESIDUE_SCAN_TARGETS = (
    REPO_ROOT / ".env.example",
    REPO_ROOT / "config",
    REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "graphs" / "on_the_fly_commands.py",
    REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "graphs" / "sandbox.py",
    REPO_ROOT / "tests" / "test_telegram_agent_token.py",
    REPO_ROOT / "tests" / "test_manager_telegram_env_overlay.py",
    REPO_ROOT / "tests" / "test_telegram_guard_team_whitelist.py",
    REPO_ROOT / "tests" / "test_sovereign_wizard.py",
)


def _backend_files() -> list[Path]:
    files: list[Path] = []
    for root in BACKEND_SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            if path.is_file() and path.suffix in SCAN_SUFFIXES:
                files.append(path)
    return files


def _runtime_python_files() -> list[Path]:
    files: list[Path] = []
    for root in RUNTIME_PYTHON_SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            files.append(path)
    return files


def _parse_python(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _rel(path: Path) -> str:
    return path.relative_to(REPO_ROOT).as_posix()


def _module_matches_prefix(module: str, prefix: str) -> bool:
    return module == prefix or module.startswith(f"{prefix}.")


def _call_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def _string_literal(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def test_removed_legacy_forge_packages_stay_removed() -> None:
    existing = [_rel(path) for path in REMOVED_LEGACY_PACKAGES if path.exists()]
    assert existing == []


def test_removed_legacy_forge_atoms_stay_removed() -> None:
    existing = [str(path.relative_to(REPO_ROOT)) for path in REMOVED_LEGACY_ATOMS if path.exists()]
    assert existing == []


def test_removed_legacy_forge_models_stay_removed() -> None:
    existing = [str(path.relative_to(REPO_ROOT)) for path in REMOVED_LEGACY_MODELS if path.exists()]
    assert existing == []


def test_removed_job_hunter_and_github_vertical_core_modules_stay_removed() -> None:
    existing = [_rel(path) for path in REMOVED_VERTICAL_CORE_MODULES if path.exists()]
    assert existing == []


def test_backend_does_not_reference_removed_legacy_forge_packages() -> None:
    offenders: list[str] = []
    current_test = Path(__file__).resolve()
    for path in _backend_files():
        if path.resolve() == current_test:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in BANNED_BACKEND_REFERENCES:
            if pattern in text:
                offenders.append(f"{path.relative_to(REPO_ROOT)}: {pattern}")

    assert offenders == []


def test_runtime_python_does_not_import_removed_forge_packages() -> None:
    offenders: list[str] = []
    for path in _runtime_python_files():
        tree = _parse_python(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if any(
                        _module_matches_prefix(alias.name, prefix)
                        for prefix in REMOVED_LEGACY_MODULE_PREFIXES
                    ):
                        offenders.append(f"{_rel(path)}:{node.lineno}: import {alias.name}")

            if not isinstance(node, ast.ImportFrom):
                continue
            module = node.module or ""
            if any(_module_matches_prefix(module, prefix) for prefix in REMOVED_LEGACY_MODULE_PREFIXES):
                offenders.append(f"{_rel(path)}:{node.lineno}: from {module} import ...")
                continue
            if module == "duckclaw.forge":
                for alias in node.names:
                    if alias.name in REMOVED_LEGACY_MODULE_NAMES:
                        offenders.append(f"{_rel(path)}:{node.lineno}: from {module} import {alias.name}")
            if module == "duckclaw.forge.atoms":
                for alias in node.names:
                    if alias.name in REMOVED_LEGACY_ATOM_MODULE_NAMES:
                        offenders.append(f"{_rel(path)}:{node.lineno}: from {module} import {alias.name}")

    assert offenders == []


def test_runtime_python_does_not_load_removed_guardrail_policy_dirs() -> None:
    offenders: list[str] = []
    for path in _runtime_python_files():
        tree = _parse_python(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if _call_name(node.func) != "load_guardrail" or not node.args:
                continue
            first_arg = _string_literal(node.args[0])
            if first_arg in {"directives", "capabilities"}:
                offenders.append(f"{_rel(path)}:{node.lineno}: load_guardrail({first_arg!r}, ...)")

    assert offenders == []


def test_runtime_python_does_not_reintroduce_default_prompt_policies() -> None:
    offenders: list[str] = []
    for path in _runtime_python_files():
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "DEFAULT_PROMPT_POLICIES" in text:
            offenders.append(_rel(path))

    assert offenders == []


def test_worker_identity_module_exposes_only_generic_predicates() -> None:
    identity_path = REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "workers" / "identity.py"
    tree = _parse_python(identity_path)
    public_functions = [
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and not node.name.startswith("_")
    ]
    domain_predicates = [
        name for name in public_functions if name.startswith("is_") and name != "is_worker"
    ]
    legacy_constants: list[str] = []
    for node in tree.body:
        targets: list[ast.expr] = []
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]
        for target in targets:
            if not isinstance(target, ast.Name):
                continue
            if target.id.startswith("WORKER_") or target.id in {"MARKET_WORKERS", "PLOT_CAPABLE_WORKERS"}:
                legacy_constants.append(target.id)

    assert domain_predicates == []
    assert legacy_constants == []


def test_runtime_python_does_not_import_legacy_worker_ids() -> None:
    offenders: list[str] = []
    legacy_module_path = (
        REPO_ROOT
        / "packages"
        / "agents"
        / "src"
        / "duckclaw"
        / "workers"
        / "worker_ids.py"
    )
    for path in _runtime_python_files():
        if path == legacy_module_path:
            continue
        tree = _parse_python(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "duckclaw.workers.worker_ids":
                        offenders.append(f"{_rel(path)}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "duckclaw.workers.worker_ids":
                    offenders.append(f"{_rel(path)}:{node.lineno}: from {module} import ...")

    assert offenders == []


def test_runtime_python_does_not_reintroduce_domain_worker_id_shims() -> None:
    offenders: list[str] = []
    current_test = Path(__file__).resolve()
    for path in _runtime_python_files():
        if path.resolve() == current_test:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in REMOVED_DOMAIN_WORKER_ID_SHIMS:
            if marker in text:
                offenders.append(f"{_rel(path)}: {marker}")

    assert offenders == []


def test_labor_vertical_residues_are_absent_from_core_config_and_telegram_tests() -> None:
    offenders: list[str] = []
    for target in LABOR_VERTICAL_RESIDUE_SCAN_TARGETS:
        if target.is_dir():
            candidates = [
                path
                for path in target.rglob("*")
                if path.is_file()
                and path.suffix in SCAN_SUFFIXES
                and not any(part in IGNORED_DIRS for part in path.parts)
            ]
        else:
            candidates = [target] if target.exists() else []
        for path in candidates:
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in REMOVED_LABOR_VERTICAL_MARKERS_RE.finditer(text):
                offenders.append(f"{_rel(path)}:{match.start()}: {match.group(0)}")

    assert offenders == []


def test_on_the_fly_command_graph_has_no_quant_finance_trading_residue() -> None:
    text = ON_THE_FLY_COMMAND_GRAPH.read_text(encoding="utf-8", errors="ignore")
    offenders = [
        f"{match.start()}: {match.group(0)}"
        for match in ON_THE_FLY_VERTICAL_MARKERS_RE.finditer(text)
    ]

    assert offenders == []


def test_sandbox_graph_has_no_domain_specific_runtime_guidance() -> None:
    sandbox_path = REPO_ROOT / "packages" / "agents" / "src" / "duckclaw" / "graphs" / "sandbox.py"
    text = sandbox_path.read_text(encoding="utf-8", errors="ignore")
    offenders = [
        f"{match.start()}: {match.group(0)}"
        for match in SANDBOX_VERTICAL_MARKERS_RE.finditer(text)
    ]

    assert offenders == []


def test_heartbeat_base_has_no_quant_finance_trading_residue() -> None:
    text = HEARTBEAT_BASE.read_text(encoding="utf-8", errors="ignore")
    offenders = [
        f"{match.start()}: {match.group(0)}"
        for match in HEARTBEAT_VERTICAL_MARKERS_RE.finditer(text)
    ]

    assert offenders == []


def test_homeostasis_goals_alignment_has_no_quant_finance_trading_residue() -> None:
    text = HOMEOSTASIS_GOALS_ALIGNMENT.read_text(encoding="utf-8", errors="ignore")
    offenders = [
        f"{match.start()}: {match.group(0)}"
        for match in HOMEOSTASIS_VERTICAL_MARKERS_RE.finditer(text)
    ]

    assert offenders == []


def test_meditate_harness_uses_transversal_stale_task_source_table() -> None:
    offenders: list[str] = []
    for path in MEDITATE_HARNESS_SOURCE_TABLE_FILES:
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "quant_core.trade_signals" in text:
            offenders.append(f"{_rel(path)}: quant_core.trade_signals")

    assert offenders == []


def test_homeostasis_operation_docs_use_generic_metrics() -> None:
    offenders: list[str] = []
    for path in HOMEOSTASIS_OPERATION_DOCS:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for match in HOMEOSTASIS_DOC_VERTICAL_MARKERS_RE.finditer(text):
            offenders.append(f"{_rel(path)}:{match.start()}: {match.group(0)}")

    assert offenders == []


def test_canonical_homeostasis_package_does_not_depend_on_forge_homeostasis() -> None:
    offenders: list[str] = []
    for path in HOMEOSTASIS_CANONICAL_ROOT.rglob("*.py"):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        tree = _parse_python(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _module_matches_prefix(alias.name, "duckclaw.forge.homeostasis"):
                        offenders.append(f"{_rel(path)}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if _module_matches_prefix(module, "duckclaw.forge.homeostasis"):
                    offenders.append(f"{_rel(path)}:{node.lineno}: from {module} import ...")

    assert offenders == []


def test_core_runtime_uses_db_write_queue_for_singleton_writer_imports() -> None:
    offenders: list[str] = []
    for path in _runtime_python_files():
        if path.resolve() == LEGACY_SINGLETON_WRITER.resolve():
            continue
        tree = _parse_python(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "duckclaw.forge.homeostasis.singleton_writer":
                        offenders.append(f"{_rel(path)}:{node.lineno}: import {alias.name}")
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                if module == "duckclaw.forge.homeostasis.singleton_writer":
                    offenders.append(f"{_rel(path)}:{node.lineno}: from {module} import ...")

    assert offenders == []


def test_core_docs_recommend_db_write_queue_for_singleton_writer() -> None:
    offenders: list[str] = []
    for root in DOCS_SINGLETON_WRITER_SCAN_ROOTS:
        if not root.exists():
            continue
        for path in root.rglob("*.md"):
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for pattern in LEGACY_SINGLETON_WRITER_DOC_PATTERNS:
                if pattern in text:
                    offenders.append(f"{_rel(path)}: {pattern}")

    assert offenders == []


def test_gateway_db_does_not_define_domain_specific_path_env_keys() -> None:
    gateway_db_path = REPO_ROOT / "packages" / "shared" / "src" / "duckclaw" / "gateway_db.py"
    text = gateway_db_path.read_text(encoding="utf-8")

    offenders = sorted(set(DOMAIN_DB_PATH_ENV_RE.findall(text)))

    assert offenders == []


def test_backend_and_tooling_do_not_define_domain_specific_db_path_env_keys() -> None:
    offenders: list[str] = []
    current_test = Path(__file__).resolve()
    for path in _backend_files():
        if path.resolve() == current_test:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        if DOMAIN_DB_PATH_ENV_RE.search(text):
            offenders.append(_rel(path))

    assert offenders == []


def test_cleanup_default_tenant_tool_does_not_name_demo_tables() -> None:
    cleanup_path = REPO_ROOT / "scripts" / "cleanup_default_duckdb_tenant_schemas.py"
    text = cleanup_path.read_text(encoding="utf-8")

    offenders = sorted(name for name in REMOVED_TENANT_DEMO_TABLE_NAMES if name in text)

    assert offenders == []


def test_cleanup_default_tenant_tool_does_not_hardcode_domain_schemas() -> None:
    cleanup_path = REPO_ROOT / "scripts" / "cleanup_default_duckdb_tenant_schemas.py"
    text = cleanup_path.read_text(encoding="utf-8")

    offenders = sorted(marker for marker in REMOVED_TENANT_DOMAIN_SCHEMA_MARKERS if marker in text)

    assert offenders == []


def test_team_env_does_not_infer_tenant_from_vertical_process_or_path_names() -> None:
    team_env_path = FORGE_ROOT / "team_env.py"
    text = team_env_path.read_text(encoding="utf-8")

    offenders = sorted(marker for marker in REMOVED_TEAM_ENV_TENANT_INFERENCE_MARKERS if marker in text)

    assert offenders == []


def test_shared_schema_migrations_do_not_register_war_room_core() -> None:
    migrations_path = REPO_ROOT / "packages" / "shared" / "src" / "duckclaw" / "schema_migrations.py"
    text = migrations_path.read_text(encoding="utf-8")
    removed_markers = (
        "war_room_core",
        "M019_WAR_ROOM_CORE",
        "wr_members",
        "wr_audit_log",
    )

    offenders = [marker for marker in removed_markers if marker in text]

    assert offenders == []


def test_generic_bootstrap_does_not_create_war_room_core() -> None:
    bootstrap_path = REPO_ROOT / "scripts" / "bootstrap_dbs.py"
    text = bootstrap_path.read_text(encoding="utf-8")
    removed_markers = (
        "war_room_core",
        "wr_members",
        "wr_audit_log",
    )

    offenders = [marker for marker in removed_markers if marker in text]

    assert offenders == []


def test_gateway_base_does_not_embed_war_room_runtime() -> None:
    gateway_root = REPO_ROOT / "services" / "api-gateway"
    removed_files = (
        gateway_root / "core" / "war_rooms.py",
    )
    existing = [_rel(path) for path in removed_files if path.exists()]
    offenders = [f"{path}: file exists" for path in existing]

    for path in gateway_root.rglob("*.py"):
        if any(part in IGNORED_DIRS for part in path.parts):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore").lower()
        for marker in REMOVED_GATEWAY_WAR_ROOM_MARKERS:
            if marker in text:
                offenders.append(f"{_rel(path)}: {marker}")

    assert offenders == []


def test_runtime_and_tooling_do_not_reintroduce_removed_demo_tables() -> None:
    scan_roots = (
        REPO_ROOT / "packages" / "agents" / "src",
        REPO_ROOT / "packages" / "shared" / "src",
        REPO_ROOT / "packages" / "duckops",
        REPO_ROOT / "services",
        REPO_ROOT / "scripts",
        REPO_ROOT / "tests",
    )
    current_test = Path(__file__).resolve()
    offenders: list[str] = []
    for root in scan_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.resolve() == current_test or any(part in IGNORED_DIRS for part in path.parts):
                continue
            if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for name in REMOVED_TENANT_DEMO_TABLE_NAMES:
                if name in text:
                    offenders.append(f"{_rel(path)}: {name}")

    assert offenders == []


def test_core_framework_domain_vertical_markers_are_confined_to_explicit_allowlist() -> None:
    scan_roots = (
        REPO_ROOT / "packages" / "agents" / "src" / "duckclaw",
        REPO_ROOT / "packages" / "shared" / "src" / "duckclaw",
        REPO_ROOT / "services" / "api-gateway",
        REPO_ROOT / "services" / "db-writer",
        REPO_ROOT / "scripts",
    )
    ignored_script_dirs = {"deployment", "data_prep"}
    current_test = Path(__file__).resolve()
    offenders: list[str] = []
    for root in scan_roots:
        if not root.exists():
            continue
        for path in root.rglob("*"):
            if path.resolve() == current_test or any(part in IGNORED_DIRS for part in path.parts):
                continue
            if root.name == "scripts" and any(part in ignored_script_dirs for part in path.parts):
                continue
            if not path.is_file() or path.suffix not in SCAN_SUFFIXES:
                continue
            rel_path = _rel(path)
            if rel_path in DOMAIN_VERTICAL_RUNTIME_ALLOWLIST:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for match in REMOVED_DOMAIN_VERTICAL_MARKERS_RE.finditer(text):
                offenders.append(f"{rel_path}:{match.start()}: {match.group(0)}")

    assert offenders == []


def test_core_egress_uses_transversal_evidence_validator_imports() -> None:
    offenders: list[str] = []
    current_test = Path(__file__).resolve()
    allowed_legacy_alias = (
        REPO_ROOT
        / "packages"
        / "agents"
        / "src"
        / "duckclaw"
        / "egress"
        / "quant_price_validator.py"
    )
    scan_roots = (
        REPO_ROOT / "packages" / "agents" / "src" / "duckclaw",
        REPO_ROOT / "tests",
    )
    for root in scan_roots:
        if not root.exists():
            continue
        for path in root.rglob("*.py"):
            if path.resolve() in {current_test, allowed_legacy_alias.resolve()}:
                continue
            if any(part in IGNORED_DIRS for part in path.parts):
                continue
            tree = _parse_python(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        if alias.name == "duckclaw.egress.quant_price_validator":
                            offenders.append(f"{_rel(path)}:{node.lineno}: import {alias.name}")
                elif isinstance(node, ast.ImportFrom):
                    if node.module == "duckclaw.egress.quant_price_validator":
                        offenders.append(f"{_rel(path)}:{node.lineno}: from {node.module} import ...")

    assert offenders == []


def test_runtime_create_table_sql_is_confined_to_explicit_allowlist() -> None:
    offenders: list[str] = []
    for path in _runtime_python_files():
        rel_path = _rel(path)
        if rel_path in DB_FIRST_DDL_ALLOWLIST:
            continue
        tree = _parse_python(path)
        for node in ast.walk(tree):
            text = _string_literal(node)
            if text and CREATE_TABLE_RE.search(text):
                offenders.append(f"{rel_path}:{node.lineno}")

    assert offenders == []


def test_direct_read_write_duckdb_connections_are_confined_to_explicit_allowlist() -> None:
    offenders: list[str] = []
    for path in _runtime_python_files():
        rel_path = _rel(path)
        if rel_path in DB_FIRST_READ_WRITE_ALLOWLIST:
            continue
        tree = _parse_python(path)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for keyword in node.keywords:
                if (
                    keyword.arg == "read_only"
                    and isinstance(keyword.value, ast.Constant)
                    and keyword.value.value is False
                ):
                    offenders.append(f"{rel_path}:{node.lineno}")

    assert offenders == []
