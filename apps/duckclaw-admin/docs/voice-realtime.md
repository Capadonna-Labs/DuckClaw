# Voz en vivo (Pipecat) — Admin UI

Integración de **Voz en vivo** en el playground y la burbuja flotante vía Pipecat SmallWebRTC.

## Prerrequisitos

1. Gateway (`DuckClaw-Gateway`) activo.
2. Servicio de voz (`DuckClaw-Voice`) en PM2 con extras Pipecat instalados.
3. Variables en `.env` raíz duckclaw:

```env
DUCKCLAW_VOICE_ENABLED=true
DUCKCLAW_VOICE_BIND_HOST=127.0.0.1
DUCKCLAW_VOICE_PORT=8012
DUCKCLAW_VOICE_GATEWAY_URL=http://127.0.0.1:8000
DUCKCLAW_VOICE_GATEWAY_ADMIN_KEY=<mismo que DUCKCLAW_ADMIN_API_KEY>
DEEPGRAM_API_KEY=...
CARTESIA_API_KEY=...
DUCKCLAW_VOICE_INTERNAL_URL=http://127.0.0.1:8012
```

4. Admin BFF (`apps/duckclaw-admin/.env.local`):

```env
DUCKCLAW_VOICE_INTERNAL_URL=http://127.0.0.1:8012
```

## Smoke manual

1. Verificar `http://127.0.0.1:8012/health` → `{ "ok": true }`.
2. Abrir admin `:3001/playground` o la burbuja flotante.
3. Menú clip → **Voz en vivo** → permitir micrófono → hablar 2–3 turnos → **Colgar**.
4. El historial debe mostrar los turnos con el mismo `chat_id` en `conversation_traces`.
5. **Nota de voz** (Sensory batch) y **Voz automática** siguen operativos.

## Arquitectura

- Señalización WebRTC: BFF same-origin `/api/admin/playground/voice/realtime/offer`.
- Audio + RTVI (transcripciones, `app_state`, `update_state`): data channel WebRTC.
- Turnos del grafo: solo server-side (Pipecat → gateway `/admin/playground/chat`).

## HTTPS

`getUserMedia` requiere contexto seguro. En VPS sin TLS el mic puede fallar (igual que nota de voz batch).
