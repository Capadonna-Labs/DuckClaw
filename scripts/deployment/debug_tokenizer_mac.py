#!/usr/bin/env python3
import traceback

candidates = [
    "mlx-community/OmniVoice-bf16",
    "mlx-community/OmniVoice",
    "mlx-community/OmniVoice-4bit",
]

for model_id in candidates:
    print("===", model_id)
    try:
        from mlx_audio.codec.models.higgs_audio.higgs_audio import HiggsAudioTokenizer

        tok = HiggsAudioTokenizer.from_pretrained(model_id)
        print("tokenizer ok", type(tok))
    except Exception as exc:
        print("fail", type(exc).__name__, exc)
        traceback.print_exc()
