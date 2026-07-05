"""Shell canónico para recrear procesos PM2 (delete + start)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from duckclaw.ops.pm2_env_filter import pm2_node_dev_env_filter_spec


def _process_spec(kind: str) -> dict[str, Any]:
    spec = pm2_node_dev_env_filter_spec()
    processes = spec.get("pm2_processes") or {}
    entry = processes.get(kind)
    if not entry:
        raise KeyError(f"pm2_processes.{kind} no definido en pm2_node_dev_env_filter_v1.json")
    return entry


def pm2_recycle_shell(
    kind: str,
    *,
    repo_root: str | Path = ".",
    success_token: str | None = None,
) -> str:
    """Recrea un proceso PM2 leyendo el ecosystem (no ``pm2 restart``)."""
    entry = _process_spec(kind)
    name = entry["name"]
    ecosystem = entry["ecosystem"]
    only_flag = entry.get("only_flag")
    root = Path(repo_root).resolve()
    start_cmd = f"pm2 start {ecosystem}"
    if only_flag:
        start_cmd = f"{start_cmd} {only_flag}"
    lines = [
        f'cd "{root}"',
        f"pm2 delete {name} 2>/dev/null || true",
        start_cmd,
    ]
    if success_token:
        lines.append(f'echo "{success_token}"')
    return "\n".join(lines) + "\n"


def pm2_recycle_gateway_shell(*, repo_root: str | Path = ".") -> str:
    return pm2_recycle_shell("gateway", repo_root=repo_root, success_token="PM2_RECYCLE_GATEWAY_OK")


def pm2_recycle_db_writer_shell(*, repo_root: str | Path = ".") -> str:
    return pm2_recycle_shell("db_writer", repo_root=repo_root, success_token="PM2_RECYCLE_DB_WRITER_OK")


def pm2_recycle_gateway_bash_lc(*, repo_root: str | Path = ".") -> str:
    entry = _process_spec("gateway")
    name = entry["name"]
    ecosystem = entry["ecosystem"]
    only_flag = entry.get("only_flag") or ""
    return (
        f"pm2 delete {name} 2>/dev/null || true; "
        f"pm2 start {ecosystem} {only_flag}".strip()
    )


def pm2_recycle_db_writer_bash_lc(*, repo_root: str | Path = ".") -> str:
    entry = _process_spec("db_writer")
    name = entry["name"]
    ecosystem = entry["ecosystem"]
    return f"pm2 delete {name} 2>/dev/null || true; pm2 start {ecosystem}"
