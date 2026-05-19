#!/usr/bin/env python3
"""
Comprueba que Telegram pueda entregar webhooks a este Mac (Tailscale Funnel + gateway local).

Salida 0 = OK o no aplica (sin DUCKCLAW_PUBLIC_URL ts.net).
Salida 1 = ingress roto (Tailscale parado, funnel caído, gateway no responde).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_DEBUG_LOG = REPO_ROOT / ".cursor" / "debug-77cb49.log"


def _load_dotenv() -> None:
    env_path = REPO_ROOT / ".env"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            key = k.strip()
            if key and key not in os.environ:
                os.environ[key] = v.strip().strip("'\"")


def _agent_log(message: str, data: dict, hypothesis_id: str) -> None:
    try:
        payload = {
            "sessionId": "77cb49",
            "timestamp": int(time.time() * 1000),
            "location": "check_telegram_ingress.py",
            "message": message,
            "data": data,
            "hypothesisId": hypothesis_id,
            "runId": "ingress-check",
        }
        with _DEBUG_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _tailscale_running() -> bool:
    if not shutil.which("tailscale"):
        return False
    try:
        proc = subprocess.run(
            ["tailscale", "status"],
            capture_output=True,
            text=True,
            timeout=8,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        if proc.returncode != 0:
            return False
        return "Tailscale is stopped" not in out and "Stopped" not in out[:200]
    except Exception:
        return False


def _probe_url(url: str, timeout: float = 12.0) -> tuple[int | None, str]:
    try:
        req = urllib.request.Request(
            url,
            data=b'{"update_id":0}',
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, ""
    except urllib.error.HTTPError as e:
        return e.code, (e.read().decode("utf-8", errors="replace")[:200] if e.fp else str(e))
    except Exception as e:
        return None, str(e)[:200]


def main() -> int:
    _load_dotenv()
    public = (os.environ.get("DUCKCLAW_PUBLIC_URL") or "").strip().rstrip("/")
    from duckclaw.gateway_port import resolve_gateway_port

    port = resolve_gateway_port()
    local_path = "/api/v1/telegram/marco_assistant"
    issues: list[str] = []

    local_url = f"http://127.0.0.1:{port}{local_path}"
    local_status, local_err = _probe_url(local_url, timeout=8.0)
    if local_status != 200:
        issues.append(
            f"Gateway local no responde en {local_url} (HTTP {local_status or 'error'}: {local_err})"
        )

    if not public:
        if issues:
            for line in issues:
                print(f"error: {line}", file=sys.stderr)
            _agent_log("ingress check failed", {"issues": issues}, "H6")
            return 1
        print("ok: sin DUCKCLAW_PUBLIC_URL (solo comprobado gateway local)")
        return 0

    if ".ts.net" in public:
        if not _tailscale_running():
            issues.append(
                "Tailscale está PARADO. Telegram no puede entregar webhooks. "
                "Abre la app Tailscale o ejecuta: tailscale up"
            )
        funnel_status = ""
        if shutil.which("tailscale"):
            try:
                fs = subprocess.run(
                    ["tailscale", "funnel", "status"],
                    capture_output=True,
                    text=True,
                    timeout=8,
                )
                funnel_status = (fs.stdout or fs.stderr or "").strip()
            except Exception:
                funnel_status = ""
            if funnel_status and "No serve config" in funnel_status:
                issues.append(
                    f"Tailscale Funnel no expone el puerto {port}. Ejecuta: "
                    f"tailscale funnel --bg {port}"
                )

        public_probe = f"{public}{local_path}"
        pub_status, pub_err = _probe_url(public_probe, timeout=15.0)
        if pub_status != 200:
            issues.append(
                f"URL pública no alcanzable: {public_probe} "
                f"(HTTP {pub_status or 'error'}: {pub_err}). "
                f"Con Tailscale activo: tailscale funnel --bg {port}"
            )

    if issues:
        for line in issues:
            print(f"error: {line}", file=sys.stderr)
        _agent_log("telegram ingress broken", {"issues": issues, "public": public}, "H6")
        return 1

    print(f"ok: Telegram ingress ({public} → gateway :{port})")
    _agent_log("telegram ingress ok", {"public": public, "port": port}, "H6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
