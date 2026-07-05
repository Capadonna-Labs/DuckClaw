"""Deploy local DuckClaw stack (migrate + PM2 recycle + health)."""

from __future__ import annotations

import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from duckclaw.ops.pm2_recycle import (
    pm2_recycle_db_writer_shell,
    pm2_recycle_gateway_shell,
    pm2_recycle_heartbeat_shell,
    pm2_recycle_knowledge_indexer_shell,
)
from duckclaw.ops.toolchain import run_pm2

PrintFn = Callable[[str], None]

GATEWAY_NAME = "DuckClaw-Gateway"
DB_WRITER_NAME = "DuckClaw-DB-Writer"
INDEXER_NAME = "DuckClaw-Knowledge-Indexer"
HEARTBEAT_NAME = "DuckClaw-Heartbeat"

_PM2_WAIT_PREAMBLE = """
wait_pm2_stopped() {
  local name="$1"
  local timeout="${2:-15}"
  local deadline=$((SECONDS + timeout))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if ! pm2 describe "$name" >/dev/null 2>&1; then
      return 0
    fi
    if pm2 describe "$name" 2>/dev/null | grep -qE 'status.*(stopped|errored)'; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

wait_pm2_online() {
  local name="$1"
  local timeout="${2:-30}"
  local deadline=$((SECONDS + timeout))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if pm2 describe "$name" 2>/dev/null | grep -qE 'status.*online'; then
      return 0
    fi
    sleep 0.5
  done
  return 1
}

wait_gateway_health() {
  local url="${DUCKCLAW_GATEWAY_URL:-http://127.0.0.1:8000}/health"
  local timeout="${1:-45}"
  local deadline=$((SECONDS + timeout))
  while [ "$SECONDS" -lt "$deadline" ]; do
    if curl -sf "$url" >/dev/null 2>&1; then
      echo "GATEWAY_HEALTH_OK $url"
      return 0
    fi
    sleep 0.5
  done
  return 1
}
""".strip()


def stack_deploy_shell(*, repo_root: str | Path) -> str:
    """Bash script: stop → recycle (delete+start) → wait online → health."""
    root = Path(repo_root).resolve()
    return f"""set -euo pipefail
export PATH="/opt/homebrew/bin:/usr/local/bin:${{PATH:-/usr/bin:/bin}}"
cd "{root}"
{_PM2_WAIT_PREAMBLE}

echo "==> Deteniendo stack PM2…"
pm2 stop {GATEWAY_NAME} 2>/dev/null || true
pm2 stop {DB_WRITER_NAME} 2>/dev/null || true
pm2 stop {INDEXER_NAME} 2>/dev/null || true
pm2 stop {HEARTBEAT_NAME} 2>/dev/null || true
wait_pm2_stopped {GATEWAY_NAME} 15 || true
wait_pm2_stopped {DB_WRITER_NAME} 15 || true
wait_pm2_stopped {INDEXER_NAME} 15 || true
wait_pm2_stopped {HEARTBEAT_NAME} 15 || true

echo "==> Reciclando DuckClaw-DB-Writer…"
{pm2_recycle_db_writer_shell(repo_root=root).strip()}
wait_pm2_online {DB_WRITER_NAME} 30

echo "==> Reciclando DuckClaw-Knowledge-Indexer…"
{pm2_recycle_knowledge_indexer_shell(repo_root=root).strip()}
wait_pm2_online {INDEXER_NAME} 30

echo "==> Reciclando DuckClaw-Heartbeat…"
{pm2_recycle_heartbeat_shell(repo_root=root).strip()}
wait_pm2_online {HEARTBEAT_NAME} 30

echo "==> Reciclando DuckClaw-Gateway…"
{pm2_recycle_gateway_shell(repo_root=root).strip()}
wait_pm2_online {GATEWAY_NAME} 30

wait_gateway_health 45 || true
pm2 save 2>/dev/null || true
pm2 list
echo "STACK_DEPLOY_OK"
"""


def _gateway_health_ok(host: str = "127.0.0.1", port: int = 8000, timeout: float = 2.0) -> bool:
    try:
        with urllib.request.urlopen(f"http://{host}:{port}/health", timeout=timeout) as response:
            response.read()
            return 200 <= int(response.status) < 300
    except (OSError, urllib.error.URLError, TimeoutError):
        return False


def _wait_gateway_health(host: str, port: int, timeout_seconds: float) -> bool:
    deadline = time.monotonic() + max(timeout_seconds, 0.0)
    while time.monotonic() <= deadline:
        if _gateway_health_ok(host=host, port=port):
            return True
        time.sleep(0.5)
    return False


def _pm2_status(name: str) -> str:
    proc = run_pm2("jlist")
    if proc.returncode != 0:
        return "unknown"
    import json

    try:
        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return "unknown"
    for item in data if isinstance(data, list) else []:
        if str(item.get("name") or "") != name:
            continue
        env = item.get("pm2_env") if isinstance(item.get("pm2_env"), dict) else {}
        return str(env.get("status") or "unknown")
    return "missing"


def run_uv_sync(*, repo_root: Path, print_fn: PrintFn) -> bool:
    print_fn("==> uv sync …")
    proc = subprocess.run(
        ["uv", "sync", "--quiet"],
        cwd=str(repo_root),
        check=False,
    )
    if proc.returncode != 0:
        print_fn("ERROR: uv sync falló")
        return False
    return True


def run_migrate(*, repo_root: Path, print_fn: PrintFn) -> bool:
    print_fn("==> duckclaw-migrate …")
    proc = subprocess.run(
        ["uv", "run", "duckclaw-migrate"],
        cwd=str(repo_root),
        check=False,
    )
    if proc.returncode != 0:
        print_fn("ERROR: duckclaw-migrate falló")
        return False
    return True


def run_stack_deploy(
    *,
    repo_root: str | Path,
    print_fn: PrintFn = print,
    sync_deps: bool = True,
    migrate: bool = True,
    host: str = "127.0.0.1",
    port: int = 8000,
    wait_health: bool = True,
    health_timeout: float = 45.0,
) -> int:
    """uv sync (optional), migrate (optional), recycle PM2 stack with clean env, verify health."""
    root = Path(repo_root).resolve()
    if not (root / ".env").is_file():
        print_fn(f"ERROR: falta .env en {root}")
        return 1

    if sync_deps and not run_uv_sync(repo_root=root, print_fn=print_fn):
        return 1

    if migrate and not run_migrate(repo_root=root, print_fn=print_fn):
        return 1

    print_fn("==> Reciclando stack PM2 (DB-Writer → Knowledge-Indexer → Heartbeat → Gateway)…")
    shell = stack_deploy_shell(repo_root=root)
    proc = subprocess.run(["bash", "-lc", shell], cwd=str(root), check=False)
    if proc.returncode != 0:
        print_fn(f"ERROR: deploy shell exit {proc.returncode}")
        return proc.returncode

    if wait_health and not _wait_gateway_health(host, port, health_timeout):
        print_fn(f"WARN: Gateway sin /health OK en http://{host}:{port}/health")
        print_fn(f"  Gateway: {_pm2_status(GATEWAY_NAME)}")
        print_fn(f"  Indexer: {_pm2_status(INDEXER_NAME)}")
        print_fn(f"  Heartbeat: {_pm2_status(HEARTBEAT_NAME)}")
        print_fn(f"  DB-Writer: {_pm2_status(DB_WRITER_NAME)}")
        return 2

    print_fn("✓ Stack desplegado")
    print_fn(f"  Gateway: {_pm2_status(GATEWAY_NAME)} — http://{host}:{port}/health")
    print_fn(f"  Knowledge-Indexer: {_pm2_status(INDEXER_NAME)}")
    print_fn(f"  Heartbeat: {_pm2_status(HEARTBEAT_NAME)}")
    print_fn(f"  DB-Writer: {_pm2_status(DB_WRITER_NAME)}")
    print_fn("  Admin: cd apps/duckclaw-admin && pnpm dev")
    return 0
