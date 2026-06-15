#!/usr/bin/env python3
"""Regenerate all manifest voices on Mac (run on Mac mini)."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path.home() / "Desktop" / "duckclaw"
SCRIPT = REPO / "integrations/sensory-node/scripts/prepare_voice.py"
VOICES_DIR = REPO / "integrations/sensory-node/voices"
REFS = VOICES_DIR / "refs"


def _voice_jobs() -> list[tuple[str, str]]:
    manifest_path = VOICES_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict):
        raise ValueError("voices manifest must be a JSON object")
    jobs: list[tuple[str, str]] = []
    for voice_id, entry in sorted(manifest.items()):
        ref_text = ""
        if isinstance(entry, dict):
            ref_text = str(entry.get("ref_text") or "").strip()
        if ref_text:
            jobs.append((str(voice_id), ref_text))
    return jobs


def main() -> int:
    jobs = _voice_jobs()
    if not jobs:
        print("no manifest voices with ref_text to regenerate")
        return 0
    for voice_id, ref_text in jobs:
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
