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
    allowed = {
        ("services/api-gateway/core/fly_command_invocation.py", "_open_legacy_fly_duckclaw_rw"),
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
    fly_owner = (GATEWAY_ROOT / "core" / "fly_command_invocation.py").read_text(encoding="utf-8")

    assert "invoke_legacy_fly_command" in main
    assert "DuckClaw(" not in main
    assert "DB-first runtime compat allowlist: legacy slash/fly commands" in fly_owner
    assert "DuckClaw(vault_db_path, read_only=False" in fly_owner


def test_gateway_fly_rw_exception_excludes_read_only_safe_commands() -> None:
    fly_owner = (GATEWAY_ROOT / "core" / "fly_command_invocation.py").read_text(encoding="utf-8")

    assert "READ_ONLY_SAFE_FLY_COMMANDS" in fly_owner
    assert '"context"' in fly_owner
    assert '"workers"' in fly_owner
    assert '"forget"' in fly_owner
    assert "LEGACY_RW_FLY_COMMANDS" in fly_owner
    legacy_rw_segment = fly_owner.split("LEGACY_RW_FLY_COMMANDS", 1)[1].split(")", 1)[0]
    assert '"context"' not in legacy_rw_segment
    assert '"workers"' not in legacy_rw_segment
    assert '"forget"' not in legacy_rw_segment


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


def test_admin_domains_do_not_call_legacy_raw_write_queue() -> None:
    offenders = []
    for path in sorted((GATEWAY_ROOT / "routers" / "admin_domains").rglob("*.py")):
        source = path.read_text(encoding="utf-8")
        if "enqueue_duckdb_write_sync" in source:
            offenders.append(path.as_posix())

    assert offenders == []
