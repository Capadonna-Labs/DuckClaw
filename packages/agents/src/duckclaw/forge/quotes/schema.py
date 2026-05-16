"""
Schema: tabla quotes y directorio de PDFs.

Spec: specs/Motor_Cotizacion_Omnicanal_QuoteEngine.md
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

QUOTES_DIR = Path(os.environ.get("DUCKCLAW_QUOTES_DIR", "/tmp/quotes"))


def _json_sql_type(db: Any) -> str:
    """JSON nativo si la extensión carga; si no, VARCHAR (compatible con binding C++ sin ext)."""
    home = (os.environ.get("DUCKCLAW_TEST_DUCKDB_HOME") or "").strip()
    if home:
        esc = home.replace("'", "''")
        try:
            db.execute(f"SET home_directory='{esc}'")
        except Exception:
            pass
    for stmt in ("INSTALL json;", "LOAD json;"):
        try:
            db.execute(stmt)
        except Exception:
            pass
    try:
        db.execute("SELECT '{}'::JSON")
        return "JSON"
    except Exception:
        return "VARCHAR"


def ensure_quotes_schema(db: Any, schema: str = "main") -> None:
    """Crea tabla quotes si no existe."""
    json_t = _json_sql_type(db)
    safe = "".join(c if c.isalnum() or c == "_" else "_" for c in schema.strip()) or "main"
    db.execute(f"""
        CREATE TABLE IF NOT EXISTS {safe}.quotes (
            quote_id VARCHAR PRIMARY KEY,
            user_id VARCHAR,
            customer_name VARCHAR,
            items {json_t},
            subtotal DECIMAL,
            discount DECIMAL DEFAULT 0,
            tax DECIMAL DEFAULT 0,
            total_amount DECIMAL,
            currency VARCHAR DEFAULT 'COP',
            status VARCHAR DEFAULT 'generated',
            pdf_path VARCHAR,
            download_token VARCHAR,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    QUOTES_DIR.mkdir(parents=True, exist_ok=True)
