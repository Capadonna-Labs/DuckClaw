"""Operaciones de bóveda DuckDB (fresh dev, migración legacy axis)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from duckops.paths import repo_root


def migrate_legacy_axis_vault(*, dry_run: bool = False) -> int:
    """Renombra axis.duckdb → duckclaw.duckdb y limpia .env legacy."""
    root = repo_root()
    if dry_run:
        print("DRY-RUN: migrate legacy axis vault")
    renamed = 0
    for legacy in sorted(root.glob("db/**/axis.duckdb")):
        if not legacy.is_file():
            continue
        target = legacy.with_name("duckclaw.duckdb")
        if target.exists():
            print(f"SKIP (dest exists): {legacy}")
            continue
        if dry_run:
            print(f"DRY-RUN RENAME: {legacy} -> {target}")
        else:
            legacy.rename(target)
            print(f"RENAMED: {legacy} -> {target}")
        renamed += 1

    env_path = root / ".env"
    if env_path.is_file():
        text = env_path.read_text(encoding="utf-8")
        if "DUCKCLAW_AXIS_DB_PATH" in text:
            if dry_run:
                print("DRY-RUN: remove DUCKCLAW_AXIS_DB_PATH from .env")
            else:
                lines = [ln for ln in text.splitlines() if not ln.strip().startswith("DUCKCLAW_AXIS_DB_PATH=")]
                env_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
                print("Removed DUCKCLAW_AXIS_DB_PATH from .env")
        for key in ("DUCKCLAW_GATEWAY_DB_PATH", "DUCKCLAW_VAULT_DB_PATH", "DUCKDB_PATH"):
            marker = f"{key}=.*axis\\.duckdb"
            if dry_run:
                if f"axis.duckdb" in text and key in text:
                    print(f"DRY-RUN: update {key} axis.duckdb → duckclaw.duckdb")
            else:
                import re

                new_text, n = re.subn(
                    rf"({key}=.*?)axis\.duckdb",
                    r"\1duckclaw.duckdb",
                    text,
                )
                if n:
                    env_path.write_text(new_text, encoding="utf-8")
                    print(f"Updated {key} axis.duckdb → duckclaw.duckdb in .env")
                    text = new_text

    print(f"Done. Vaults renamed: {renamed}. Run: uv run duckops stack deploy")
    return 0


def fresh_dev_platform(*, dry_run: bool = False) -> int:
    """Bóveda default limpia: stack down, rm vault, migrate, stack deploy."""
    root = repo_root()
    os.chdir(root)
    env_path = root / ".env"
    if not env_path.is_file():
        print(f"error: falta .env en {root}", file=sys.stderr)
        return 1

    if dry_run:
        print("DRY-RUN: duckops stack down")
        print("DRY-RUN: rm vault + duckclaw-migrate + duckops stack deploy")
        return 0

    subprocess.run(["uv", "run", "duckops", "stack", "down"], cwd=root, check=False)

    from dotenv import load_dotenv

    load_dotenv(env_path)
    vault = (os.environ.get("DUCKCLAW_GATEWAY_DB_PATH") or "db/private/default/duckclaw.duckdb").strip()
    vault_path = (root / vault).resolve() if not Path(vault).is_absolute() else Path(vault)
    wal = Path(f"{vault_path}.wal")
    print(f"==> Eliminando bóveda anterior: {vault_path}")
    vault_path.unlink(missing_ok=True)
    wal.unlink(missing_ok=True)

    legacy_tenant = root / "db/private/7822026745"
    if legacy_tenant.is_dir():
        import shutil

        shutil.rmtree(legacy_tenant)
        print("    eliminado db/private/7822026745/")

    print("==> Migraciones (duckclaw-migrate)…")
    proc = subprocess.run(["uv", "run", "duckclaw-migrate"], cwd=root, check=False)
    if proc.returncode != 0:
        return proc.returncode

    print("==> Deploy stack PM2…")
    proc = subprocess.run(["uv", "run", "duckops", "stack", "deploy"], cwd=root, check=False)
    if proc.returncode != 0:
        return proc.returncode

    subprocess.run(["uv", "run", "duckclaw-healthcheck"], cwd=root, check=False)
    print("\n✓ Plataforma lista (usuario nuevo)")
    print(f"  Vault: {vault_path}")
    return 0
