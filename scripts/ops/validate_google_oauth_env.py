"""Check GOOGLE_OAUTH_* env vars before Workspace MCP OAuth."""

from __future__ import annotations

import os
import sys


def main() -> int:
    client_id = (os.environ.get("GOOGLE_OAUTH_CLIENT_ID") or "").strip()
    secret = (os.environ.get("GOOGLE_OAUTH_CLIENT_SECRET") or "").strip()
    redirect = (os.environ.get("GOOGLE_OAUTH_REDIRECT_URI") or "").strip()
    ok = True
    if not client_id:
        print("missing GOOGLE_OAUTH_CLIENT_ID")
        ok = False
    elif not client_id.endswith(".apps.googleusercontent.com"):
        print("warn: GOOGLE_OAUTH_CLIENT_ID does not look like a Google web client")
    if not secret:
        print("missing GOOGLE_OAUTH_CLIENT_SECRET")
        ok = False
    if not redirect:
        print("missing GOOGLE_OAUTH_REDIRECT_URI (or set DUCKCLAW_ADMIN_URL / DUCKCLAW_PUBLIC_URL)")
    elif not redirect.startswith("https://"):
        print("warn: redirect URI should use https in production")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
