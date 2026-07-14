import os
import duckdb

db = os.environ.get("DUCKCLAW_GATEWAY_DB_PATH", "/root/Capadonna-Driller/db/duckclaw.duckdb")
con = duckdb.connect(db)

for cid in ("mcp_notion", "mcp_remote_http_oauth"):
    r = con.execute(
        "SELECT connector_id, tenant_id, auth_kind, auth_secret_key, active, enabled "
        "FROM main.admin_mcp_connectors WHERE connector_id = ?",
        [cid],
    ).fetchone()
    print("row", r)
    if r:
        key = r[3] or f"{cid}.bearer"
        s = con.execute(
            "SELECT tenant_id, actor_email, domain, key, secret, length(value_text) "
            "FROM main.admin_runtime_settings WHERE domain = 'mcp_connector' AND key = ?",
            [key],
        ).fetchall()
        print("  settings", s)

try:
    t = con.execute(
        "SELECT command_type, status, error_text, created_at "
        "FROM main.admin_write_tasks WHERE command_type ILIKE '%mcp%' "
        "ORDER BY created_at DESC LIMIT 10"
    ).fetchall()
    print("tasks", t)
except Exception as e:
    print("tasks", e)

con.close()
