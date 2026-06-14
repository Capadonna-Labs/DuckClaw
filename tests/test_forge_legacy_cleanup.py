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
)

REMOVED_LEGACY_MODULE_PREFIXES = (
    "duckclaw.forge.crm",
    "duckclaw.forge.quotes",
    "duckclaw.forge.sft",
    "duckclaw.forge.models",
    "duckclaw.forge.industries",
    "duckclaw.forge.atoms",
)
REMOVED_LEGACY_MODULE_NAMES = frozenset(
    prefix.rsplit(".", 1)[-1] for prefix in REMOVED_LEGACY_MODULE_PREFIXES
)
REMOVED_LEGACY_ATOM_MODULE_NAMES = frozenset(path.stem for path in REMOVED_LEGACY_ATOMS)

DB_FIRST_DDL_ALLOWLIST_REASONS = {
    "packages/agents/src/duckclaw/adf_validator.py": "validator creates isolated test/validation tables",
    "packages/agents/src/duckclaw/forge/rag/catalog.py": "derived RAG catalog bootstrap DDL",
    "packages/agents/src/duckclaw/forge/skills/quant_cfd_bridge.py": "quant control-plane table bootstrap",
    "packages/agents/src/duckclaw/graphs/graph_rag.py": "graph memory bootstrap DDL",
    "packages/agents/src/duckclaw/graphs/on_the_fly_commands.py": "chat command control-plane bootstrap",
    "packages/agents/src/duckclaw/graphs/telegram_bot.py": "telegram runtime bootstrap",
    "packages/agents/src/duckclaw/graphs/tools.py": "legacy tool schema bootstrap",
    "packages/agents/src/duckclaw/workers/db_runtime.py": "worker schema bootstrap",
    "packages/agents/src/duckclaw/workers/factory.py": "worker-local runtime bootstrap",
    "packages/agents/src/duckclaw/workers/loader.py": "worker belief bootstrap",
    "services/api-gateway/core/war_rooms.py": "authorized war-room ACL bootstrap",
    "services/api-gateway/routers/admin.py": "authorized admin maintenance/bootstrap endpoints",
    "services/db-writer/context_injection_handler.py": "DB-writer context command schema",
    "services/db-writer/quant_state_delta_handler.py": "DB-writer quant command schema",
    "services/db-writer/visual_state_delta_handler.py": "DB-writer visual command schema",
}
DB_FIRST_DDL_ALLOWLIST = frozenset(DB_FIRST_DDL_ALLOWLIST_REASONS)

DB_FIRST_READ_WRITE_ALLOWLIST_REASONS = {
    "packages/agents/src/duckclaw/graphs/graph_server.py": "legacy graph command handler awaiting DB-writer migration",
    "packages/agents/src/duckclaw/graphs/on_the_fly_commands.py": "authorized chat command mutations",
    "services/api-gateway/main.py": "authorized command-plane bridge",
    "services/api-gateway/routers/admin.py": "authorized admin control-plane mutations",
    "services/api-gateway/routers/admin_db_first.py": "authorized DB-first admin mutators",
    "services/db-writer/context_injection_handler.py": "DB-writer context mutations",
    "services/db-writer/main.py": "singleton DB-writer",
    "services/db-writer/quant_state_delta_handler.py": "DB-writer quant mutations",
    "services/db-writer/visual_state_delta_handler.py": "DB-writer visual mutations",
}
DB_FIRST_READ_WRITE_ALLOWLIST = frozenset(DB_FIRST_READ_WRITE_ALLOWLIST_REASONS)

SCAN_SUFFIXES = {".py", ".yaml", ".yml", ".json", ".toml"}
IGNORED_DIRS = {".git", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".venv", "__pycache__", "node_modules"}
CREATE_TABLE_RE = re.compile(r"\bCREATE\s+TABLE\b", re.IGNORECASE)
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
