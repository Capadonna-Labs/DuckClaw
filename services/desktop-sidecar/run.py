"""
Desktop composition root — one process, Spawn inline writes, no db-writer.

Sets LITE_MODE / Spawn env, user data dir under %%LOCALAPPDATA%%\\DuckClaw,
bootstraps DuckDB, then runs the API gateway on loopback.

Spec: docs/specs/features/platform/DESKTOP_LITE_SIDECAR.md
"""

from __future__ import annotations

import multiprocessing

# PyInstaller on Windows: child processes re-exec the exe; freeze_support prevents
# each child from running main() again (infinite console windows).
multiprocessing.freeze_support()

import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parents[2]


def desktop_data_dir() -> Path:
    local = (os.environ.get("LOCALAPPDATA") or "").strip()
    if not local:
        local = str(Path.home() / "AppData" / "Local")
    return Path(local) / "DuckClaw"


def apply_desktop_env(*, repo_root: Path | None = None) -> Path:
    """Configure lite/spawn profile and desktop paths. Returns data directory."""
    os.environ.setdefault("LITE_MODE", "1")
    from duckclaw.spawn_profile import apply_lite_mode_env

    apply_lite_mode_env()
    os.environ.setdefault("DUCKCLAW_DEV_MODE", "1")
    os.environ.setdefault("DUCKCLAW_GATEWAY_HOST", "127.0.0.1")
    os.environ.setdefault("DUCKCLAW_DISABLE_DOTENV", "1")
    os.environ.pop("DUCKCLAW_SPAWN_USE_DB_WRITER", None)

    root = (repo_root or _repo_root()).resolve()
    os.environ["DUCKCLAW_REPO_ROOT"] = str(root)

    data = desktop_data_dir()
    db_path = data / "db" / "private" / "default" / "duckclaw.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    os.environ["DUCKCLAW_GATEWAY_DB_PATH"] = str(db_path)
    return data


def bootstrap_desktop_db(db_path: Path) -> None:
    """Create hub DuckDB and apply pending schema migrations."""
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations

    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(db_path), read_only=False)
    try:
        run_pending_migrations(con)
    finally:
        con.close()


def _prepare_import_paths(repo_root: Path) -> Path:
    gateway_dir = repo_root / "services" / "api-gateway"
    writer_dir = repo_root / "services" / "db-writer"
    for p in (str(gateway_dir), str(writer_dir), str(repo_root)):
        if p not in sys.path:
            sys.path.insert(0, p)
    return gateway_dir


def run_gateway(*, host: str | None = None, port: int | None = None) -> None:
    repo = _repo_root()
    apply_desktop_env(repo_root=repo)
    db_path = Path(os.environ["DUCKCLAW_GATEWAY_DB_PATH"])
    bootstrap_desktop_db(db_path)
    _prepare_import_paths(repo)

    bind_host = (host or os.environ.get("DUCKCLAW_GATEWAY_HOST") or "127.0.0.1").strip()
    bind_port = port
    if bind_port is None:
        from duckclaw.gateway_port import resolve_gateway_port

        bind_port = resolve_gateway_port(repo)

    import uvicorn

    from gateway_app import app

    if not getattr(sys, "frozen", False):
        os.chdir(repo / "services" / "api-gateway")

    uvicorn.run(
        app,
        host=bind_host,
        port=int(bind_port),
        log_level=(os.environ.get("DUCKCLAW_LOG_LEVEL") or "info").lower(),
    )


def main() -> None:
    run_gateway()


if __name__ == "__main__":
    main()
