import os
import duckdb

from duckclaw.admin_mcp_connectors import _connector_has_auth, _row_to_connector
from duckclaw.admin_runtime_settings import resolve_runtime_setting

db = os.environ.get("DUCKCLAW_GATEWAY_DB_PATH", "/root/Capadonna-Driller/db/duckclaw.duckdb")
con = duckdb.connect(db)
tenant = "user-juanjoarevalo57-79c5ca60b91d4f3e"

row = con.execute(
    "SELECT * FROM main.admin_mcp_connectors WHERE connector_id = 'mcp_notion'"
).fetchone()
connector = _row_to_connector(row)
print("owner_email", connector.get("owner_email"))
print("tenant_id", connector.get("tenant_id"))
print("has_auth", _connector_has_auth(con, connector))

for actor in ("system", "juanjoarevalo57@gmail.com", ""):
    r = resolve_runtime_setting(
        con,
        tenant_id=tenant,
        actor_email=actor,
        domain="mcp_connector",
        key="mcp_notion.bearer",
    )
    val = str(r.get("value") or r.get("value_text") or "")
    print("resolve", repr(actor), "configured", r.get("configured"), "len", len(val))

con.close()
