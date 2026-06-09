#!/usr/bin/env python3
from huggingface_hub import snapshot_download
from mlx_audio.codec.models.higgs_audio.higgs_audio import HiggsAudioTokenizer

p = snapshot_download("mlx-community/OmniVoice-4bit")
tok = HiggsAudioTokenizer.from_pretrained(p)
print("tokenizer ok", type(tok).__name__, "path", p)
