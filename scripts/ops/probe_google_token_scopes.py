"""Print OAuth token scopes for a Google MCP connector (VPS debug)."""

from __future__ import annotations

import os
import sys

import duckdb
import httpx

from duckclaw.admin_mcp_connectors import resolve_connector_bearer_token


def main() -> None:
    connector_id = (sys.argv[1] if len(sys.argv) > 1 else "mcp_google_workspace").strip()
    db_path = (
        os.environ.get("DUCKCLAW_GATEWAY_DB_PATH")
        or "/root/Capadonna-Driller/db/duckclaw.duckdb"
    )
    con = duckdb.connect(db_path, read_only=False)
    row = con.execute(
        "SELECT tenant_id, connector_id, preset_id, read_only, auth_kind, auth_secret_key "
        "FROM main.admin_mcp_connectors WHERE connector_id = ? AND active = true LIMIT 1",
        [connector_id],
    ).fetchone()
    if not row:
        print("connector_not_found", connector_id)
        raise SystemExit(1)
    tenant_id, cid, preset_id, read_only, auth_kind, secret_key = row
    connector = {
        "tenant_id": tenant_id,
        "connector_id": cid,
        "preset_id": preset_id,
        "read_only": read_only,
        "auth_kind": auth_kind,
        "auth_secret_key": secret_key,
    }
    token = resolve_connector_bearer_token(con, connector)
    print("connector_id", cid)
    print("read_only", read_only)
    print("preset_id", preset_id)
    print("token_present", bool(token))
    con.close()
    if not token:
        raise SystemExit(2)
    resp = httpx.get(
        "https://oauth2.googleapis.com/tokeninfo",
        params={"access_token": token},
        timeout=15.0,
    )
    print("tokeninfo_status", resp.status_code)
    data = resp.json()
    print("scope", data.get("scope", ""))
    print("expires_in", data.get("expires_in"))
    print("email", data.get("email", ""))


if __name__ == "__main__":
    main()
