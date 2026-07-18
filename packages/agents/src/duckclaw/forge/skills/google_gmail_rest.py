"""Google Gmail via REST when official Gmail MCP tools/call is blocked.

Same pattern as Calendar: OAuth bearer often gets Gmail REST 200 while
gmailmcp tools/call returns permission/auth errors (Developer Preview).
Keep MCP tools/list; execute tools over Gmail API v1.
"""

from __future__ import annotations

import base64
import json
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from urllib.parse import quote

import httpx

_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"


def _bearer(headers: dict[str, str] | None) -> str:
    raw = str((headers or {}).get("Authorization") or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        return [str(x).strip() for x in value if str(x).strip()]
    return [str(value).strip()] if str(value).strip() else []


def _thread_format(message_format: str) -> str:
    fmt = (message_format or "").strip().upper()
    if fmt in ("MINIMAL", "METADATA"):
        return "metadata"
    if fmt in ("FULL", "FULL_CONTENT", ""):
        return "full"
    return "full"


def _build_draft_raw(args: dict[str, Any]) -> str:
    to = _as_list(args.get("to"))
    if not to:
        raise ValueError("to required")
    subject = str(args.get("subject") or "")
    body = str(args.get("body") or "")
    html_body = str(args.get("htmlBody") or args.get("html_body") or "")
    reply_to = str(args.get("replyToMessageId") or args.get("reply_to_message_id") or "").strip()

    if html_body:
        msg: MIMEText | MIMEMultipart = MIMEMultipart("alternative")
        if body:
            msg.attach(MIMEText(body, "plain", "utf-8"))
        msg.attach(MIMEText(html_body, "html", "utf-8"))
    else:
        msg = MIMEText(body, "plain", "utf-8")

    msg["To"] = ", ".join(to)
    cc = _as_list(args.get("cc"))
    bcc = _as_list(args.get("bcc"))
    if cc:
        msg["Cc"] = ", ".join(cc)
    if bcc:
        msg["Bcc"] = ", ".join(bcc)
    msg["Subject"] = subject
    if reply_to:
        msg["In-Reply-To"] = reply_to
        msg["References"] = reply_to

    raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii").rstrip("=")
    return raw


async def call_google_gmail_rest(
    tool_name: str,
    arguments: dict[str, Any] | None,
    *,
    headers: dict[str, str] | None = None,
) -> str:
    token = _bearer(headers)
    if not token:
        return "Error Gmail REST: missing bearer token"
    args = dict(arguments or {})
    auth = {"Authorization": f"Bearer {token}"}
    name = (tool_name or "").strip()

    async with httpx.AsyncClient(timeout=30.0, headers=auth) as client:
        try:
            if name == "search_threads":
                params: dict[str, str] = {}
                q = str(args.get("query") or args.get("q") or "").strip()
                if q:
                    params["q"] = q
                page_size = args.get("pageSize") or args.get("maxResults") or args.get("max_results")
                if page_size:
                    params["maxResults"] = str(page_size)
                if args.get("pageToken"):
                    params["pageToken"] = str(args["pageToken"])
                if args.get("includeTrash") is True:
                    params["includeSpamTrash"] = "true"
                resp = await client.get(f"{_GMAIL_BASE}/threads", params=params)

            elif name == "get_thread":
                thread_id = str(args.get("threadId") or args.get("id") or "").strip()
                if not thread_id:
                    return "Error Gmail REST: threadId required"
                fmt = _thread_format(str(args.get("messageFormat") or args.get("format") or ""))
                resp = await client.get(
                    f"{_GMAIL_BASE}/threads/{quote(thread_id, safe='')}",
                    params={"format": fmt},
                )

            elif name == "list_labels":
                resp = await client.get(f"{_GMAIL_BASE}/labels")

            elif name == "list_drafts":
                params = {}
                page_size = args.get("pageSize") or args.get("maxResults")
                if page_size:
                    params["maxResults"] = str(page_size)
                if args.get("pageToken"):
                    params["pageToken"] = str(args["pageToken"])
                resp = await client.get(f"{_GMAIL_BASE}/drafts", params=params)

            elif name == "create_draft":
                try:
                    raw = _build_draft_raw(args)
                except ValueError as exc:
                    return f"Error Gmail REST: {exc}"
                body: dict[str, Any] = {"message": {"raw": raw}}
                reply_to = str(
                    args.get("replyToMessageId") or args.get("reply_to_message_id") or ""
                ).strip()
                if reply_to:
                    # Best-effort: put reply under same thread when message id known.
                    msg_meta = await client.get(
                        f"{_GMAIL_BASE}/messages/{quote(reply_to, safe='')}",
                        params={"format": "minimal"},
                    )
                    if msg_meta.status_code < 400:
                        tid = str((msg_meta.json() or {}).get("threadId") or "").strip()
                        if tid:
                            body["message"]["threadId"] = tid
                resp = await client.post(f"{_GMAIL_BASE}/drafts", json=body)

            elif name == "label_message":
                message_id = str(args.get("messageId") or args.get("id") or "").strip()
                label_ids = _as_list(args.get("labelIds") or args.get("label_ids"))
                if not message_id or not label_ids:
                    return "Error Gmail REST: messageId and labelIds required"
                resp = await client.post(
                    f"{_GMAIL_BASE}/messages/{quote(message_id, safe='')}/modify",
                    json={"addLabelIds": label_ids},
                )

            elif name == "unlabel_message":
                message_id = str(args.get("messageId") or args.get("id") or "").strip()
                label_ids = _as_list(args.get("labelIds") or args.get("label_ids"))
                if not message_id or not label_ids:
                    return "Error Gmail REST: messageId and labelIds required"
                resp = await client.post(
                    f"{_GMAIL_BASE}/messages/{quote(message_id, safe='')}/modify",
                    json={"removeLabelIds": label_ids},
                )

            elif name == "label_thread":
                thread_id = str(args.get("threadId") or args.get("id") or "").strip()
                label_ids = _as_list(args.get("labelIds") or args.get("label_ids"))
                if not thread_id or not label_ids:
                    return "Error Gmail REST: threadId and labelIds required"
                resp = await client.post(
                    f"{_GMAIL_BASE}/threads/{quote(thread_id, safe='')}/modify",
                    json={"addLabelIds": label_ids},
                )

            elif name == "unlabel_thread":
                thread_id = str(args.get("threadId") or args.get("id") or "").strip()
                label_ids = _as_list(args.get("labelIds") or args.get("label_ids"))
                if not thread_id or not label_ids:
                    return "Error Gmail REST: threadId and labelIds required"
                resp = await client.post(
                    f"{_GMAIL_BASE}/threads/{quote(thread_id, safe='')}/modify",
                    json={"removeLabelIds": label_ids},
                )

            else:
                return f"Error Gmail REST: unsupported tool {name}"
        except httpx.HTTPError as exc:
            return f"Error Gmail REST ({name}): {exc}"

        if resp.status_code >= 400:
            return f"Error Gmail REST ({name}): {resp.status_code} {resp.text[:400]}"
        if not resp.content:
            return json.dumps({"ok": True}, ensure_ascii=False)
        try:
            return json.dumps(resp.json(), ensure_ascii=False)
        except Exception:
            return resp.text


def uses_google_gmail_rest_fallback(connector: dict[str, Any]) -> bool:
    preset = str(connector.get("preset_id") or "").strip().lower()
    url = str(connector.get("endpoint_url") or "").strip().lower()
    return preset == "google_gmail" or "gmailmcp.googleapis.com" in url
