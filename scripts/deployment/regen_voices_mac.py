#!/usr/bin/env python3
"""Regenerate all manifest voices on Mac (run on Mac mini)."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path.home() / "Desktop" / "duckclaw"
SCRIPT = REPO / "integrations/sensory-node/scripts/prepare_voice.py"
REFS = REPO / "integrations/sensory-node/voices/refs"
VOICES = [
    ("leila_assistant", "Hola soy Leila tu asistente de DuckClaw"),
    ("finanz_alert", "Alerta financiera DuckClaw revisa tu portafolio"),
    ("campus_legal_main", "Asesoria legal campus DuckClaw"),
    ("quant_trader_brief", "Resumen de mercado Quant Trader DuckClaw"),
]

def main() -> int:
    for voice_id, ref_text in VOICES:
        wav = REFS / f"{voice_id}.wav"
        if not wav.is_file():
            print(f"missing {wav}", file=sys.stderr)
            return 1
        cmd = [
            "uv", "run", "--project", "integrations/sensory-node", "python",
            str(SCRIPT),
            "--voice-id", voice_id,
            "--ref-audio", str(wav),
            "--ref-text", ref_text,
        ]
        print("==>", " ".join(cmd))
        subprocess.run(cmd, cwd=REPO, check=True)
    for p in sorted((REPO / "integrations/sensory-node/voices").glob("*.safetensors")):
        print(p.name, p.stat().st_size)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
