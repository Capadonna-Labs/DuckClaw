"""Apagar stack local DuckClaw: PM2, locks DuckDB y consola admin dev."""

from __future__ import annotations

import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Callable

PrintFn = Callable[[str], None]

# Núcleo que duckops up arranca (ecosystem.api + db-writer).
CORE_PM2_NAMES: tuple[str, ...] = (
    "DuckClaw-Gateway",
    "duckclaw-gateway",
    "DuckClaw-DB-Writer",
)

# Procesos que suelen abrir el hub/vault (RW o RO) y bloquean duckclaw-migrate.
MIGRATE_STOP_PM2_NAMES: tuple[str, ...] = (
    "DuckClaw-Gateway",
    "duckclaw-gateway",
    "DuckClaw-DB-Writer",
    "DuckClaw-Knowledge-Indexer",
    "DuckClaw-Heartbeat",
)

# Perfil spawn / servicios opcionales del monorepo.
OPTIONAL_PM2_PREFIXES: tuple[str, ...] = (
    "DuckClaw-",
    "duckclaw-",
    "Sensory-",
    "MLX-",
    "ComfyUI",
)


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent


def _default_print(msg: str) -> None:
    print(msg, flush=True)


def _run(argv: list[str]) -> subprocess.CompletedProcess[str]:
    from duckclaw.ops.toolchain import ToolchainError, run_pm2

    if argv and argv[0] == "pm2":
        try:
            return run_pm2(*argv[1:])
        except ToolchainError:
            return subprocess.CompletedProcess(argv, returncode=127, stdout="", stderr="pm2 not found")
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def _pm2_processes() -> list[dict]:
    proc = _run(["pm2", "jlist"])
    if proc.returncode != 0:
        return []
    try:
        import json

        data = json.loads(proc.stdout or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _pm2_names_matching(*, all_services: bool) -> list[str]:
    names: list[str] = []
    for item in _pm2_processes():
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        if name in CORE_PM2_NAMES:
            names.append(name)
            continue
        if all_services and any(name.startswith(p) or name == p for p in OPTIONAL_PM2_PREFIXES):
            names.append(name)
    # Preservar orden estable; core primero.
    ordered: list[str] = []
    for core in CORE_PM2_NAMES:
        if core in names and core not in ordered:
            ordered.append(core)
    for name in sorted(set(names) - set(ordered)):
        ordered.append(name)
    if not ordered and not all_services:
        return list(CORE_PM2_NAMES)
    return ordered


def stop_pm2_services(
    *,
    all_services: bool = False,
    print_fn: PrintFn = _default_print,
) -> list[str]:
    """pm2 stop de procesos DuckClaw registrados. Devuelve nombres parados."""
    names = _pm2_names_matching(all_services=all_services)
    stopped: list[str] = []
    for name in names:
        status = "missing"
        for item in _pm2_processes():
            if str(item.get("name") or "") != name:
                continue
            env = item.get("pm2_env") if isinstance(item.get("pm2_env"), dict) else {}
            status = str(env.get("status") or "unknown")
            break
        if status == "missing":
            continue
        if status == "stopped":
            print_fn(f"PM2 {name}: ya detenido")
            stopped.append(name)
            continue
        proc = _run(["pm2", "stop", name])
        if proc.returncode == 0:
            print_fn(f"PM2 stop {name}")
            stopped.append(name)
        else:
            detail = (proc.stderr or proc.stdout or "").strip()
            print_fn(f"PM2 stop {name} falló: {detail or proc.returncode}")
    if not stopped:
        print_fn("Ningún proceso PM2 DuckClaw activo (o PM2 no instalado).")
    return stopped


def duckdb_paths_to_unlock(repo: Path) -> list[Path]:
    from duckclaw.gateway_db import DEFAULT_SESSION_DB_RELPATH

    workspace_name = Path(DEFAULT_SESSION_DB_RELPATH).name
    paths: list[Path] = []
    try:
        from duckclaw.gateway_db import get_gateway_db_path

        raw = (get_gateway_db_path() or "").strip()
        if raw:
            path = Path(raw).expanduser()
            if path.is_file():
                paths.append(path)
    except Exception:
        pass
    private = repo / "db" / "private"
    if private.is_dir():
        for vault_db in sorted(private.glob(f"*/{workspace_name}")):
            if vault_db.is_file():
                paths.append(vault_db)
        legacy_name = "axis.duckdb"
        for vault_db in sorted(private.glob(f"*/{legacy_name}")):
            if vault_db.is_file():
                paths.append(vault_db)
    # Dedup preservando orden
    seen: set[str] = set()
    out: list[Path] = []
    for path in paths:
        key = str(path.resolve())
        if key in seen:
            continue
        seen.add(key)
        out.append(path)
    return out


def _pids_holding_path(path: Path) -> list[int]:
    proc = _run(["lsof", "-t", str(path)])
    if proc.returncode != 0:
        return []
    pids: list[int] = []
    for line in (proc.stdout or "").splitlines():
        text = line.strip()
        if text.isdigit():
            pids.append(int(text))
    return sorted(set(pids))


def kill_processes(pids: list[int], *, sig: int, print_fn: PrintFn, reason: str) -> int:
    killed = 0
    for pid in pids:
        try:
            os.kill(pid, sig)
            print_fn(f"kill -{sig} {pid} ({reason})")
            killed += 1
        except ProcessLookupError:
            pass
        except PermissionError:
            print_fn(f"Sin permiso para matar PID {pid}")
    return killed


def release_duckdb_locks(
    repo: Path,
    *,
    print_fn: PrintFn = _default_print,
) -> int:
    """Termina procesos que aún bloquean hub/vault DuckDB tras pm2 stop."""
    total = 0
    paths = duckdb_paths_to_unlock(repo)
    if not paths:
        print_fn("Sin rutas DuckDB conocidas para liberar locks.")
        return 0
    for path in paths:
        pids = _pids_holding_path(path)
        if not pids:
            continue
        print_fn(f"Lock en {path} → PIDs {pids}")
        total += kill_processes(pids, sig=signal.SIGTERM, print_fn=print_fn, reason=path.name)
    if total:
        time.sleep(0.6)
    for path in paths:
        survivors = _pids_holding_path(path)
        if survivors:
            print_fn(f"Forzando lock restante en {path} → {survivors}")
            total += kill_processes(survivors, sig=signal.SIGKILL, print_fn=print_fn, reason=f"{path.name} (force)")
    if total == 0:
        print_fn("Sin locks DuckDB activos.")
    return total


def remaining_duckdb_lock_holders(repo: Path) -> list[tuple[Path, list[int]]]:
    """Lista (path, pids) que aún tienen abierto un .duckdb del hub/vault."""
    out: list[tuple[Path, list[int]]] = []
    for path in duckdb_paths_to_unlock(repo):
        pids = _pids_holding_path(path)
        if pids:
            out.append((path, pids))
    return out


def stop_pm2_for_migrate(*, print_fn: PrintFn = _default_print) -> list[str]:
    """pm2 stop de Gateway/Writer/Indexer/Heartbeat; delete si siguen online."""
    stopped: list[str] = []
    for name in MIGRATE_STOP_PM2_NAMES:
        status = "missing"
        pid = 0
        for item in _pm2_processes():
            if str(item.get("name") or "") != name:
                continue
            env = item.get("pm2_env") if isinstance(item.get("pm2_env"), dict) else {}
            status = str(env.get("status") or "unknown")
            try:
                pid = int(item.get("pid") or 0)
            except (TypeError, ValueError):
                pid = 0
            break
        if status == "missing":
            continue
        if status == "stopped":
            print_fn(f"PM2 {name}: ya detenido")
            stopped.append(name)
            continue
        proc = _run(["pm2", "stop", name])
        if proc.returncode == 0:
            print_fn(f"PM2 stop {name}")
            stopped.append(name)
        else:
            detail = (proc.stderr or proc.stdout or "").strip()
            print_fn(f"PM2 stop {name} falló: {detail or proc.returncode}")
        # Esperar a que deje de estar online; si no, delete (libera el PID real).
        deadline = time.monotonic() + 12.0
        while time.monotonic() < deadline:
            cur = "missing"
            for item in _pm2_processes():
                if str(item.get("name") or "") != name:
                    continue
                env = item.get("pm2_env") if isinstance(item.get("pm2_env"), dict) else {}
                cur = str(env.get("status") or "unknown")
                break
            if cur in ("stopped", "errored", "missing"):
                break
            time.sleep(0.4)
        else:
            print_fn(f"PM2 {name} sigue activo tras stop → delete")
            _run(["pm2", "delete", name])
            if pid > 0:
                kill_processes([pid], sig=signal.SIGTERM, print_fn=print_fn, reason=f"{name} orphan")
    return stopped


def prepare_duckdb_for_migrate(
    repo: Path | None = None,
    *,
    print_fn: PrintFn = _default_print,
) -> int:
    """Detiene procesos PM2 que bloquean DuckDB y mata survivors vía lsof.

    Returns:
        0 si no quedan holders; 1 si aún hay lock (migrate no debe continuar).
    """
    root = (repo or repo_root()).resolve()
    print_fn("==> Preparar DuckDB para migrate (stop PM2 + liberar locks)…")
    stop_pm2_for_migrate(print_fn=print_fn)
    time.sleep(0.5)
    release_duckdb_locks(root, print_fn=print_fn)
    remaining = remaining_duckdb_lock_holders(root)
    if remaining:
        for path, pids in remaining:
            print_fn(f"ERROR: lock residual en {path} → PIDs {pids}")
        print_fn("Abortando migrate: libera esos PIDs manualmente o reintenta.")
        return 1
    print_fn("DUCKDB_UNLOCKED_OK")
    return 0


def kill_admin_dev_server(
    repo: Path,
    *,
    print_fn: PrintFn = _default_print,
) -> int:
    from duckops.admin_dev_server import resolve_admin_port

    port = resolve_admin_port(repo)
    proc = _run(["lsof", "-ti", f":{port}"])
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return 0
    pids = [int(x) for x in proc.stdout.split() if x.strip().isdigit()]
    if not pids:
        return 0
    print_fn(f"Consola admin :{port} → PIDs {pids}")
    return kill_processes(pids, sig=signal.SIGTERM, print_fn=print_fn, reason=f"admin:{port}")


def run_stack_down(
    repo: Path | None = None,
    *,
    all_services: bool = False,
    stop_pm2: bool = True,
    release_locks: bool = True,
    stop_admin: bool = True,
    print_fn: PrintFn = _default_print,
) -> int:
    """Apaga stack local. Código 0 si no hubo error fatal de PM2."""
    root = (repo or repo_root()).resolve()
    print_fn("🦆 DuckClaw down")
    print_fn(f"Repo: {root}\n")

    if stop_pm2:
        print_fn("[1/3] PM2 stop")
        stop_pm2_services(all_services=all_services, print_fn=print_fn)
        time.sleep(0.8)
    else:
        print_fn("[1/3] PM2 omitido")

    if release_locks:
        print_fn("\n[2/3] Liberar locks DuckDB")
        release_duckdb_locks(root, print_fn=print_fn)
    else:
        print_fn("\n[2/3] Locks omitidos")

    if stop_admin:
        print_fn("\n[3/3] Consola admin dev")
        kill_admin_dev_server(root, print_fn=print_fn)
    else:
        print_fn("\n[3/3] Admin dev omitido")

    print_fn("\n✓ Stack detenido. Ahora puedes: uv run duckclaw-migrate  o  uv run duckops up")
    return 0
