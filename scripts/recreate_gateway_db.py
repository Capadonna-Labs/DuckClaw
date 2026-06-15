#!/usr/bin/env python3
"""Recrea la BD del Gateway desde cero con el esquema core genérico.

Usa la misma ruta que el Gateway (get_gateway_db_path(), respeta .env).
Uso: python3 scripts/recreate_gateway_db.py
"""
import sys
from datetime import datetime
from pathlib import Path

root = Path(__file__).resolve().parent.parent
if str(root) not in sys.path:
    sys.path.insert(0, str(root))
try:
    from dotenv import load_dotenv
    load_dotenv(root / ".env")
except ImportError:
    pass

def main():
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw import DuckClaw
    from duckclaw.bootstrap_core import bootstrap_core_schema
    from duckclaw.vaults import ensure_registry as ensure_vault_registry

    db_path = get_gateway_db_path()
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    backup_path = None
    if path.is_file():
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = path.parent / (path.name + f".bak.{ts}")
        path.rename(backup_path)
        backup_path = str(backup_path)
        print("Backup:", backup_path)

    db = DuckClaw(db_path)
    try:
        db.execute("SELECT 1")
        ensure_vault_registry()
        bootstrap_core_schema(db)
    finally:
        db.close()

    print("BD nueva:", db_path)
    if backup_path:
        print("Backup anterior:", backup_path)


if __name__ == "__main__":
    main()
