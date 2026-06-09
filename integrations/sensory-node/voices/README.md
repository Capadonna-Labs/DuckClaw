# Pre-approved voice tensors (Identity Lock)

Voice cloning is done **offline** by the administrator. Place immutable `.safetensors` (or `.wav` reference clips) here.

Run on Mac mini:

```bash
uv run --project integrations/sensory-node python integrations/sensory-node/scripts/prepare_voice.py \
  --voice-id leila_assistant \
  --ref-audio /path/to/ref.wav \
  --ref-text "Transcripción exacta del clip de 5 segundos."
```

Do **not** commit PII or production voice tensors to git.
