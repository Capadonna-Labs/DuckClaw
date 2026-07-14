"""Inspect stored Google Calendar bearer: JWT aud vs opaque; try MCP call."""

from __future__ import annotations

import base64
import json
import os
import sys

import duckdb
import httpx

from duckclaw.admin_mcp_connectors import resolve_connector_bearer_token


def _b64url_json(part: str) -> dict:
    pad = "=" * (-len(part) % 4)
    return json.loads(base64.urlsafe_b64decode(part + pad))


def main() -> None:
    connector_id = (sys.argv[1] if len(sys.argv) > 1 else "mcp_google_calendar").strip()
    db_path = os.environ.get("DUCKCLAW_GATEWAY_DB_PATH") or "/root/Capadonna-Driller/db/duckclaw.duckdb"
    con = duckdb.connect(db_path, read_only=False)
    row = con.execute(
        "SELECT tenant_id, connector_id, preset_id, auth_kind, auth_secret_key "
        "FROM main.admin_mcp_connectors WHERE connector_id = ? AND active = true LIMIT 1",
        [connector_id],
    ).fetchone()
    if not row:
        raise SystemExit("not_found")
    connector = {
        "tenant_id": row[0],
        "connector_id": row[1],
        "preset_id": row[2],
        "auth_kind": row[3],
        "auth_secret_key": row[4],
    }
    token = resolve_connector_bearer_token(con, connector) or ""
    rows = con.execute(
        "SELECT actor_email, length(value_text), updated_at, left(value_text, 12) "
        "FROM main.admin_runtime_settings "
        "WHERE domain = 'mcp_connector' AND key = ? AND tenant_id = ? AND active = true "
        "ORDER BY updated_at DESC",
        [row[4], row[0]],
    ).fetchall()
    print("secret_rows", rows)
    con.close()
    print("token_len", len(token))
    print("token_dots", token.count("."))
    print("token_prefix", token[:24])
    if token.count(".") == 2:
        header, payload, _sig = token.split(".")
        print("jwt_header", _b64url_json(header))
        claims = _b64url_json(payload)
        safe = {k: claims.get(k) for k in ("aud", "azp", "scope", "scp", "exp", "iss", "sub")}
        print("jwt_claims", safe)
    info = httpx.get(
        "https://oauth2.googleapis.com/tokeninfo",
        params={"access_token": token},
        timeout=15.0,
    )
    print("tokeninfo", info.status_code, info.text[:500])
    if not token:
        return
    resp = httpx.post(
        "https://calendarmcp.googleapis.com/mcp/v1",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "list_calendars", "arguments": {}},
        },
        timeout=30.0,
    )
    print("list_calendars", resp.status_code, resp.text[:400])


if __name__ == "__main__":
    main()
