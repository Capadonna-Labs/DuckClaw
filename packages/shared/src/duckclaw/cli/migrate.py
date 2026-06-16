"""Apply versioned DuckDB migrations for the gateway hub."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def _repo_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here, *here.parents]:
        if (parent / "packages" / "shared").is_dir():
            return parent
    return Path.cwd()


def _load_dotenv() -> None:
    if os.environ.get("DUCKCLAW_DISABLE_DOTENV") == "1":
        return
    try:
        from dotenv import load_dotenv

        load_dotenv(_repo_root() / ".env")
    except ImportError:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply DuckClaw gateway schema migrations")
    parser.add_argument(
        "--db-path",
        default="",
        help="Gateway DuckDB path (default: DUCKCLAW_GATEWAY_DB_PATH / DUCKDB_PATH)",
    )
    parser.add_argument(
        "--no-seed-admin",
        action="store_true",
        help="Skip default admin user seeding during bootstrap",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify schema integrity; do not apply migrations",
    )
    args = parser.parse_args(argv)

    _load_dotenv()
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.schema_migrations import migrate_gateway_database, verify_schema_integrity

    db_path = (args.db_path or get_gateway_db_path() or "").strip()
    if not db_path:
        print("No gateway DB path resolved. Set DUCKCLAW_GATEWAY_DB_PATH or DUCKDB_PATH.", file=sys.stderr)
        return 1

    if args.verify_only:
        ok, message = verify_schema_integrity(db_path)
        if ok:
            print(f"OK: {db_path}")
            return 0
        print(message, file=sys.stderr)
        return 1

    try:
        migrate_gateway_database(db_path, seed_admin=not args.no_seed_admin)
    except Exception as exc:
        print(f"migrate failed: {exc}", file=sys.stderr)
        return 1

    ok, message = verify_schema_integrity(db_path)
    if not ok:
        print(message, file=sys.stderr)
        return 1
    print(f"Migrated OK: {db_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
