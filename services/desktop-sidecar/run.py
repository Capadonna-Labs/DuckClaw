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
import secrets
import sys
from pathlib import Path
from typing import Any


def desktop_env_file() -> Path:
    return desktop_data_dir() / "desktop.env"


def _parse_env_file(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        out[key.strip()] = val.strip().strip('"').strip("'")
    return out


def _write_env_file(path: Path, values: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"{k}={v}" for k, v in values.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_or_create_desktop_env() -> dict[str, str]:
    """Stable desktop credentials/API key under %%LOCALAPPDATA%%\\DuckClaw\\desktop.env."""
    path = desktop_env_file()
    existing = _parse_env_file(path)
    if existing.get("DUCKCLAW_ADMIN_API_KEY"):
        return existing

    admin_password = secrets.token_urlsafe(12)
    values = {
        "DUCKCLAW_ADMIN_API_KEY": secrets.token_urlsafe(32),
        "DUCKCLAW_ADMIN_EMAIL": "admin@duckclaw.local",
        "DUCKCLAW_ADMIN_PASSWORD": admin_password,
        "DUCKCLAW_DESKTOP_ADMIN_PASSWORD": admin_password,
    }
    merged = {**existing, **values}
    _write_env_file(path, merged)
    return merged


def apply_desktop_env_file() -> None:
    """Desktop bundle: ``desktop.env`` wins over inherited OS/process env."""
    force_keys = {
        "DUCKCLAW_ADMIN_API_KEY",
        "DUCKCLAW_ADMIN_EMAIL",
        "DUCKCLAW_ADMIN_PASSWORD",
        "DUCKCLAW_DESKTOP_ADMIN_PASSWORD",
        "OPENROUTER_API_KEY",
        "DUCKCLAW_LLM_PROVIDER",
        "DUCKCLAW_LLM_BASE_URL",
    }
    for key, val in load_or_create_desktop_env().items():
        if key in force_keys:
            os.environ[key] = val
        else:
            os.environ.setdefault(key, val)


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
    apply_desktop_env_file()
    os.environ.setdefault("DUCKCLAW_DEV_MODE", "1")
    os.environ.setdefault("DUCKCLAW_GATEWAY_HOST", "127.0.0.1")
    os.environ.setdefault("DUCKCLAW_DISABLE_DOTENV", "1")
    os.environ.pop("DUCKCLAW_SPAWN_USE_DB_WRITER", None)

    root = (repo_root or _repo_root()).resolve()
    os.environ["DUCKCLAW_REPO_ROOT"] = str(root)

    data = desktop_data_dir()
    db_path = data / "db" / "private" / "default" / "duckclaw.duckdb"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if not (os.environ.get("DUCKCLAW_GATEWAY_DB_PATH") or "").strip():
        os.environ["DUCKCLAW_GATEWAY_DB_PATH"] = str(db_path)
    return data


def bootstrap_desktop_db(db_path: Path) -> None:
    """Create hub DuckDB, migrations, and seed admin user when empty."""
    from duckclaw.schema_migrations import migrate_gateway_database

    migrate_gateway_database(str(db_path), seed_admin=True)


def _prepare_import_paths(repo_root: Path) -> Path:
    # No db-writer dir here (see module docstring: "one process, Spawn inline writes,
    # no db-writer") — it defines its own core.config.Settings, and both dirs share the
    # top-level `core` package name, so adding it shadows api-gateway's real core.config
    # (settings.VERSION) with db-writer's unrelated Settings class.
    gateway_dir = repo_root / "services" / "api-gateway"
    for p in (str(gateway_dir), str(repo_root)):
        if p not in sys.path:
            sys.path.insert(0, p)
    return gateway_dir


def _attach_desktop_file_logging(data_dir: Path) -> dict[str, Any]:
    """ponytail: uvicorn log_config → gateway.log."""
    log_path = data_dir / "gateway.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    return {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s %(levelname)s %(name)s %(message)s",
            },
        },
        "handlers": {
            "file": {
                "class": "logging.FileHandler",
                "filename": str(log_path),
                "formatter": "default",
                "encoding": "utf-8",
            },
        },
        "root": {"handlers": ["file"], "level": "INFO"},
        "loggers": {
            "uvicorn": {"handlers": ["file"], "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": ["file"], "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": ["file"], "level": "INFO", "propagate": False},
            "duckclaw.gateway": {"handlers": ["file"], "level": "INFO", "propagate": False},
        },
    }


def _port_is_open(host: str, port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, int(port))) == 0


def run_gateway(*, host: str | None = None, port: int | None = None) -> None:
    repo = _repo_root()
    data = apply_desktop_env(repo_root=repo)
    log_config = _attach_desktop_file_logging(data)
    db_path = Path(os.environ["DUCKCLAW_GATEWAY_DB_PATH"])
    bootstrap_desktop_db(db_path)
    _prepare_import_paths(repo)

    bind_host = (host or os.environ.get("DUCKCLAW_GATEWAY_HOST") or "127.0.0.1").strip()
    bind_port = port
    if bind_port is None:
        raw_port = (os.environ.get("DUCKCLAW_GATEWAY_PORT") or "").strip()
        if raw_port.isdigit() and int(raw_port) > 0:
            bind_port = int(raw_port)
        else:
            from duckclaw.gateway_port import resolve_gateway_port

            bind_port = resolve_gateway_port(repo)

    if getattr(sys, "frozen", False) and _port_is_open(bind_host, int(bind_port)):
        print(f"[desktop] Puerto {bind_port} ya en uso; omitiendo segundo sidecar.", flush=True)
        return

    import uvicorn

    from gateway_app import app

    if not getattr(sys, "frozen", False):
        os.chdir(repo / "services" / "api-gateway")

    uvicorn.run(
        app,
        host=bind_host,
        port=int(bind_port),
        log_level=(os.environ.get("DUCKCLAW_LOG_LEVEL") or "info").lower(),
        log_config=log_config,
    )


def main() -> None:
    run_gateway()


if __name__ == "__main__":
    main()
