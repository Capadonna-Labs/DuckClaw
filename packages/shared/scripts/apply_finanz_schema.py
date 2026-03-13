#!/usr/bin/env python3
"""Aplica las tablas faltantes de Finanz (cuentas, presupuestos, deudas) a una .duckdb."""
import sys
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
    if len(sys.argv) > 1:
        db_path = sys.argv[1]
    else:
        try:
            from duckclaw.gateway_db import get_gateway_db_path
            db_path = get_gateway_db_path()
        except Exception:
            db_path = str(root / "db" / "gateway.duckdb")
    from duckclaw import DuckClaw
    db = DuckClaw(db_path)
    db.execute("CREATE SCHEMA IF NOT EXISTS finance_worker")
    db.execute("""
        CREATE TABLE IF NOT EXISTS finance_worker.cuentas (
            id INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL UNIQUE,
            balance REAL NOT NULL DEFAULT 0,
            currency VARCHAR DEFAULT 'COP',
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS finance_worker.presupuestos (
            id INTEGER PRIMARY KEY,
            name VARCHAR NOT NULL,
            amount_limit REAL NOT NULL,
            period VARCHAR NOT NULL DEFAULT 'monthly',
            category_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    db.execute("""
        CREATE TABLE IF NOT EXISTS finance_worker.deudas (
            id INTEGER PRIMARY KEY,
            descripcion VARCHAR,
            acreedor VARCHAR NOT NULL,
            monto REAL NOT NULL,
            moneda VARCHAR DEFAULT 'COP',
            fecha_inicio DATE,
            fecha_vencimiento DATE,
            tasa_interes REAL,
            estado VARCHAR DEFAULT 'pendiente',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    print("OK: cuentas, presupuestos, deudas creadas o ya existían en", db_path)

if __name__ == "__main__":
    main()
