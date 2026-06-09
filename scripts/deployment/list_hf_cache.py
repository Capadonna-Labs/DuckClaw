#!/usr/bin/env python3
from pathlib import Path

hub = Path.home() / ".cache" / "huggingface" / "hub"
for p in sorted(hub.glob("models--*OmniVoice*")):
    print(p.name)
    snaps = p / "snapshots"
    if snaps.is_dir():
        for s in snaps.iterdir():
            print(" ", s)
            at = s / "audio_tokenizer"
            if at.is_dir():
                print("   audio_tokenizer:", list(at.iterdir())[:5])
