#!/usr/bin/env python3
"""
Precheck antes de cloudflared: comprueba si hay algo escuchando en :3000
(IPv4 vs IPv6 localhost). Escribe NDJSON en .cursor/debug-8d6707.log (sesión debug).
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

import httpx

_LOG = Path(__file__).resolve().parents[1] / ".cursor" / "debug-8d6707.log"
_SESSION = "8d6707"


def _log(hypothesis_id: str, message: str, data: dict) -> None:
    line = {
        "sessionId": _SESSION,
        "timestamp": int(time.time() * 1000),
        "hypothesisId": hypothesis_id,
        "location": "scripts/crm_origin_check.py",
        "message": message,
        "data": data,
        "runId": "crm-origin-precheck",
    }
    _LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(_LOG, "a", encoding="utf-8") as f:
        f.write(json.dumps(line, ensure_ascii=False) + "\n")


def main() -> None:
    # region agent log
    repo = Path(__file__).resolve().parents[1]
    crm = repo / "external" / "retoPWRSomegahack"
    for label, p in (("repo_root", repo), ("crm_app", crm)):
        try:
            u = shutil.disk_usage(str(p if p.exists() else repo))
            _log(
                "H5",
                "disk_usage",
                {
                    "path": str(p),
                    "label": label,
                    "total_bytes": u.total,
                    "used_bytes": u.used,
                    "free_bytes": u.free,
                    "free_gib": round(u.free / (1024**3), 2),
                },
            )
        except OSError as e:
            _log("H5", "disk_usage_error", {"path": str(p), "error": str(e)[:200]})
    # endregion agent log

    targets = [
        ("H1", "http://127.0.0.1:3000/", "IPv4 loopback"),
        ("H2", "http://[::1]:3000/", "IPv6 loopback (localhost suele resolver aquí)"),
    ]
    for hid, url, label in targets:
        try:
            r = httpx.get(url, timeout=3.0, follow_redirects=True)
            _log(
                hid,
                "origin respondió",
                {"url": url, "label": label, "status": r.status_code, "ok": True},
            )
        except httpx.RequestError as e:
            _log(
                hid,
                "origin no alcanzable",
                {"url": url, "label": label, "error": type(e).__name__, "detail": str(e)[:200]},
            )


if __name__ == "__main__":
    main()
