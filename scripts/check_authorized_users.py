#!/usr/bin/env python3
"""
Consulta ``main.authorized_users`` en una DuckDB (depuración del flujo /team).

Ejemplos::

  uv run python scripts/check_authorized_users.py --db db/private/USER/finanzdb1.duckdb
  uv run python scripts/check_authorized_users.py --tenant Finanzas

Si omites ``--db``, se usa ``get_gateway_db_path()`` (requiere ``DUCKCLAW_REPO_ROOT`` / env multiplex).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Lista filas en main.authorized_users")
    parser.add_argument(
        "--db",
        default="",
        help="Ruta al .duckdb (relativa al repo si aplica)",
    )
    parser.add_argument(
        "--tenant",
        default="",
        help="Filtrar por tenant_id (opcional; sin filtro lista todo)",
    )
    args = parser.parse_args()

    repo = Path(__file__).resolve().parent.parent
    if "DUCKCLAW_REPO_ROOT" not in os.environ:
        os.environ.setdefault("DUCKCLAW_REPO_ROOT", str(repo))

    db_path = (args.db or "").strip()
    if not db_path:
        sys.path.insert(0, str(repo / "packages" / "shared" / "src"))
        from duckclaw.gateway_db import get_gateway_db_path

        db_path = get_gateway_db_path()
    if not db_path:
        print("No hay ruta DuckDB: usa --db o define multiplex / DUCKDB_PATH", file=sys.stderr)
        return 1

    p = Path(db_path).expanduser()
    if not p.is_absolute():
        p = (repo / p).resolve()
    else:
        p = p.resolve()
    if not p.is_file():
        print(f"No existe el archivo: {p}", file=sys.stderr)
        return 1

    import duckdb

    tid = (args.tenant or "").strip()
    con = duckdb.connect(str(p), read_only=True)
    try:
        if tid:
            rows = con.execute(
                "SELECT tenant_id, user_id, username, role FROM main.authorized_users "
                "WHERE lower(tenant_id) = lower(?) ORDER BY user_id",
                [tid],
            ).fetchall()
        else:
            rows = con.execute(
                "SELECT tenant_id, user_id, username, role FROM main.authorized_users ORDER BY tenant_id, user_id"
            ).fetchall()
    except Exception as exc:
        print(f"Error SQL: {exc}", file=sys.stderr)
        return 1
    finally:
        con.close()

    out = [
        {"tenant_id": r[0], "user_id": r[1], "username": r[2], "role": r[3]}
        for r in rows
    ]
    print(json.dumps({"db": str(p), "count": len(out), "rows": out}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
