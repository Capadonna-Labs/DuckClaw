"""List runtime secrets for google calendar connector."""

from __future__ import annotations

import duckdb
import os

db = os.environ.get("DUCKCLAW_GATEWAY_DB_PATH") or "/root/Capadonna-Driller/db/duckclaw.duckdb"
con = duckdb.connect(db, read_only=True)
rows = con.execute(
    """
    SELECT key, actor_email, length(value_text), updated_at, substr(value_text, 1, 20)
    FROM main.admin_runtime_settings
    WHERE domain = 'mcp_connector'
      AND (key LIKE '%google_calendar%' OR key LIKE '%mcp_google_calendar%')
      AND active = true
    ORDER BY updated_at DESC
    """
).fetchall()
print(rows)
con.close()
