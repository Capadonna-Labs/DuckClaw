"""Google Gmail via REST when official Gmail MCP tools/call is blocked.

Same pattern as Calendar: OAuth bearer often gets Gmail REST 200 while
gmailmcp tools/call returns permission/auth errors (Developer Preview).
Keep MCP tools/list; execute tools over Gmail API v1.
"""

from __future__ import annotations

import base64
import json
import re
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any
from urllib.parse import quote, unquote, urlparse

import httpx

_GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1/users/me"

# Gmail web UI ids (#inbox/FMfcgz…) are NOT Gmail API message/thread ids.
_GMAIL_WEB_ID_RE = re.compile(r"(FMfcgz[0-9A-Za-z_-]+)")
_GMAIL_API_ID_RE = re.compile(r"^[0-9a-f]{10,}$", re.IGNORECASE)


def _bearer(headers: dict[str, str] | None) -> str:
    raw = str((headers or {}).get("Authorization") or "").strip()
    if raw.lower().startswith("bearer "):
        return raw[7:].strip()
    return raw


def _extract_gmail_resource_id(raw: str) -> str:
    """Pull message/thread id from plain id or mail.google.com deep link."""
    text = unquote(str(raw or "").strip())
    if not text:
        return ""
    if "mail.google.com" in text.lower():
        # https://mail.google.com/mail/u/0/#inbox/FMfcgz…  (fragment or path)
        parsed = urlparse(text)
        frag = parsed.fragment or ""
        # fragment forms: inbox/ID, all/ID, label/Foo/ID
        parts = [p for p in frag.split("/") if p]
        if parts:
            text = parts[-1]
        m = _GMAIL_WEB_ID_RE.search(parsed.path + "#" + frag)
        if m:
            return m.group(1)
    m = _GMAIL_WEB_ID_RE.search(text)
    if m:
        return m.group(1)
    return text.strip().strip("/")


def _is_gmail_web_sync_id(resource_id: str, raw: str = "") -> bool:
    rid = _extract_gmail_resource_id(resource_id or raw)
    if not rid:
        return False
    if rid.startswith("FMfcgz"):
        return True
    if "mail.google.com" in (raw or resource_id).lower() and not _GMAIL_API_ID_RE.match(rid):
        return True
    return False


def _label_from_gmail_url(raw: str) -> tuple[str | None, str | None]:
    """Return (labelIds value, optional q=) from a Gmail web URL."""
    text = unquote(str(raw or "").strip())
    if "mail.google.com" not in text.lower():
        return "INBOX", None
    frag = urlparse(text).fragment or ""
    parts = [p for p in frag.split("/") if p]
    if not parts:
        return "INBOX", None
    head = parts[0].lower()
    if head == "inbox":
        return "INBOX", None
    if head == "sent":
        return "SENT", None
    if head == "starred":
        return "STARRED", None
    if head == "drafts":
        return "DRAFT", None
    if head == "spam":
        return "SPAM", None
    if head == "trash":
        return "TRASH", None
    if head == "important":
        return "IMPORTANT", None
    if head == "label" and len(parts) >= 2:
        # Custom label name in URL (may be URL-encoded).
        return None, f"label:{unquote(parts[1])}"
    if head in ("all", "category", "search"):
        return None, "in:anywhere"
    return "INBOX", None


def _header_map(payload: dict[str, Any] | None) -> dict[str, str]:
    headers = (payload or {}).get("headers") or []
    out: dict[str, str] = {}
    for h in headers:
        if not isinstance(h, dict):
            continue
        name = str(h.get("name") or "").strip()
        if name:
            out[name] = str(h.get("value") or "")
    return out


async def _candidates_for_web_sync_id(client: httpx.AsyncClient, raw: str) -> str:
    """Web sync ids (FMfcgz…) are unique but API-opaque — list recent folder mail instead."""
    sync_id = _extract_gmail_resource_id(raw)
    label_id, q = _label_from_gmail_url(raw)
    params: dict[str, str] = {"maxResults": "25"}
    if label_id:
        params["labelIds"] = label_id
    if q:
        params["q"] = q
    listed = await client.get(f"{_GMAIL_BASE}/messages", params=params)
    if listed.status_code >= 400:
        return (
            f"Error Gmail REST: web sync id {sync_id} is not an API id, and listing "
            f"folder failed: {listed.status_code} {listed.text[:200]}"
        )
    messages = (listed.json() or {}).get("messages") or []
    candidates: list[dict[str, Any]] = []
    for i, item in enumerate(messages[:25], start=1):
        mid = str(item.get("id") or "").strip()
        if not mid:
            continue
        meta = await client.get(
            f"{_GMAIL_BASE}/messages/{quote(mid, safe='')}",
            params=[
                ("format", "metadata"),
                ("metadataHeaders", "Subject"),
                ("metadataHeaders", "From"),
                ("metadataHeaders", "Date"),
            ],
        )
        if meta.status_code >= 400:
            continue
        body = meta.json() or {}
        headers = _header_map(body.get("payload") if isinstance(body.get("payload"), dict) else {})
        candidates.append(
            {
                "n": i,
                "messageId": mid,
                "threadId": str(body.get("threadId") or item.get("threadId") or mid),
                "subject": headers.get("Subject") or "",
                "from": headers.get("From") or "",
                "date": headers.get("Date") or "",
                "snippet": str(body.get("snippet") or "")[:180],
            }
        )
    return json.dumps(
        {
            "ok": False,
            "reason": "gmail_web_sync_id",
            "sync_id": sync_id,
            "folder": label_id or q or "INBOX",
            "note": (
                "Gmail web URL ids (FMfcgz…) are unique in the UI but the public Gmail API "
                "rejects them. Below are recent messages from the same folder with real API ids."
            ),
            "candidates": candidates,
            "next": (
                "Call get_message or get_thread with candidates[i].messageId / threadId (hex). "
                "If the user only pasted a link, show a short numbered list (from + subject) and "
                "open the one they pick — or the one matching any extra words they wrote. "
                "Do NOT invent email content. Do NOT open mail.google.com in sandbox."
            ),
        },
        ensure_ascii=False,
    )


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
                if q and _is_gmail_web_sync_id(q, q):
                    return await _candidates_for_web_sync_id(client, q)
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
                raw_tid = str(args.get("threadId") or args.get("id") or "")
                thread_id = _extract_gmail_resource_id(raw_tid)
                if not thread_id:
                    return "Error Gmail REST: threadId required"
                if _is_gmail_web_sync_id(thread_id, raw_tid):
                    return await _candidates_for_web_sync_id(client, raw_tid or thread_id)
                fmt = _thread_format(str(args.get("messageFormat") or args.get("format") or ""))
                resp = await client.get(
                    f"{_GMAIL_BASE}/threads/{quote(thread_id, safe='')}",
                    params={"format": fmt},
                )

            elif name == "get_message":
                raw_mid = str(args.get("messageId") or args.get("id") or "")
                message_id = _extract_gmail_resource_id(raw_mid)
                if not message_id:
                    return "Error Gmail REST: messageId required"
                if _is_gmail_web_sync_id(message_id, raw_mid):
                    return await _candidates_for_web_sync_id(client, raw_mid or message_id)
                fmt = _thread_format(str(args.get("messageFormat") or args.get("format") or ""))
                resp = await client.get(
                    f"{_GMAIL_BASE}/messages/{quote(message_id, safe='')}",
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
