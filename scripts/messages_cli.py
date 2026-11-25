#!/usr/bin/env python3
"""Read and write DuckClaw messages (Historial > Mensajes) from a terminal: for a coding agent that works for a console user.

Env: DUCKCLAW_GATEWAY_URL, DUCKCLAW_ADMIN_API_KEY (same as the admin BFF), DUCKCLAW_MESSAGES_AS (the person's console email) and
DUCKCLAW_MESSAGES_LABEL (how the agent signs, e.g. "Claude (Sam)").

  uv run python scripts/messages_cli.py channels
  uv run python scripts/messages_cli.py read <channel_id> [--since "2026-11-25 15:00:00"]
  uv run python scripts/messages_cli.py post <channel_id> "texto"
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request


def call(method: str, path: str, body: dict | None = None) -> dict:
    base = os.environ["DUCKCLAW_GATEWAY_URL"].rstrip("/")
    req = urllib.request.Request(
        f"{base}/api/v1/admin/messages{path}",
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"X-Admin-Key": os.environ["DUCKCLAW_ADMIN_API_KEY"], "X-Duckclaw-Actor": os.environ["DUCKCLAW_MESSAGES_AS"],
                 "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read())


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    cmd = argv[0]
    if cmd == "channels":
        for c in call("GET", "/channels")["channels"]:
            print(f"{c['id']}  [{c['kind']}] {c['name']}  ({c['message_count']} msgs, {c['updated_at']})")
    elif cmd == "read" and len(argv) >= 2:
        since = argv[argv.index("--since") + 1] if "--since" in argv else ""
        ch = call("GET", f"/channels/{urllib.parse.quote(argv[1])}?since={urllib.parse.quote(since)}")
        print(f"# {ch['name']} — {', '.join(ch['members'])}")
        for m in ch["messages"]:
            print(f"[{m['created_at'][:19]}] {m['author']}: {m['body']}")
    elif cmd == "post" and len(argv) >= 3:
        r = call("POST", f"/channels/{urllib.parse.quote(argv[1])}", {"body": argv[2], "author_label": os.environ.get("DUCKCLAW_MESSAGES_LABEL", "")})
        print(r["message_id"])
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
