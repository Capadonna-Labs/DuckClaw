"""run_browser_sandbox debe serializar stdout_tail/stderr_tail para el LLM."""

from __future__ import annotations

import json
from unittest.mock import patch

from duckclaw.graphs.sandbox import ExecutionResult, browser_sandbox_tool_factory


def test_browser_sandbox_tool_includes_stdout_and_stderr_tails() -> None:
    payload = '{"extracted": true, "source": "mql5"}\n'
    fake = ExecutionResult(
        exit_code=0,
        stdout=payload,
        stderr="selector article: timeout\n",
        timed_out=False,
        artifacts=[],
        attempts=1,
    )
    tool = browser_sandbox_tool_factory(None, None)
    with patch("duckclaw.graphs.sandbox.run_in_sandbox", return_value=fake):
        raw = tool.invoke({"code": "print('x')"})

    assert isinstance(raw, str)
    data = json.loads(raw)
    assert "stdout_tail" in data
    assert "extracted" in data["stdout_tail"]
    assert "stderr_tail" in data
    assert "selector article" in data["stderr_tail"]
