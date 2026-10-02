"""Sandbox auto-correct must never run the AIMessage repr as code."""

from __future__ import annotations

from langchain_core.messages import AIMessage

from duckclaw.graphs.sandbox import _corrected_code_from_llm


def test_empty_content_is_not_turned_into_repr_code() -> None:
    # Reasoning model spent the whole budget: content '' + completion_tokens == max.
    msg = AIMessage(content="", response_metadata={"token_usage": {"completion_tokens": 2048}})
    assert _corrected_code_from_llm(msg) == ""


def test_truncated_reply_is_discarded() -> None:
    msg = AIMessage(content="import numpy as np\nfor i in", response_metadata={"finish_reason": "length"})
    assert _corrected_code_from_llm(msg) == ""


def test_fenced_code_and_block_lists_are_extracted() -> None:
    assert _corrected_code_from_llm(AIMessage(content="```python\nprint(1)\n```")) == "print(1)"
    blocks = AIMessage(content=[{"type": "text", "text": "print(2)"}])
    assert _corrected_code_from_llm(blocks) == "print(2)"
    assert _corrected_code_from_llm("print(3)") == "print(3)"


def test_sandbox_timeout_ceiling_is_configurable(monkeypatch) -> None:
    """Long-running agents: the per-run ceiling is no longer a fixed 600 s."""
    from duckclaw.forge.schema import SecurityPolicy
    from duckclaw.graphs import sandbox as sb

    monkeypatch.delenv("DUCKCLAW_SANDBOX_MAX_TIMEOUT_SEC", raising=False)
    monkeypatch.setenv("DUCKCLAW_SANDBOX_MIN_TIMEOUT_SEC", "1800")
    pol = SecurityPolicy()  # zero-trust default: 30 s
    assert sb._sandbox_effective_timeout_sec(pol) == 1800  # env floor, above the old 600 cap
    monkeypatch.setenv("DUCKCLAW_SANDBOX_MAX_TIMEOUT_SEC", "900")
    assert sb._sandbox_effective_timeout_sec(pol) == 900  # still bounded by the ceiling
    assert SecurityPolicy(max_execution_time_seconds=7200).max_execution_time_seconds == 7200


def test_session_output_dir_is_writable_by_non_root_sandbox_user(tmp_path, monkeypatch) -> None:
    """The container runs as uid 1000; /workspace/output must be writable or charts never reach the chat."""
    import os
    import stat
    import sys

    import pytest

    if sys.platform.startswith("win"):
        pytest.skip("POSIX permissions")
    from duckclaw.graphs import sandbox as sb

    monkeypatch.setattr(sb, "_TMP_BASE", tmp_path)
    mgr = sb.StrixSandboxManager.__new__(sb.StrixSandboxManager)
    _data, out = mgr._session_dirs("s1")
    assert stat.S_IMODE(os.stat(out).st_mode) & 0o002  # world-writable


def test_only_files_written_by_this_run_are_artifacts(tmp_path, monkeypatch) -> None:
    """Session output persists across runs; an old chart must not resurface on a later run."""
    import os

    from duckclaw.graphs import sandbox as sb

    monkeypatch.chdir(tmp_path)
    out = tmp_path / "out"
    out.mkdir()
    old = out / "equity_curve.png"
    old.write_bytes(b"old")
    rewritten = out / "report.csv"
    rewritten.write_text("v1")
    before = sb._output_snapshot(out)
    (out / "new.png").write_bytes(b"new")
    rewritten.write_text("v2-longer")
    os.utime(rewritten, ns=(before["report.csv"][0] + 10**9,) * 2)

    mgr = sb.StrixSandboxManager.__new__(sb.StrixSandboxManager)
    artifacts, _rid, _ids = mgr._collect_artifacts(out, output_before=before)
    assert sorted(os.path.basename(a) for a in artifacts) == ["new.png", "report.csv"]
