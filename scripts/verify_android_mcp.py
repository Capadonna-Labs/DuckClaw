#!/usr/bin/env python3
"""Smoke: Android MCP connector + Dispositivos status.

Exit 0 only when ADB sees a device in state `device`.
Optional: ANDROID_ADB_PAIR_PORT + ANDROID_ADB_PAIR_CODE for wireless pairing.

Usage (repo root, env loaded):
  set -a; source .env; set +a
  uv run python scripts/verify_android_mcp.py
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request


def _get(url: str, headers: dict[str, str]) -> dict:
    req = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _post(url: str, headers: dict[str, str], body: dict) -> dict:
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    base = (os.environ.get("DUCKCLAW_GATEWAY_URL") or "http://127.0.0.1:8000").rstrip("/")
    key = (os.environ.get("DUCKCLAW_ADMIN_API_KEY") or "").strip()
    if not key:
        print("DUCKCLAW_ADMIN_API_KEY required", file=sys.stderr)
        return 2

    headers = {"X-Admin-Key": key, "Accept": "application/json"}
    android = _get(f"{base}/api/v1/admin/devices/android-status", headers)
    print("android-status:", json.dumps(android, indent=2)[:2000])

    if not android.get("adb_connected"):
        print("ADB offline — attempting android_adb_connect op…", file=sys.stderr)
        connect = _post(
            f"{base}/api/v1/admin/ops/run",
            headers,
            {"op_id": "android_adb_connect"},
        )
        print("android_adb_connect:", json.dumps(connect, indent=2)[:1200])
        android = _get(f"{base}/api/v1/admin/devices/android-status", headers)
        print("android-status (after connect):", json.dumps(android, indent=2)[:2000])

    connectors = _get(f"{base}/api/v1/admin/mcp/connectors", headers)
    rows = connectors if isinstance(connectors, list) else connectors.get("connectors", [])
    android_row = next(
        (c for c in rows if str(c.get("preset_id") or "").lower() == "android"),
        None,
    )
    if not android_row:
        print("WARN: no android MCP connector — create Android Agent preset in admin UI", file=sys.stderr)
    else:
        print("android connector has_auth:", android_row.get("has_auth"))

    device = android.get("device") or {}
    if android.get("adb_connected") and device.get("state") == "device":
        print(
            f"OK: ADB device {device.get('model') or device.get('serial')} "
            f"battery={android.get('battery')}"
        )
        return 0

    host = android.get("adb_host") or os.environ.get("ANDROID_ADB_HOST") or "?"
    print(
        f"FAIL: no Android in state 'device' (host={host}). "
        "Enable wireless debugging on the phone, pair if needed, then set "
        "ANDROID_ADB_PAIR_PORT/CODE and ANDROID_ADB_DEBUG_PORT in .env "
        "(or legacy tcpip :5555).",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        print(f"HTTP {exc.code}: {exc.read()[:500]}", file=sys.stderr)
        raise SystemExit(1) from exc
