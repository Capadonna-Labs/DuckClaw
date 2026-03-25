#!/usr/bin/env python3
"""Merge N8N_OUTBOUND_WEBHOOK_URL (+ optional N8N_AUTH_KEY) from repo .env into config/ecosystem.api.config.cjs for each app."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    env_path = root / ".env"
    eco_path = root / "config" / "ecosystem.api.config.cjs"
    if not env_path.is_file():
        print("No .env at", env_path, file=sys.stderr)
        return 1
    if not eco_path.is_file():
        print("No ecosystem at", eco_path, file=sys.stderr)
        return 1

    env: dict[str, str] = {}
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip().strip("'\"")

    url = (env.get("N8N_OUTBOUND_WEBHOOK_URL") or "").strip()
    key = (env.get("N8N_AUTH_KEY") or "").strip()
    if not url:
        print("SKIP: N8N_OUTBOUND_WEBHOOK_URL not set in .env")
        return 0

    extra = f'        "N8N_OUTBOUND_WEBHOOK_URL": {json.dumps(url)},\n'
    if key:
        extra += f'        "N8N_AUTH_KEY": {json.dumps(key)},\n'

    text = eco_path.read_text(encoding="utf-8")
    text = re.sub(r'\s*"N8N_OUTBOUND_WEBHOOK_URL":[^\n]+\n', "\n", text)
    text = re.sub(r'\s*"N8N_AUTH_KEY":[^\n]+\n', "\n", text)

    marker = '"REDIS_URL": "redis://localhost:6379/0",\n'
    if text.count(marker) < 1:
        print("Could not find REDIS_URL marker in ecosystem", file=sys.stderr)
        return 1

    new_text = text.replace(marker, marker + extra, 2 if text.count(marker) >= 2 else 1)
    eco_path.write_text(new_text, encoding="utf-8")
    print("OK: merged N8N from .env into", eco_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
