"""Sandbox orchestration repair stays domain-agnostic in duckclaw core."""

from __future__ import annotations

from pathlib import Path

from duckclaw.workers.sandbox_force_repair import (
    extract_python_from_llm_text,
    is_forced_sandbox_tool,
    resolve_orchestration_fallback_code,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
SANDBOX_FORCE_REPAIR = (
    REPO_ROOT
    / "packages"
    / "agents"
    / "src"
    / "duckclaw"
    / "workers"
    / "sandbox_force_repair.py"
)
FORGE_LEGACY_CLEANUP = REPO_ROOT / "tests" / "test_forge_legacy_cleanup.py"


def test_sandbox_force_repair_has_no_vertical_coupling_markers() -> None:
    """Reuse monorepo guardrail regex; runtime module must stay extension-agnostic."""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "test_forge_legacy_cleanup",
        FORGE_LEGACY_CLEANUP,
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    source = SANDBOX_FORCE_REPAIR.read_text(encoding="utf-8")
    coupling_offenders = [
        f"{match.start()}: {match.group(0)}"
        for match in module.CAPADONNA_DRILLER_MARKER_RE.finditer(source)
    ]
    vertical_offenders = [
        f"{match.start()}: {match.group(0)}"
        for match in module.REMOVED_DOMAIN_VERTICAL_MARKERS_RE.finditer(source)
    ]
    assert coupling_offenders == []
    assert vertical_offenders == []


def test_resolve_orchestration_fallback_reads_manifest_snippet(tmp_path: Path) -> None:
    snippet = tmp_path / "fallback.py"
    snippet.write_text("print('ok')\n", encoding="utf-8")

    class _Spec:
        tool_orchestration_config = {
            "sandbox_force_fallback_snippet": "fallback.py",
            "intents": {
                "x": {
                    "patterns": ["(?i)test"],
                    "force_first_tool": "read_sql",
                }
            },
        }
        worker_dir = tmp_path

    code = resolve_orchestration_fallback_code(_Spec())
    assert code == "print('ok')"


def test_extract_python_from_codeblock() -> None:
    body = "```python\nimport json\nprint(json.dumps({'ok': True}))\n```"
    assert extract_python_from_llm_text(body) is not None


def test_is_forced_sandbox_tool() -> None:
    assert is_forced_sandbox_tool("execute_sandbox_script")
    assert not is_forced_sandbox_tool("read_sql")
