"""Call Google Calendar MCP list_events with stored connector token."""

from __future__ import annotations

import json
import os
import sys

import duckdb
import httpx

from duckclaw.admin_mcp_connectors import resolve_connector_bearer_token


def _load_token(connector_id: str) -> tuple[dict, str]:
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
        raise SystemExit(f"connector_not_found:{connector_id}")
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
    con.close()
    return connector, token or ""


def _tokeninfo(token: str) -> dict:
    resp = httpx.get(
        "https://oauth2.googleapis.com/tokeninfo",
        params={"access_token": token},
        timeout=15.0,
    )
    return {"status": resp.status_code, "body": resp.json()}


def _mcp_list_tools(token: str) -> dict:
    resp = httpx.post(
        "https://calendarmcp.googleapis.com/mcp/v1",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
        timeout=30.0,
    )
    return {"status": resp.status_code, "body": resp.text}


def _mcp_call(token: str, tool: str, arguments: dict | None = None) -> dict:
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": tool, "arguments": arguments or {}},
    }
    resp = httpx.post(
        "https://calendarmcp.googleapis.com/mcp/v1",
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
        },
        json=payload,
        timeout=30.0,
    )
    return {
        "status": resp.status_code,
        "content_type": resp.headers.get("content-type", ""),
        "body": resp.text[:1200],
    }


def main() -> None:
    connector_id = (sys.argv[1] if len(sys.argv) > 1 else "mcp_google_calendar").strip()
    connector, token = _load_token(connector_id)
    print("connector", connector["connector_id"], "preset", connector["preset_id"])
    print("token_present", bool(token))
    if not token:
        raise SystemExit(2)
    info = _tokeninfo(token)
    print("tokeninfo", json.dumps(info["body"], ensure_ascii=False))
    listed = _mcp_list_tools(token)
    print("tools_list_status", listed["status"], listed["body"][:300])
    if listed["status"] == 200:
        tools = json.loads(listed["body"]).get("result", {}).get("tools", [])
        for tool in tools:
            if tool.get("name") == "list_events":
                print("list_events_schema", json.dumps(tool.get("inputSchema", {}), indent=2)[:1500])
                break
    for args in (
        {},
        {"calendarId": "primary"},
        {
            "calendarId": "primary",
            "startTime": "2026-07-13T00:00:00Z",
            "endTime": "2026-07-14T00:00:00Z",
        },
    ):
        result = _mcp_call(token, "list_events", args)
        print("list_events_args", args)
        print("list_events_status", result["status"])
        print("list_events_body", result["body"])
    for tool in ("list_calendars", "create_event"):
        result = _mcp_call(token, tool, {})
        print(f"{tool}_body", result["body"][:400])
    create = _mcp_call(
        token,
        "create_event",
        {
            "summary": "DuckClaw probe",
            "startTime": "2026-07-14T15:00:00Z",
            "endTime": "2026-07-14T16:00:00Z",
        },
    )
    print("create_event_full_body", create["body"][:500])
    cal = httpx.get(
        "https://www.googleapis.com/calendar/v3/users/me/calendarList",
        headers={"Authorization": f"Bearer {token}"},
        timeout=20.0,
    )
    print("calendar_api_status", cal.status_code, cal.text[:400])


if __name__ == "__main__":
    main()
