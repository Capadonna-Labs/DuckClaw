"""Puerto canónico del API Gateway — fuente única: .env (+ overlay propuesto) → PM2 JSON."""

from __future__ import annotations

import os
import re
from pathlib import Path

from duckclaw.dotenv_immutable import merged_root_and_proposed_flat_env

# Solo si no hay DUCKCLAW_GATEWAY_PORT ni bloque PM2.
DEFAULT_GATEWAY_PORT = 8000

_PORT_RE = re.compile(r"--port\s+(\d+)")


def gateway_port_from_dotenv(flat: dict[str, str]) -> int | None:
    raw = (flat.get("DUCKCLAW_GATEWAY_PORT") or "").strip()
    if raw.isdigit():
        p = int(raw)
        if p > 0:
            return p
    return None


def gateway_port_from_pm2_json(repo_root: Path | str, app_name: str) -> int | None:
    cfg = Path(repo_root).resolve() / "config" / "api_gateways_pm2.json"
    if not cfg.is_file():
        return None
    try:
        import json

        raw = json.loads(cfg.read_text(encoding="utf-8"))
        apps = raw.get("apps") if isinstance(raw, dict) else None
        if not isinstance(apps, list):
            return None
        want = (app_name or "").strip()
        for app in apps:
            if not isinstance(app, dict):
                continue
            if (app.get("name") or "").strip() != want:
                continue
            p = int(app.get("port") or 0)
            if p > 0:
                return p
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return None
    return None


def _use_process_env(repo_root: Path) -> bool:
    """``os.environ`` solo cuando el repo pedido es el cwd (PM2/CLI en la raíz)."""
    try:
        return repo_root.resolve() == Path.cwd().resolve()
    except OSError:
        return False


def resolve_gateway_port(
    repo_root: Path | str | None = None,
    *,
    app_name: str = "DuckClaw-Gateway",
    fallback: int = DEFAULT_GATEWAY_PORT,
) -> int:
    """
    Orden (cwd = repo): ``os.environ`` → ``.env`` + propuesto → PM2 JSON → ``fallback``.
    Si ``repo_root`` es otro directorio (tests), solo archivos de ese repo.
    """
    root = Path(repo_root or Path.cwd()).resolve()
    if _use_process_env(root):
        raw = (os.environ.get("DUCKCLAW_GATEWAY_PORT") or "").strip()
        if raw.isdigit():
            p = int(raw)
            if p > 0:
                return p
    flat = merged_root_and_proposed_flat_env(root)
    from_env = gateway_port_from_dotenv(flat)
    if from_env is not None:
        return from_env
    pm2_name = (flat.get("DUCKCLAW_PM2_PROCESS_NAME") or app_name).strip() or app_name
    from_json = gateway_port_from_pm2_json(root, pm2_name)
    if from_json is not None:
        return from_json
    return int(fallback)


def gateway_base_url(
    repo_root: Path | str | None = None,
    *,
    host: str | None = None,
    app_name: str = "DuckClaw-Gateway",
) -> str:
    """URL local del gateway (sin barra final)."""
    root = Path(repo_root or Path.cwd()).resolve()
    if _use_process_env(root):
        explicit = (os.environ.get("DUCKCLAW_GATEWAY_URL") or "").strip().rstrip("/")
        if explicit:
            return explicit
    flat = merged_root_and_proposed_flat_env(root)
    explicit = (flat.get("DUCKCLAW_GATEWAY_URL") or "").strip().rstrip("/")
    if explicit:
        return explicit
    env_host = (
        (os.environ.get("DUCKCLAW_GATEWAY_HOST") or "").strip()
        if _use_process_env(root)
        else ""
    )
    bind_host = host or env_host or (flat.get("DUCKCLAW_GATEWAY_HOST") or "").strip() or "127.0.0.1"
    port = resolve_gateway_port(root, app_name=app_name)
    return f"http://{bind_host}:{port}"


def parse_uvicorn_port_from_pm2_args(args: object) -> int | None:
    """Extrae ``--port N`` de ``pm2 jlist`` → ``pm2_env.args``."""
    if isinstance(args, list):
        text = " ".join(str(x) for x in args)
    else:
        text = str(args or "")
    m = _PORT_RE.search(text)
    if m:
        return int(m.group(1))
    return None
