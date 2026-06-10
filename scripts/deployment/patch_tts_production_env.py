#!/usr/bin/env python3
"""Idempotent .env patch for TTS production settings (Mac mini + VPS gateway)."""
from __future__ import annotations

import argparse
import re
from pathlib import Path

MAC_VARS: dict[str, str] = {
    "DUCKCLAW_SENSORY_TTS_MODEL": "mlx-community/OmniVoice",
    "DUCKCLAW_SENSORY_TTS_MAX_CHARS": "1400",
    "DUCKCLAW_SENSORY_TTS_MAX_DURATION_SEC": "90",
    "DUCKCLAW_SENSORY_TTS_NUM_STEPS": "48",
    "DUCKCLAW_SENSORY_TTS_TIMEOUT_MS": "60000",
}

VPS_VARS: dict[str, str] = {
    "DUCKCLAW_SENSORY_TIMEOUT_TTS": "90.0",
    "DUCKCLAW_TTS_VOICE_MAP": (
        '{"quant-trader":"finanz_alert","finanz":"finanz_alert","default":"leila_assistant"}'
    ),
}


def _patch_env(path: Path, updates: dict[str, str], *, label: str) -> None:
    text = path.read_text(encoding="utf-8") if path.is_file() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    changed: list[str] = []
    for key, value in updates.items():
        line = f"{key}={value}"
        pattern = re.compile(rf"^{re.escape(key)}=.*$", re.MULTILINE)
        if pattern.search(text):
            text = pattern.sub(line, text, count=1)
        else:
            if "# TTS production" not in text:
                text += f"\n# TTS production ({label})\n"
            text += f"{line}\n"
        changed.append(key)
    path.write_text(text, encoding="utf-8")
    print(f"patched {path} ({label}): {', '.join(changed)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Patch TTS env vars")
    parser.add_argument("--mac-env", type=Path, help="Path to Mac mini .env")
    parser.add_argument("--vps-env", type=Path, help="Path to VPS gateway .env")
    args = parser.parse_args()
    if not args.mac_env and not args.vps_env:
        parser.error("pass --mac-env and/or --vps-env")
    if args.mac_env:
        _patch_env(args.mac_env.expanduser().resolve(), MAC_VARS, label="mac")
    if args.vps_env:
        _patch_env(args.vps_env.expanduser().resolve(), VPS_VARS, label="vps")
    print("OK — restart: pm2 restart Sensory-Node --update-env (Mac) and pm2 restart DuckClaw-Gateway (VPS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
