"""PM2 provider — delega resolución de binario a ``duckclaw.ops.toolchain``."""

from __future__ import annotations

from typing import Any

from duckclaw.ops.toolchain import (
    ToolchainError,
    is_pm2_available,
    pm2_argv,
    resolve_pm2_executable,
    run_pm2,
    run_pm2_checked,
)

__all__ = [
    "ToolchainError",
    "deploy_pm2",
    "is_pm2_available",
    "pm2_argv",
    "resolve_pm2_executable",
    "run_pm2",
    "run_pm2_checked",
]


def deploy_pm2(
    name: str,
    command: str,
    python_path: str,
    cwd: str,
    **kwargs: Any,
) -> str:
    if not is_pm2_available():
        return "Error: pm2 is not installed or not in PATH. Install it (e.g. npm install -g pm2) and retry."

    try:
        r = run_pm2(
            "start",
            python_path,
            "--name",
            name,
            "--cwd",
            cwd,
            "--",
            *command.split(),
            cwd=cwd,
        )
        if r.returncode != 0:
            return f"Error: pm2 start failed. stderr: {r.stderr or r.stdout or 'unknown'}"
        return f"pm2: started '{name}'. Use 'pm2 logs {name}' and 'pm2 save' to persist."
    except ToolchainError as e:
        return f"Error running pm2: {e}"
