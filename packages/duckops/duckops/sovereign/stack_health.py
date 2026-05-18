"""Comprobaciones de salud del stack (Redis, gateway, DB-Writer) para Review y materialize."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from duckops.sovereign.draft import SovereignDraft
from duckops.sovereign.duckdb_health import DuckDbHealth, audit_duckdb, primary_duckdb_relpath
from duckops.sovereign.validate import is_port_in_use, redis_ping_url

DB_WRITER_PM2_NAME = "DuckClaw-DB-Writer"
DEFAULT_GATEWAY_PM2 = "DuckClaw-Gateway"


@dataclass(frozen=True)
class StackCheck:
    label: str
    ok: bool
    detail: str


@dataclass(frozen=True)
class StackHealthReport:
    checks: tuple[StackCheck, ...]

    @property
    def all_ok(self) -> bool:
        return all(c.ok for c in self.checks)


def _pm2_jlist() -> list[dict]:
    try:
        proc = subprocess.run(
            ["pm2", "jlist"],
            capture_output=True,
            text=True,
            timeout=12,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []
    if proc.returncode != 0 or not (proc.stdout or "").strip():
        return []
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def pm2_process_online(name: str) -> bool:
    target = (name or "").strip()
    if not target:
        return False
    for item in _pm2_jlist():
        if not isinstance(item, dict):
            continue
        if (item.get("name") or "").strip() != target:
            continue
        env = item.get("pm2_env") or {}
        if isinstance(env, dict) and env.get("status") == "online":
            return True
    return False


def pm2_available() -> bool:
    try:
        proc = subprocess.run(
            ["pm2", "-v"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return False


def db_writer_ecosystem_path(repo_root: Path) -> Path | None:
    portable = repo_root / "config" / "ecosystem.db-writer.config.cjs"
    if portable.is_file():
        return portable
    legacy = repo_root / "ecosystem.db-writer.config.cjs"
    if legacy.is_file():
        return legacy
    return None


def _interop_detail(
    *,
    redis_ok: bool,
    duck: DuckDbHealth,
    dbw_ok: bool,
    gw_ok: bool,
) -> tuple[bool, str]:
    """Redis → cola → DB-Writer → DuckDB (rutas y procesos alineados)."""
    parts: list[str] = []
    ok = True
    if redis_ok:
        parts.append("Redis→cola")
    else:
        parts.append("Redis pendiente")
        ok = False
    if duck.writable_parent and (duck.ok or not duck.exists):
        parts.append(f"DuckDB {duck.rel_path}")
    else:
        parts.append("DuckDB no lista")
        ok = False
    if dbw_ok:
        parts.append("DB-Writer consume cola")
    else:
        parts.append("DB-Writer pendiente")
        ok = False
    if gw_ok:
        parts.append("Gateway expone API")
    else:
        parts.append("Gateway pendiente")
        ok = False
    return ok, " · ".join(parts)


def audit_stack(repo_root: Path, draft: SovereignDraft) -> StackHealthReport:
    """Estado legible antes de confirmar Review (no modifica el sistema)."""
    checks: list[StackCheck] = []
    duck = audit_duckdb(repo_root, draft, quick=False)

    ok_redis, msg_redis = redis_ping_url(draft.redis_url)
    checks.append(
        StackCheck(
            label="Redis",
            ok=ok_redis,
            detail=msg_redis if ok_redis else f"{msg_redis} · {draft.redis_url}",
        )
    )

    if duck.exists:
        duck_detail = (
            f"{duck.rel_path} · {duck.size_human} · "
            f"{'conexión OK' if duck.connection_ok else 'sin conexión'}"
        )
        if duck.integrity_ok and duck.integrity_detail:
            duck_detail += f" · {duck.integrity_detail}"
        elif duck.integrity_detail:
            duck_detail += f" · {duck.integrity_detail}"
        if duck.table_count is not None:
            duck_detail += f" · {duck.table_count} tablas"
    else:
        duck_detail = f"{duck.rel_path} · se creará al aplicar"
        if not duck.writable_parent:
            duck_detail += " · sin permiso en db/"
    checks.append(
        StackCheck(
            label="DuckDB",
            ok=duck.ok,
            detail=duck_detail,
        )
    )

    host = "127.0.0.1"
    port = int(draft.gateway_port)
    port_open = is_port_in_use(host, port)
    gw_name = (draft.gateway_pm2_name or DEFAULT_GATEWAY_PM2).strip()
    gw_online = pm2_process_online(gw_name) if pm2_available() else False
    if gw_online:
        gw_detail = f"PM2 {gw_name} online"
        gw_ok = True
    elif port_open:
        gw_detail = f"puerto {port} en escucha (¿gateway manual?)"
        gw_ok = True
    else:
        gw_detail = f"puerto {port} libre · PM2 {gw_name} no online"
        gw_ok = False
    checks.append(StackCheck(label="Gateway", ok=gw_ok, detail=gw_detail))

    dbw_online = pm2_process_online(DB_WRITER_PM2_NAME) if pm2_available() else False
    eco = db_writer_ecosystem_path(repo_root)
    if dbw_online:
        dbw_detail = f"PM2 {DB_WRITER_PM2_NAME} online → {duck.rel_path}"
        dbw_ok = True
    elif eco:
        dbw_detail = f"{eco.relative_to(repo_root)} · pendiente · destino {duck.rel_path}"
        dbw_ok = False
    else:
        dbw_detail = f"se generará PM2 → {duck.rel_path}"
        dbw_ok = False
    checks.append(StackCheck(label="DB-Writer", ok=dbw_ok, detail=dbw_detail))

    interop_ok, interop_msg = _interop_detail(
        redis_ok=ok_redis,
        duck=duck,
        dbw_ok=dbw_ok,
        gw_ok=gw_ok,
    )
    checks.append(StackCheck(label="Interoperabilidad", ok=interop_ok, detail=interop_msg))

    return StackHealthReport(checks=tuple(checks))


def write_db_writer_ecosystem(repo_root: Path, draft: SovereignDraft) -> Path:
    """Genera config/ecosystem.db-writer.config.cjs portable (lee .env vía env_file)."""
    from duckclaw.ops.manager import render_db_writer_ecosystem_cjs  # noqa: PLC0415

    _ = draft
    config_dir = repo_root / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    path = config_dir / "ecosystem.db-writer.config.cjs"
    path.write_text(render_db_writer_ecosystem_cjs(), encoding="utf-8")
    return path


def ensure_db_writer_pm2(
    repo_root: Path,
    draft: SovereignDraft,
    console_print,
) -> int:
    """Arranca DuckClaw-DB-Writer en PM2 si no está online."""
    if draft.orchestration != "pm2":
        console_print("[dim]DB-Writer: omitido (orquestación Docker).[/]")
        return 0
    if not pm2_available():
        console_print(
            "[yellow]PM2 no está en PATH. Arranca DB-Writer: "
            "python services/db-writer/main.py[/]"
        )
        return 0
    if pm2_process_online(DB_WRITER_PM2_NAME):
        console_print(f"[green]DB-Writer[/] {DB_WRITER_PM2_NAME} ya en ejecución.")
        return 0
    eco = db_writer_ecosystem_path(repo_root)
    if eco is None:
        eco = write_db_writer_ecosystem(repo_root, draft)
        console_print(f"[dim]Generado[/] {eco.relative_to(repo_root)}")
    try:
        proc = subprocess.run(
            ["pm2", "start", str(eco)],
            cwd=str(repo_root),
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError) as e:
        console_print(f"[yellow]DB-Writer PM2:[/] {e}")
        return 1
    if proc.returncode == 0:
        console_print(f"[green]DB-Writer[/] iniciado ({DB_WRITER_PM2_NAME}).")
        return 0
    err = (proc.stderr or proc.stdout or "").strip()[:400]
    if "already" in err.lower() or pm2_process_online(DB_WRITER_PM2_NAME):
        console_print(f"[green]DB-Writer[/] {DB_WRITER_PM2_NAME} en ejecución.")
        return 0
    console_print(f"[yellow]DB-Writer PM2:[/] {err or proc.returncode}")
    return 1


def format_stack_health_rich(
    report: StackHealthReport,
    *,
    duck_block: str | None = None,
) -> str:
    lines: list[str] = ["[bold]Estado general[/]"]
    if duck_block:
        lines.extend(["", duck_block, ""])
    lines.append("[bold]Servicios[/]")
    for c in report.checks:
        mark = "[green]OK[/]" if c.ok else "[yellow]—[/]"
        lines.append(f"  {mark} [bold]{c.label}[/] — {c.detail}")
    lines.append("")
    lines.append(
        "[dim]Telegram (user id, token), Tailscale e integraciones: "
        "apps/duckclaw-admin tras aplicar.[/]"
    )
    return "\n".join(lines)
