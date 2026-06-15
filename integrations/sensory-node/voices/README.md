# Pre-approved voice tensors (Identity Lock)

Voice cloning is done **offline** by the administrator. Place immutable `.safetensors` (or `.wav` reference clips) here.

Run on Mac mini:

```bash
uv run --project integrations/sensory-node python integrations/sensory-node/scripts/prepare_voice.py \
  --voice-id tenant_voice_alpha \
  --ref-audio /path/to/ref.wav \
  --ref-text "Transcripción exacta del clip de 5 segundos."
```

`manifest.json` is intentionally empty in core. Add voice profiles through this offline
admin flow; do not commit production voice tensors or domain-specific defaults.

Do **not** commit PII or production voice tensors to git.
