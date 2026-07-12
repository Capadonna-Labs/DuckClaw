"""Comando doctor: diagnóstico rápido del entorno local (solo lectura)."""

from __future__ import annotations

import os
import re
import shutil
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import typer

from duckops.admin_bootstrap import (
    admin_bootstrap_ready,
    is_admin_key_valid,
    sync_admin_console_user_from_env,
)

app = typer.Typer()


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent.parent.parent


def _load_dotenv(repo: Path) -> None:
    if os.environ.get("DUCKCLAW_DISABLE_DOTENV") == "1":
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(repo / ".env")
    except ImportError:
        pass


def _emit(label: str, ok: bool, detail: str) -> bool:
    mark = typer.style("OK", fg=typer.colors.GREEN) if ok else typer.style("—", fg=typer.colors.YELLOW)
    typer.echo(f"  {mark} {label} — {detail}")
    return ok


def _duckdb_paths_same(a: str, b: str) -> bool:
    try:
        return Path(a).resolve() == Path(b).resolve()
    except OSError:
        return (a or "").strip() == (b or "").strip()


def _playground_vault_user_id() -> str:
    for key in ("DUCKCLAW_OWNER_ID", "DUCKCLAW_ADMIN_CHAT_ID"):
        value = (os.environ.get(key) or "").strip()
        if value:
            return value
    return "default"


def _expected_playground_vault_path() -> str:
    from duckclaw.gateway_db import resolve_env_duckdb_path

    uid = re.sub(r"[^a-z0-9_-]", "_", _playground_vault_user_id().lower())[:128] or "default"
    return resolve_env_duckdb_path(f"db/private/{uid}/duckclaw.duckdb")


def _legacy_hub_path() -> str:
    from duckclaw.gateway_db import resolve_env_duckdb_path

    return resolve_env_duckdb_path("db/duckclaw.duckdb")


def _knowledge_source_count(db_path: str) -> int | None:
    path = Path(db_path)
    if not path.is_file():
        return None
    try:
        import duckdb

        con = duckdb.connect(str(path), read_only=True)
        try:
            row = con.execute("SELECT count(*) FROM main.admin_knowledge_sources").fetchone()
            return int(row[0]) if row else 0
        except Exception:
            return None
        finally:
            con.close()
    except Exception:
        return None


def _emit_split_check(label: str, ok: bool, detail: str, *, strict: bool, split: bool) -> bool:
    if ok:
        mark = typer.style("OK", fg=typer.colors.GREEN)
        typer.echo(f"  {mark} {label} — {detail}")
        return True
    if split and strict:
        mark = typer.style("FAIL", fg=typer.colors.RED)
        typer.echo(f"  {mark} {label} — {detail}")
        return False
    mark = typer.style("WARN", fg=typer.colors.YELLOW)
    typer.echo(f"  {mark} {label} — {detail}")
    return True


def _check_hub_vault_split(gateway_path: str, *, strict: bool) -> bool:
    vault_path = _expected_playground_vault_path()
    legacy_path = _legacy_hub_path()
    gateway = (gateway_path or "").strip()

    issues: list[str] = []
    is_split = False

    gateway_exists = bool(gateway) and Path(gateway).is_file()
    vault_exists = Path(vault_path).is_file()
    legacy_exists = Path(legacy_path).is_file()

    if gateway_exists and vault_exists and not _duckdb_paths_same(gateway, vault_path):
        is_split = True
        issues.append(f"gateway ({gateway}) ≠ bóveda playground ({vault_path})")

    if legacy_exists and vault_exists and not _duckdb_paths_same(legacy_path, vault_path):
        is_split = True
        issues.append(
            f"legacy db/duckclaw.duckdb y bóveda {vault_path} coexisten — split RAG/SQL"
        )

    seen: set[str] = set()
    counts: list[tuple[str, int]] = []
    for label, path in (("gateway", gateway), ("bóveda", vault_path), ("legacy", legacy_path)):
        if not path or not Path(path).is_file():
            continue
        try:
            resolved = str(Path(path).resolve())
        except OSError:
            resolved = path
        if resolved in seen:
            continue
        seen.add(resolved)
        row_count = _knowledge_source_count(path)
        if row_count is not None:
            counts.append((label, row_count))

    if len(counts) >= 2:
        values = [count for _, count in counts]
        if any(count > 0 for count in values) and any(count == 0 for count in values):
            is_split = True
            parts = [f"{label}={count}" for label, count in counts]
            issues.append(f"admin_knowledge_sources desalineado ({', '.join(parts)})")

    if not issues:
        detail = gateway or vault_path
        return _emit_split_check("Session DB unificada", True, detail, strict=strict, split=False)

    return _emit_split_check(
        "Session DB unificada",
        False,
        "; ".join(issues),
        strict=strict,
        split=is_split,
    )


def repair_legacy_session_db(repo: Path) -> tuple[bool, str]:
    """
    Archiva ``db/duckclaw.duckdb`` huérfano cuando la bóveda canónica ya es el hub activo.

    También reemplaza la clave obsoleta ``DUCKCLAW_GATEWAY_DB`` en ``.env`` por
    ``DUCKCLAW_GATEWAY_DB_PATH`` apuntando a la bóveda playground.
    """
    root = repo.resolve()
    _load_dotenv(root)
    from duckclaw.gateway_db import DEFAULT_SESSION_DB_RELPATH, get_gateway_db_path

    gateway = (get_gateway_db_path() or "").strip()
    vault_path = _expected_playground_vault_path()
    legacy_path = _legacy_hub_path()
    legacy_file = Path(legacy_path)
    vault_file = Path(vault_path)

    if not legacy_file.is_file():
        return True, "sin legacy db/duckclaw.duckdb"
    if not vault_file.is_file():
        return False, f"bóveda ausente: {vault_path}"
    if _duckdb_paths_same(legacy_path, vault_path):
        return True, "legacy y bóveda son el mismo archivo"
    if gateway and _duckdb_paths_same(gateway, legacy_path):
        return (
            False,
            "gateway aún apunta al legacy hub; fija DUCKCLAW_GATEWAY_DB_PATH "
            f"a {DEFAULT_SESSION_DB_RELPATH} y vuelve a ejecutar --repair-session-db",
        )

    backup_dir = root / ".duckops" / "migrate-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_path = backup_dir / f"duckclaw.legacy_hub_{stamp}.duckdb.bak"
    shutil.move(str(legacy_file), str(backup_path))

    env_path = root / ".env"
    if env_path.is_file():
        text = env_path.read_text(encoding="utf-8")
        lines = text.splitlines()
        out: list[str] = []
        saw_gateway_path = False
        legacy_keys = ("DUCKCLAW_GATEWAY_DB=", "DUCKCLAW_GATEWAY_DB_PATH=", "DUCKDB_PATH=")
        for line in lines:
            if any(line.startswith(key) for key in legacy_keys):
                if line.startswith("DUCKCLAW_GATEWAY_DB_PATH="):
                    out.append(f"DUCKCLAW_GATEWAY_DB_PATH={DEFAULT_SESSION_DB_RELPATH}")
                    saw_gateway_path = True
                elif line.startswith("DUCKCLAW_GATEWAY_DB="):
                    if not saw_gateway_path:
                        out.append(f"DUCKCLAW_GATEWAY_DB_PATH={DEFAULT_SESSION_DB_RELPATH}")
                        saw_gateway_path = True
                continue
            out.append(line)
        if not saw_gateway_path:
            out.append(f"DUCKCLAW_GATEWAY_DB_PATH={DEFAULT_SESSION_DB_RELPATH}")
        env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")

    return True, f"legacy archivado en {backup_path.name}; .env -> {DEFAULT_SESSION_DB_RELPATH}"


def _check_db_writer() -> tuple[bool, str]:
    """PM2 DuckClaw-DB-Writer, cola duckdb_write_queue y métrica processed."""
    from duckops.sovereign.stack_health import DB_WRITER_PM2_NAME, pm2_available, pm2_process_online

    detail_parts: list[str] = []
    writer_ok = False

    try:
        from duckclaw.spawn_profile import spawn_inline_writes_enabled

        if spawn_inline_writes_enabled():
            writer_ok = True
            detail_parts.append("escrituras inline (spawn)")
    except Exception:
        pass

    if pm2_available():
        if pm2_process_online(DB_WRITER_PM2_NAME):
            writer_ok = True
            detail_parts.append(f"PM2 {DB_WRITER_PM2_NAME} online")
        else:
            detail_parts.append(f"PM2 {DB_WRITER_PM2_NAME} offline")
    else:
        detail_parts.append("PM2 no en PATH")

    redis_url = (
        (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    )
    if redis_url:
        try:
            import redis as redis_sync

            client = redis_sync.Redis.from_url(
                redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
            )
            queue_depth = int(client.llen("duckdb_write_queue"))
            detail_parts.append(f"LLEN duckdb_write_queue={queue_depth}")
            if not writer_ok and queue_depth > 0:
                detail_parts.append("cola huérfana")
            processed = client.get("db_writer:metric:processed")
            if processed is not None:
                detail_parts.append(f"processed={processed}")
        except Exception as exc:
            detail_parts.append(f"Redis: {str(exc)[:100]}")

    if not detail_parts:
        detail_parts.append("sin señales de writer")

    return writer_ok, " · ".join(detail_parts)


@app.callback(invoke_without_command=True)
def cmd_doctor(
    ctx: typer.Context,
    repo: Path | None = typer.Option(None, "--repo", "-C", help="Raíz del monorepo."),
    smoke: bool = typer.Option(False, "--smoke", help="Además, probe GET /health si el gateway escucha."),
    bootstrap: bool = typer.Option(
        False,
        "--bootstrap",
        help="Instala prerequisitos faltantes (uv, Redis, Node, PM2) y ejecuta uv sync.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        "-y",
        help="Con --bootstrap: instalar sin pedir confirmación (brew/apt).",
    ),
    strict: bool = typer.Option(
        False,
        "--strict",
        help="Falla si hub y bóveda DuckDB están desalineados (split RAG/SQL).",
    ),
    repair_session_db: bool = typer.Option(
        False,
        "--repair-session-db",
        help="Archiva db/duckclaw.duckdb legacy si la bóveda canónica ya existe.",
    ),
) -> None:
    """Comprueba Redis, migraciones, admin key y puerto gateway."""
    if ctx.invoked_subcommand is not None:
        return

    root = (repo or _repo_root()).resolve()

    if bootstrap:
        from duckops.prerequisites import ensure_development_prerequisites, platform_label

        typer.secho(f"DuckClaw bootstrap ({platform_label()})", fg=typer.colors.CYAN)
        if not ensure_development_prerequisites(
            root,
            install=True,
            assume_yes=yes,
            sync_python=True,
            print_fn=typer.echo,
        ):
            raise typer.Exit(1)
        typer.echo("")

    _load_dotenv(root)
    typer.secho("DuckClaw doctor", fg=typer.colors.CYAN)

    if repair_session_db:
        ok, detail = repair_legacy_session_db(root)
        mark = typer.style("OK", fg=typer.colors.GREEN) if ok else typer.style("FAIL", fg=typer.colors.RED)
        typer.echo(f"  {mark} Reparar session DB — {detail}")
        if not ok:
            raise typer.Exit(1)
        typer.echo("")

    critical_ok = True

    try:
        from duckops.prerequisites import check_all

        for tool in check_all():
            is_critical = tool.name == "Redis"
            if not _emit(
                tool.name,
                tool.ok,
                f"{tool.version} · {tool.detail}" if tool.version else tool.detail,
            ):
                if is_critical:
                    critical_ok = False
    except Exception as exc:
        if not _emit("Prerequisitos", False, str(exc)[:160]):
            critical_ok = False

    db_path = ""
    try:
        from duckclaw.gateway_db import get_gateway_db_path
        from duckclaw.schema_migrations import verify_schema_integrity

        db_path = (get_gateway_db_path() or "").strip()
        if not db_path:
            _emit("Migraciones", True, "sin ruta hub (ejecuta duckops up o duckops configure)")
        else:
            ok_schema, msg_schema = verify_schema_integrity(db_path)
            if not _emit(
                "Migraciones",
                ok_schema,
                f"{db_path}" if ok_schema else f"{db_path}: {msg_schema}",
            ):
                critical_ok = False
    except Exception as exc:
        if not _emit("Migraciones", False, str(exc)[:160]):
            critical_ok = False

    if not _check_hub_vault_split(db_path, strict=strict):
        critical_ok = False

    if db_path:
        try:
            import duckdb

            from duckops.policy_health import check_framework_prompt_policies

            con = duckdb.connect(db_path, read_only=True)
            try:
                policy_health = check_framework_prompt_policies(con)
                policy_ok = policy_health.ok
                if not _emit(
                    "Policies framework",
                    policy_ok,
                    policy_health.summary(),
                ):
                    critical_ok = False
                elif policy_health.degraded:
                    _emit(
                        "Policies airbag",
                        True,
                        "capa 0 activa — ejecuta duckclaw-migrate para materializar en DB",
                    )
                from duckops.policy_health import check_catalog_worker_system_prompts

                catalog_prompt_health = check_catalog_worker_system_prompts(con)
                if not catalog_prompt_health.ok:
                    _emit(
                        "Catalog system_prompt",
                        True,
                        catalog_prompt_health.summary()
                        + " (workers en uso) — sync-catalog o editor de agente",
                    )
            except Exception as exc:
                if not _emit("Policies framework", False, str(exc)[:160]):
                    critical_ok = False
            finally:
                con.close()
        except Exception as exc:
            if not _emit("Policies framework", False, str(exc)[:160]):
                critical_ok = False

    admin_key = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    key_ok = is_admin_key_valid(admin_key)
    _emit(
        "Admin API key",
        key_ok,
        "configurada" if key_ok else "falta o placeholder (duckops up o duckops configure)",
    )

    try:
        dbw_ok, dbw_detail = _check_db_writer()
        _emit("DB-Writer", dbw_ok, dbw_detail)
    except Exception as exc:
        _emit("DB-Writer", False, str(exc)[:160])

    admin_email = (os.environ.get("DUCKCLAW_ADMIN_EMAIL") or "").strip()
    admin_pass = (os.environ.get("DUCKCLAW_ADMIN_PASSWORD") or "").strip()
    seed_ok = admin_bootstrap_ready(admin_email, admin_pass, admin_key)
    _emit(
        "Admin login seed",
        seed_ok,
        admin_email if seed_ok else "DUCKCLAW_ADMIN_EMAIL/PASSWORD incompletos o placeholder",
    )
    if seed_ok:
        sync_ok, sync_detail = sync_admin_console_user_from_env(root)
        _emit(
            "Admin login DuckDB",
            sync_ok,
            sync_detail if sync_ok else sync_detail,
        )

    from duckops.onboarding_health import (
        check_custom_agents_in_catalog,
        check_integration_bootstrap,
        check_llm_bootstrap,
    )

    if db_path:
        try:
            from duckclaw.gateway_db import ReadOnlyDbConnection

            db = ReadOnlyDbConnection(db_path)
            try:
                llm_health = check_llm_bootstrap(root, db=db)
                if not _emit("LLM bootstrap", llm_health.ok, llm_health.detail):
                    if strict:
                        critical_ok = False
                agents_health = check_custom_agents_in_catalog(db)
                _emit(
                    "Primer agente",
                    agents_health.ok,
                    agents_health.detail,
                )
                integrations = check_integration_bootstrap(db)
                _emit(
                    "Integraciones API keys",
                    integrations.ok,
                    integrations.summary() + " (opcional hasta activar skills)",
                )
            finally:
                db.close()
        except Exception as exc:
            _emit("Onboarding", False, str(exc)[:160])

    gateway_listening = False
    gateway_port = 8000
    try:
        from duckclaw.gateway_port import resolve_gateway_port
        from duckops.sovereign.validate import is_port_in_use

        gateway_port = int(resolve_gateway_port(root))
        gateway_listening = is_port_in_use("127.0.0.1", gateway_port)
        _emit(
            "Gateway puerto",
            True,
            f":{gateway_port} {'en escucha' if gateway_listening else 'libre (duckops serve --gateway --pm2)'}",
        )
    except Exception as exc:
        _emit("Gateway puerto", False, str(exc)[:160])

    if smoke:
        smoke_ok = False
        if gateway_listening:
            try:
                with urllib.request.urlopen(
                    f"http://127.0.0.1:{gateway_port}/health",
                    timeout=3.0,
                ) as response:
                    body = response.read(200).decode("utf-8", errors="replace")
                    smoke_ok = 200 <= int(response.status) < 300
                detail = f"HTTP {response.status}" + (f" · {body[:80]}" if body else "")
            except (OSError, urllib.error.URLError, TimeoutError) as exc:
                detail = str(exc)[:120]
        else:
            detail = "gateway no escucha — ejecuta: uv run duckops serve --gateway --pm2 --stack"
        if not _emit("Smoke /health", smoke_ok, detail):
            critical_ok = False

    if not critical_ok:
        typer.secho(
            "Corrige lo anterior. Prerequisitos: uv run duckops bootstrap --yes. "
            "Session DB split: uv run duckops doctor --repair-session-db",
            fg=typer.colors.YELLOW,
        )
        raise typer.Exit(1)

    typer.secho("Listo para init/serve o stack ya operativo.", fg=typer.colors.GREEN)
