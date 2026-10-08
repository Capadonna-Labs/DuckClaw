"""Operaciones de bóveda DuckDB (fresh dev)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from duckops.paths import repo_root


def fresh_dev_platform(*, dry_run: bool = False) -> int:
    """Bóveda default limpia: stack down, rm vault, migrate, stack deploy."""
    root = repo_root()
    os.chdir(root)
    env_path = root / ".env"
    if dry_run:
        print("DRY-RUN: duckops stack down")
        print("DRY-RUN: rm vault + duckclaw-migrate + duckops stack deploy")
        return 0
    if not env_path.is_file():
        print(f"error: falta .env en {root}", file=sys.stderr)
        return 1

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
