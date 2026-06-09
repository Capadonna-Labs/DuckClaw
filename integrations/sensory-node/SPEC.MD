# Sensory Node — API contract

Edge inference microservice on Apple Silicon (Mac mini). Listens **only** on the Tailscale IP (`DUCKCLAW_SENSORY_BIND_HOST`, port `8001`).

## Endpoints

| Method | Path | Body | Response |
|--------|------|------|----------|
| POST | `/api/v1/sensory/transcribe` | `STTRequest` | `STTResponse` |
| POST | `/api/v1/sensory/synthesize` | `TTSRequest` | `TTSResponse` |
| GET | `/health` | — | VRAM + model load state |

## Identity Lock (anti-deepfake)

- TTS accepts only `voice_id` from `Literal["campus_legal_main", "leila_assistant", "finanz_alert"]`.
- **Forbidden** in any payload: `ref_audio`, `reference_audio`, `ref_text`, `ref_tokens`, `voice_embedding`.
- Voice tensors are prepared offline via `scripts/prepare_voice.py` and stored under `voices/`.

## Concurrency

`asyncio.Semaphore(2)` — max 2 concurrent tensor jobs (`DUCKCLAW_SENSORY_MAX_CONCURRENT`).

## STT edge cases

- Audio > 5 min: 30s chunking, concatenate text.
- Whisper: `condition_on_previous_text=False`, `compression_ratio_threshold=2.4`.
- No disk writes for inbound audio (memory only).

## TTS edge cases

- Sanitize markdown/emojis before synthesis.
- Timeout 2000 ms → HTTP 503 (gateway degrades to text-only).

## Network

- Bind: Tailscale IP only (not `0.0.0.0` / `127.0.0.1`).
- Middleware rejects clients outside `100.64.0.0/10` (except `/health`).

## Gateway proxy (VPS)

Con `DUCKCLAW_SENSORY_BASE_URL` configurado, el API Gateway expone los mismos paths:

- `GET /api/v1/sensory/health`
- `POST /api/v1/sensory/transcribe`
- `POST /api/v1/sensory/synthesize`

Implementación: `services/api-gateway/routers/sensory.py`. Admin UI: `apps/duckclaw-admin/.../integrations/sensory-node`.

Telegram (voz entrante / TTS saliente) se integrará en fase posterior.

### Laboratorio de voz (admin, sin Telegram)

`POST /api/v1/admin/playground/voice` — audio base64 → STT → agente → TTS opcional.

UI: Admin → Integraciones → Sensory node → **Laboratorio de voz**.

**Streaming:** STT y TTS son **batch** (clip completo). El texto del agente puede streamearse por SSE en `/api/v1/admin/playground/chat` con `stream=true`; el round-trip de voz actual espera la respuesta completa antes del TTS.

## Deploy Mac mini

```bash
# En el Mac (tras git pull con estos cambios):
cd ~/duckclaw   # o ~/Desktop/duckclaw
# .env:
#   DUCKCLAW_SENSORY_BIND_HOST=100.99.72.63
#   DUCKCLAW_SENSORY_PORT=8001
#   DUCKCLAW_MCP_PORT=8010
bash scripts/deployment/deploy_sensory_macmini.sh
```

Gateway (VPS o local) necesita `DUCKCLAW_SENSORY_BASE_URL=http://100.99.72.63:8001`.

## Deploy

```bash
pm2 start config/ecosystem.sensory.config.cjs
```

Move `DUCKCLAW_MCP_PORT` to `8010` if MCP shares the Mac (sensory uses 8001).
