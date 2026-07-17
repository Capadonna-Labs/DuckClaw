"""Google Calendar via REST when official Calendar MCP tools/call is blocked.

Runtime evidence: same OAuth bearer gets Calendar REST 200 but calendarmcp
tools/call returns \"The caller does not have permission\" (Developer Preview / MCP
service layer). Keep MCP tools/list; execute tools over Calendar API v3.
"""

from __future__ import annotations

import json
from typing import Any

import httpx

_CAL_BASE = "https://www.googleapis.com/calendar/v3"


def _bearer(headers: dict[str, str] | None) -> str:
    raw = str((headers or {}).get("Authorization") or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


def _iso_event_time(value: str) -> dict[str, str]:
    text = (value or "").strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return {"date": text}
    return {"dateTime": text}


async def call_google_calendar_rest(
    tool_name: str,
    arguments: dict[str, Any] | None,
    *,
    headers: dict[str, str] | None = None,
) -> str:
    token = _bearer(headers)
    if not token:
        return "Error Calendar REST: missing bearer token"
    args = dict(arguments or {})
    auth = {"Authorization": f"Bearer {token}"}
    name = (tool_name or "").strip()

    async with httpx.AsyncClient(timeout=30.0, headers=auth) as client:
        if name == "list_calendars":
            resp = await client.get(f"{_CAL_BASE}/users/me/calendarList")
        elif name == "list_events":
            from urllib.parse import quote

            calendar_id = str(args.get("calendarId") or "primary").strip() or "primary"
            params: dict[str, str] = {"singleEvents": "true", "orderBy": "startTime"}
            if args.get("startTime"):
                params["timeMin"] = str(args["startTime"])
            if args.get("endTime"):
                params["timeMax"] = str(args["endTime"])
            if args.get("maxResults"):
                params["maxResults"] = str(args["maxResults"])
            resp = await client.get(
                f"{_CAL_BASE}/calendars/{quote(calendar_id, safe='')}/events",
                params=params,
            )
        elif name == "get_event":
            from urllib.parse import quote

            calendar_id = str(args.get("calendarId") or "primary").strip() or "primary"
            event_id = str(args.get("eventId") or args.get("id") or "").strip()
            if not event_id:
                return "Error Calendar REST: eventId required"
            resp = await client.get(
                f"{_CAL_BASE}/calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}"
            )
        elif name == "create_event":
            from urllib.parse import quote

            calendar_id = str(args.get("calendarId") or "primary").strip() or "primary"
            summary = str(args.get("summary") or "").strip()
            start = str(args.get("startTime") or "").strip()
            end = str(args.get("endTime") or "").strip()
            if not summary or not start or not end:
                return "Error Calendar REST: summary, startTime, endTime required"
            body: dict[str, Any] = {
                "summary": summary,
                "start": _iso_event_time(start),
                "end": _iso_event_time(end),
            }
            if args.get("description"):
                body["description"] = str(args["description"])
            if args.get("location"):
                body["location"] = str(args["location"])
            resp = await client.post(
                f"{_CAL_BASE}/calendars/{quote(calendar_id, safe='')}/events",
                json=body,
            )
        elif name == "update_event":
            from urllib.parse import quote

            calendar_id = str(args.get("calendarId") or "primary").strip() or "primary"
            event_id = str(args.get("eventId") or args.get("id") or "").strip()
            if not event_id:
                return "Error Calendar REST: eventId required"
            body = {}
            if args.get("summary"):
                body["summary"] = str(args["summary"])
            if args.get("description"):
                body["description"] = str(args["description"])
            if args.get("location"):
                body["location"] = str(args["location"])
            if args.get("startTime"):
                body["start"] = _iso_event_time(str(args["startTime"]))
            if args.get("endTime"):
                body["end"] = _iso_event_time(str(args["endTime"]))
            resp = await client.patch(
                f"{_CAL_BASE}/calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}",
                json=body,
            )
        elif name == "delete_event":
            from urllib.parse import quote

            calendar_id = str(args.get("calendarId") or "primary").strip() or "primary"
            event_id = str(args.get("eventId") or args.get("id") or "").strip()
            if not event_id:
                return "Error Calendar REST: eventId required"
            resp = await client.delete(
                f"{_CAL_BASE}/calendars/{quote(calendar_id, safe='')}/events/{quote(event_id, safe='')}"
            )
            if resp.status_code in (200, 204):
                return json.dumps({"ok": True, "deleted": event_id}, ensure_ascii=False)
        elif name in ("suggest_time", "respond_to_event"):
            return (
                f"Error Calendar REST: {name} not mapped yet; "
                "use list_events/create_event/update_event via REST fallback"
            )
        else:
            return f"Error Calendar REST: unsupported tool {name}"

        if resp.status_code >= 400:
            return f"Error Calendar REST ({name}): {resp.status_code} {resp.text[:400]}"
        if not resp.content:
            return json.dumps({"ok": True}, ensure_ascii=False)
        try:
            return json.dumps(resp.json(), ensure_ascii=False)
        except Exception:
            return resp.text


def uses_google_calendar_rest_fallback(connector: dict[str, Any]) -> bool:
    preset = str(connector.get("preset_id") or "").strip().lower()
    url = str(connector.get("endpoint_url") or "").strip().lower()
    return preset == "google_calendar" or "calendarmcp.googleapis.com" in url
