"""Android MCP — ADB device probe + local MCP reachability."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.error
import urllib.request
from datetime import UTC, datetime
from typing import Any


def android_adb_host() -> str:
    return (os.environ.get("ANDROID_ADB_HOST") or "").strip()


def android_adb_debug_port() -> str:
    return (os.environ.get("ANDROID_ADB_DEBUG_PORT") or "5555").strip()


def android_mcp_port() -> int:
    raw = (os.environ.get("ANDROID_MCP_PORT") or "8080").strip()
    try:
        return max(1, min(65535, int(raw)))
    except ValueError:
        return 8080


def android_mcp_url() -> str:
    return f"http://127.0.0.1:{android_mcp_port()}/mcp"


def resolve_connector_endpoint_url(connector: dict[str, Any]) -> str:
    """ADB connectors use live ANDROID_MCP_PORT; ignore stale ${...} in DB."""
    if connector_uses_adb_auth(connector):
        return android_mcp_url()
    return str(connector.get("endpoint_url") or "").strip()


def _run_adb(args: list[str], *, timeout: float = 15.0) -> tuple[int, str, str]:
    try:
        proc = subprocess.run(
            ["adb", *args],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, proc.stdout or "", proc.stderr or ""
    except FileNotFoundError:
        return 127, "", "adb not found in PATH"
    except subprocess.TimeoutExpired:
        return 124, "", "adb command timed out"


def parse_adb_devices(output: str) -> list[dict[str, str]]:
    devices: list[dict[str, str]] = []
    for line in output.splitlines()[1:]:
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, state = parts[0], parts[1]
        model = ""
        for part in parts[2:]:
            if part.startswith("model:"):
                model = part.split(":", 1)[1]
        devices.append({"serial": serial, "state": state, "model": model})
    return devices


def parse_battery_output(output: str) -> dict[str, Any]:
    level: int | None = None
    charging: bool | None = None
    for line in output.splitlines():
        text = line.strip()
        if text.startswith("level:"):
            try:
                level = int(text.split(":", 1)[1].strip())
            except ValueError:
                level = None
        if text.startswith("status:"):
            status = text.split(":", 1)[1].strip()
            charging = status in {"2", "5"}
    out: dict[str, Any] = {}
    if level is not None:
        out["level_pct"] = level
    if charging is not None:
        out["charging"] = charging
    return out


def probe_mcp_reachable(url: str | None = None) -> tuple[bool, str]:
    target = (url or android_mcp_url()).strip()
    if not target:
        return False, "MCP URL vacía"
    try:
        req = urllib.request.Request(target, method="GET")
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            return 200 <= int(resp.status) < 500, ""
    except urllib.error.HTTPError as exc:
        # ponytail: MCP may 405 on GET but proves TCP/HTTP up
        if exc.code in {404, 405, 406}:
            return True, ""
        return False, str(exc)[:200]
    except Exception as exc:
        return False, str(exc)[:200]


def connector_uses_adb_auth(connector: dict[str, Any]) -> bool:
    kind = str(connector.get("auth_kind") or "").strip().lower()
    if kind == "adb":
        return True
    metadata = connector.get("metadata") or {}
    if isinstance(metadata, str):
        try:
            metadata = json.loads(metadata)
        except json.JSONDecodeError:
            metadata = {}
    return isinstance(metadata, dict) and metadata.get("connection_type") == "adb_device"


def adb_auth_ready(*, adb_connected: bool, mcp_reachable: bool) -> bool:
    return adb_connected and mcp_reachable


def primary_adb_serial() -> str:
    """First online device serial from ``adb devices``, or empty."""
    code, stdout, _ = _run_adb(["devices", "-l"])
    if code == 127:
        return ""
    for row in parse_adb_devices(stdout):
        if row.get("state") == "device" and row.get("serial"):
            return str(row["serial"])
    return ""


def android_expand_notifications(*, serial: str | None = None) -> dict[str, Any]:
    """Open notification shade via ``cmd statusbar expand-notifications`` (API 24+)."""
    sid = (serial or primary_adb_serial()).strip()
    if not sid:
        return {"ok": False, "error": "no ADB device in state device"}
    code, stdout, stderr = _run_adb(
        ["-s", sid, "shell", "cmd", "statusbar", "expand-notifications"],
        timeout=10.0,
    )
    return {
        "ok": code == 0,
        "serial": sid,
        "action": "expand-notifications",
        "exit_code": code,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
        "hint": "Tras expandir, usa get_ui_dump; dismiss = swipe horizontal en fila.",
    }


def android_collapse_statusbar(*, serial: str | None = None) -> dict[str, Any]:
    """Collapse status bar / notification shade."""
    sid = (serial or primary_adb_serial()).strip()
    if not sid:
        return {"ok": False, "error": "no ADB device in state device"}
    code, stdout, stderr = _run_adb(
        ["-s", sid, "shell", "cmd", "statusbar", "collapse"],
        timeout=10.0,
    )
    return {
        "ok": code == 0,
        "serial": sid,
        "action": "collapse",
        "exit_code": code,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }


def android_adb_connect(
    host: str | None = None,
    *,
    debug_port: str | int | None = None,
) -> dict[str, Any]:
    target = (host or android_adb_host()).strip()
    if not target:
        return {"ok": False, "error": "ANDROID_ADB_HOST no configurado"}

    pair_port = (os.environ.get("ANDROID_ADB_PAIR_PORT") or "").strip()
    pair_code = (os.environ.get("ANDROID_ADB_PAIR_CODE") or "").strip()
    if pair_port and pair_code:
        pair_target = target if re.search(r":\d+$", target) else f"{target}:{pair_port}"
        pcode, pstdout, pstderr = _run_adb(["pair", pair_target, pair_code])
        if pcode != 0 and "already paired" not in (pstdout + pstderr).lower():
            return {
                "ok": False,
                "error": "adb pair failed",
                "host": pair_target,
                "exit_code": pcode,
                "stdout": pstdout.strip(),
                "stderr": pstderr.strip(),
            }

    used_port = ""
    if not re.search(r":\d+$", target):
        used_port = str(debug_port).strip() if debug_port is not None else android_adb_debug_port()
        target = f"{target}:{used_port}"
    else:
        m = re.search(r":(\d+)$", target)
        used_port = m.group(1) if m else ""
    code, stdout, stderr = _run_adb(["connect", target])
    merged = f"{stdout}\n{stderr}".lower()
    ok = code == 0 and ("connected" in merged or "already connected" in merged)
    return {
        "ok": ok,
        "host": target,
        "debug_port": used_port,
        "exit_code": code,
        "stdout": stdout.strip(),
        "stderr": stderr.strip(),
    }


def android_device_status() -> dict[str, Any]:
    read_at = datetime.now(UTC).isoformat()
    host = android_adb_host()
    mcp_url = android_mcp_url()
    mcp_ok, mcp_err = probe_mcp_reachable(mcp_url)

    code, stdout, stderr = _run_adb(["devices", "-l"])
    adb_available = code != 127
    devices = parse_adb_devices(stdout) if adb_available else []
    online = [row for row in devices if row.get("state") == "device"]

    battery: dict[str, Any] = {}
    primary = online[0] if online else (devices[0] if devices else None)
    if primary and primary.get("serial"):
        bcode, bstdout, _ = _run_adb(
            ["-s", primary["serial"], "shell", "dumpsys", "battery"],
            timeout=10.0,
        )
        if bcode == 0:
            battery = parse_battery_output(bstdout)

    adb_connected = bool(online)
    return {
        "ok": adb_connected and mcp_ok,
        "adb_available": adb_available,
        "adb_connected": adb_connected,
        "adb_host": host,
        "adb_debug_port": android_adb_debug_port(),
        "mcp_url": mcp_url,
        "mcp_reachable": mcp_ok,
        "mcp_error": mcp_err if not mcp_ok else "",
        "device": primary,
        "devices": devices,
        "battery": battery,
        "read_at": read_at,
        "adb_stderr": stderr.strip() if adb_available and code not in (0, 124) else "",
    }
