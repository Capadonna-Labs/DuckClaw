#!/usr/bin/env python3
"""
Offline admin tool: encode a 5s reference clip into an immutable voice tensor.

Usage (Mac mini only):
  uv run --project integrations/sensory-node python integrations/sensory-node/scripts/prepare_voice.py \\
    --voice-id leila_assistant --ref-audio ref.wav --ref-text "transcripción del clip"
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

VOICES_DIR = Path(__file__).resolve().parents[1] / "voices"
ALLOWED = frozenset(
    {"campus_legal_main", "leila_assistant", "finanz_alert", "quant_trader_brief"}
)
_DEFAULT_AUDIO_TOKENIZER = "mlx-community/OmniVoice-4bit"


def _audio_tokenizer_path() -> str:
    explicit = (os.environ.get("DUCKCLAW_SENSORY_AUDIO_TOKENIZER_PATH") or "").strip()
    if explicit:
        return explicit
    model_id = (
        os.environ.get("DUCKCLAW_SENSORY_AUDIO_TOKENIZER_MODEL") or _DEFAULT_AUDIO_TOKENIZER
    ).strip()
    from huggingface_hub import snapshot_download

    return snapshot_download(model_id)


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare pre-approved OmniVoice ref tensor")
    parser.add_argument("--voice-id", required=True, choices=sorted(ALLOWED))
    parser.add_argument("--ref-audio", required=True, type=Path)
    parser.add_argument("--ref-text", required=True)
    args = parser.parse_args()

    if sys.platform != "darwin":
        print("prepare_voice requires Apple Silicon (darwin)", file=sys.stderr)
        return 1

    ref_audio = args.ref_audio.expanduser().resolve()
    if not ref_audio.is_file():
        print(f"ref audio not found: {ref_audio}", file=sys.stderr)
        return 1

    try:
        import numpy as np
        from mlx_audio.codec.models.higgs_audio.higgs_audio import HiggsAudioTokenizer
        from mlx_audio.tts.models.omnivoice.utils import create_voice_clone_prompt
        from safetensors.numpy import save_file
    except ImportError as exc:
        print(f"mlx-audio/safetensors/huggingface_hub required: {exc}", file=sys.stderr)
        return 1

    tokenizer_path = _audio_tokenizer_path()
    tokenizer = HiggsAudioTokenizer.from_pretrained(tokenizer_path)
    ref_tokens = create_voice_clone_prompt(
        str(ref_audio),
        tokenizer=tokenizer,
        ref_text=args.ref_text.strip(),
    )
    if ref_tokens is None or int(getattr(ref_tokens, "shape", [0])[0]) == 0:
        print("failed to encode ref_tokens (audio tokenizer)", file=sys.stderr)
        return 1

    out_path = VOICES_DIR / f"{args.voice_id}.safetensors"
    tensors: dict[str, object] = {
        "ref_text": np.frombuffer(args.ref_text.encode("utf-8"), dtype=np.uint8),
        "ref_tokens": np.asarray(ref_tokens),
    }
    save_file(tensors, str(out_path))
    manifest_path = VOICES_DIR / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest[args.voice_id] = {"file": out_path.name, "ref_text": args.ref_text.strip()}
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"wrote {out_path} shape={tensors['ref_tokens'].shape}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
