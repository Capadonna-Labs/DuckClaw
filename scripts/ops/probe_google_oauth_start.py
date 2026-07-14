"""Probe Google Workspace OAuth start on VPS gateway."""

from __future__ import annotations

import json
import os
import subprocess


def _post_start(*, body: str) -> tuple[str, str]:
    key = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    if not key:
        for line in open("/root/duckclaw/.env", encoding="utf-8"):
            if line.startswith("DUCKCLAW_ADMIN_API_KEY="):
                key = line.split("=", 1)[1].strip()
                break
    proc = subprocess.run(
        [
            "curl",
            "-sS",
            "-w",
            "\n%{http_code}",
            "-X",
            "POST",
            "-H",
            f"X-Admin-Key: {key}",
            "-H",
            "X-Duckclaw-Actor: juanjoarevalo57@gmail.com",
            "-H",
            "Content-Type: application/json",
            "-d",
            body,
            "http://127.0.0.1:8000/api/v1/admin/mcp/connectors/mcp_google_workspace/oauth/start",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    out, status = proc.stdout.rsplit("\n", 1)
    return out, status


def main() -> None:
    for label, body in (
        ("empty_body", "{}"),
        (
            "admin_origin_mismatch",
            json.dumps(
                {
                    "redirect_uri": "https://ubuntu-2gb-ash-1.tailc85db0.ts.net:8443/api/admin/mcp/connectors/oauth/callback"
                }
            ),
        ),
    ):
        raw, status = _post_start(body=body)
        print("case", label, "status", status)
        if status != "200":
            print(raw[:800])
            continue
        data = json.loads(raw)
        redirect = str(data.get("redirect_uri") or "")
        url = str(data.get("authorization_url") or "")
        print("  redirect_uri", redirect)
        print("  uses_v1_callback", redirect.endswith("/api/v1/oauth/callback"))
        print("  no_8443", ":8443" not in redirect)
        print("  no_gmail_modify", "gmail.modify" not in url)
        print("  has_gmail_readonly", "gmail.readonly" in url)


if __name__ == "__main__":
    main()
