"""Probe Calendar MCP OAuth start scopes."""

from __future__ import annotations

import json
import os
import subprocess


def main() -> None:
    key = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-X",
            "POST",
            "-H",
            f"X-Admin-Key: {key}",
            "-H",
            "X-Duckclaw-Actor: juanjoarevalo57@gmail.com",
            "-H",
            "Content-Type: application/json",
            "-d",
            "{}",
            "http://127.0.0.1:8000/api/v1/admin/mcp/connectors/mcp_google_calendar/oauth/start",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    data = json.loads(proc.stdout)
    url = str(data.get("authorization_url") or "")
    print("has_calendar_events", "calendar.events" in url)
    print("has_calendarlist_readonly", "calendar.calendarlist.readonly" in url)
    print("url_prefix", url[:160])


if __name__ == "__main__":
    main()
