#!/usr/bin/env python3
import sys
from pathlib import Path

from mlx_audio.codec.models.higgs_audio.higgs_audio import HiggsAudioTokenizer
from mlx_audio.tts.models.omnivoice.utils import create_voice_clone_prompt

model_path = sys.argv[1]
ref_wav = sys.argv[2]
tok = HiggsAudioTokenizer.from_pretrained(model_path)
print("tokenizer ok")
tokens = create_voice_clone_prompt(ref_wav, tokenizer=tok, ref_text="Hola soy Leila")
print("ref_tokens shape", tokens.shape)
