#!/usr/bin/env python3
"""Bootstrap Android MCP connector + worker grant via gateway API (no admin UI).

Requires ANDROID_MCP_GRANT_WORKER (worker_id that should receive mcp_android tools).

Usage:
  set -a; source .env; set +a
  ANDROID_MCP_GRANT_WORKER=my-worker uv run python scripts/setup_android_mcp.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request


def _request(method: str, url: str, headers: dict[str, str], body: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={**headers, "Content-Type": "application/json", "Accept": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _poll_task(base: str, headers: dict[str, str], task_id: str, *, label: str) -> None:
    deadline = time.time() + 90
    while time.time() < deadline:
        row = _request("GET", f"{base}/api/v1/admin/write-tasks/{task_id}", headers)
        status = str(row.get("status") or "").lower()
        if status in {"completed", "done", "success"}:
            print(f"OK {label}: {task_id}")
            return
        if status in {"failed", "error"}:
            raise RuntimeError(f"{label} failed: {row.get('detail') or row}")
        time.sleep(1.5)
    raise TimeoutError(f"{label} task timeout: {task_id}")


def main() -> int:
    base = (os.environ.get("DUCKCLAW_GATEWAY_URL") or "http://127.0.0.1:8000").rstrip("/")
    key = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    worker_id = (os.environ.get("ANDROID_MCP_GRANT_WORKER") or "").strip()
    if not key:
        print("DUCKCLAW_ADMIN_API_KEY required", file=sys.stderr)
        return 2
    if not worker_id:
        print("ANDROID_MCP_GRANT_WORKER required", file=sys.stderr)
        return 2

    headers = {"X-Admin-Key": key, "X-Duckclaw-Actor": "setup-android-mcp"}
    connector_id = "mcp_android"

    presets = _request("GET", f"{base}/api/v1/admin/mcp/connectors/presets", headers)
    android_preset = next(
        (p for p in presets.get("presets", []) if str(p.get("preset_id") or "") == "android"),
        None,
    )
    if not android_preset:
        print("FAIL: android preset missing — reload gateway / deploy presets", file=sys.stderr)
        return 1

    connectors = _request("GET", f"{base}/api/v1/admin/mcp/connectors", headers)
    rows = connectors.get("connectors", connectors if isinstance(connectors, list) else [])
    exists = any(str(c.get("connector_id") or "") == connector_id for c in rows)
    if not exists:
        created = _request(
            "POST",
            f"{base}/api/v1/admin/mcp/connectors",
            headers,
            {"preset_id": "android", "connector_id": connector_id, "display_name": "Android Agent"},
        )
        task_id = str(created.get("task_id") or "")
        if task_id:
            _poll_task(base, headers, task_id, label="create connector")
        print("created connector", connector_id)
    else:
        print("connector exists", connector_id)

    granted = _request(
        "POST",
        f"{base}/api/v1/admin/mcp/connectors/{connector_id}/grants",
        headers,
        {"worker_id": worker_id},
    )
    grant_task = str(granted.get("task_id") or "")
    if grant_task:
        _poll_task(base, headers, grant_task, label=f"grant {worker_id}")

    _request("POST", f"{base}/api/v1/admin/gateway/release-worker-cache", headers, {})
    print("released worker cache")

    test = _request("POST", f"{base}/api/v1/admin/mcp/connectors/{connector_id}/test", headers, {})
    print("list_tools:", json.dumps(test, indent=2)[:1500])
    if not test.get("ok"):
        print("WARN: connector test failed (ADB or MCP offline?)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read()[:800]}", file=sys.stderr)
        raise SystemExit(1) from exc
