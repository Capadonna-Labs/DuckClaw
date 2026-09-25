"""google_trends_bridge: resolución del binario MCP en venvs uv (symlink)."""

from __future__ import annotations

from pathlib import Path


def test_candidate_venv_bin_dirs_prefer_sys_prefix(tmp_path: Path, monkeypatch) -> None:
    from duckclaw.forge.skills import google_trends_bridge as gt

    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    # Simula uv: el ejecutable real vive fuera del venv
    real_py = tmp_path / "uv-python" / "bin"
    real_py.mkdir(parents=True)
    (real_py / "python").write_text("#!/bin/sh\n")
    link = bin_dir / "python"
    link.symlink_to(real_py / "python")

    monkeypatch.setattr(gt.sys, "prefix", str(venv))
    monkeypatch.setattr(gt.sys, "executable", str(link))

    dirs = gt._candidate_venv_bin_dirs()
    assert dirs[0] == bin_dir
    # Incluso si alguien resolve() el symlink, el candidate incluye el venv
    assert bin_dir in dirs
    assert real_py not in dirs or dirs[0] == bin_dir


def test_default_stdio_uses_venv_script_not_uvx(tmp_path: Path, monkeypatch) -> None:
    from duckclaw.forge.skills import google_trends_bridge as gt

    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    real_py = tmp_path / "uv-python" / "bin"
    real_py.mkdir(parents=True)
    (real_py / "python").write_text("#!/bin/sh\n")
    link = bin_dir / "python"
    link.symlink_to(real_py / "python")
    script = bin_dir / "google-trends-mcp"
    script.write_text("#!/bin/sh\necho ok\n")
    script.chmod(0o755)

    monkeypatch.setattr(gt.sys, "prefix", str(venv))
    monkeypatch.setattr(gt.sys, "executable", str(link))
    monkeypatch.setattr(gt.shutil, "which", lambda name: "/usr/bin/uvx" if name == "uvx" else None)

    cmd, args = gt._default_stdio_command_and_args()
    assert cmd == str(script)
    assert args == []


def test_mcp_tool_to_structured_passes_keywords_schema(monkeypatch) -> None:
    """args_schema must expose keywords so invoke does not send {} to MCP."""
    from types import SimpleNamespace

    from duckclaw.forge.skills import google_trends_bridge as gt
    import duckclaw.forge.skills.mcp_stdio_util as stdio_util

    calls: list[dict] = []

    async def _fake_call(_params, name, arguments):
        calls.append({"name": name, "arguments": arguments})
        return "ok-trends"

    monkeypatch.setattr(stdio_util, "mcp_stdio_call_tool", _fake_call)

    spec = SimpleNamespace(
        name="interest_over_time",
        description="Interest over time",
        inputSchema={
            "type": "object",
            "properties": {
                "keywords": {"type": "array", "items": {"type": "string"}},
                "timeframe": {"type": "string", "default": "today 5-y"},
            },
            "required": ["keywords"],
        },
    )
    tool = gt._mcp_tool_to_structured(object(), spec, "interest_over_time")
    assert tool is not None
    assert "keywords" in (tool.args or {})
    out = tool.invoke({"keywords": ["XLU"]})
    assert out == "ok-trends"
    assert calls and calls[0]["arguments"].get("keywords") == ["XLU"]


def test_default_stdio_falls_back_to_uvx_when_missing(tmp_path: Path, monkeypatch) -> None:
    from duckclaw.forge.skills import google_trends_bridge as gt

    venv = tmp_path / "venv"
    bin_dir = venv / "bin"
    bin_dir.mkdir(parents=True)
    monkeypatch.setattr(gt.sys, "prefix", str(venv))
    monkeypatch.setattr(gt.sys, "executable", str(bin_dir / "python"))
    monkeypatch.setattr(
        gt.shutil,
        "which",
        lambda name: "/usr/bin/uvx" if name == "uvx" else None,
    )

    cmd, args = gt._default_stdio_command_and_args()
    assert cmd == "/usr/bin/uvx"
    assert args == ["google-trends-mcp"]
