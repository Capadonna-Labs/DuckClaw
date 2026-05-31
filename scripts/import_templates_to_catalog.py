#!/usr/bin/env python3
"""Import filesystem templates into the DB-first worker catalog."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Iterable


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _ensure_shared_src() -> None:
    shared_src = _repo_root() / "packages" / "shared" / "src"
    if str(shared_src) not in sys.path:
        sys.path.insert(0, str(shared_src))


def default_templates_root() -> Path:
    return _repo_root() / "packages" / "agents" / "src" / "duckclaw" / "forge" / "templates"


def apply_import(
    *,
    db_path: str,
    owner_email: str,
    templates_root: str,
    include_prefixes: Iterable[str] = (),
    include_template_ids: Iterable[str] = (),
) -> dict[str, list[Any]]:
    _ensure_shared_src()

    import duckdb
    from duckclaw.admin_template_import import import_templates_to_catalog

    con = duckdb.connect(db_path, read_only=False)
    try:
        return import_templates_to_catalog(
            con,
            owner_email=owner_email,
            templates_root=templates_root,
            include_prefixes=tuple(include_prefixes),
            include_template_ids=tuple(include_template_ids),
        )
    finally:
        con.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Import templates into admin worker catalog")
    parser.add_argument("--db", help="Path to gateway DuckDB (default: get_gateway_db_path())")
    parser.add_argument("--owner-email", required=True, help="Admin/user email that will own imported workers")
    parser.add_argument("--templates-root", default=str(default_templates_root()))
    parser.add_argument(
        "--include-prefix",
        action="append",
        dest="include_prefixes",
        default=[],
        help="Template prefix to include. Repeatable. Empty means all non-default templates.",
    )
    parser.add_argument(
        "--include-template",
        action="append",
        dest="include_template_ids",
        default=[],
        help="Exact template directory name to include. Repeatable.",
    )
    args = parser.parse_args()

    _ensure_shared_src()
    db_path = (args.db or "").strip()
    if not db_path:
        from duckclaw.gateway_db import get_gateway_db_path

        db_path = (get_gateway_db_path() or "").strip()
    if not db_path:
        print("No DuckDB path", file=sys.stderr)
        return 1

    result = apply_import(
        db_path=db_path,
        owner_email=args.owner_email,
        templates_root=args.templates_root,
        include_prefixes=tuple(args.include_prefixes or ()),
        include_template_ids=tuple(args.include_template_ids or ()),
    )
    print(
        "Imported {imported} template(s); skipped existing {skipped}".format(
            imported=len(result.get("imported") or []),
            skipped=len(result.get("skipped_existing") or []),
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
