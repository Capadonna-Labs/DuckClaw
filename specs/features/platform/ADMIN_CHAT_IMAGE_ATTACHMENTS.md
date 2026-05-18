# Admin UI — Adjuntos de imagen en chat (Playground y flotante)

## Objetivo

Permitir adjuntar imágenes en el Playground y en el chat flotante (`AdminChatPanel`), con el mismo enriquecimiento VLM que Telegram Guard.

## Formatos y límites

| Regla | Valor |
|-------|--------|
| MIME | `image/jpeg`, `image/png`, `image/webp` |
| Tamaño máx. por imagen | `DUCKCLAW_VLM_MAX_IMAGE_BYTES` (default 12 MB) |
| Imágenes por mensaje | 3 |

## Flujo

1. El cliente envía `POST /api/v1/admin/playground/chat` con `message` (opcional) e `images[]` (`mime_type`, `data_base64`).
2. El gateway decodifica, valida y ejecuta VLM (`core/vlm_ingest.enrich_message_with_admin_images`).
3. El texto enviado al worker incluye bloques `Contexto visual adjunto: …` y `[VLM_CONTEXT …]`.
4. El historial Redis guarda solo el texto enriquecido (no binarios).

## API

Extensión de `PlaygroundChatBody`:

```json
{
  "worker_id": "default",
  "message": "¿Qué ves?",
  "chat_id": "admin-conv-…",
  "images": [
    { "mime_type": "image/png", "data_base64": "…" }
  ],
  "stream": true
}
```

- `message` puede estar vacío si hay al menos una imagen.
- Sin `message` ni `images` → 400.

## UI

- Botón adjuntar en footer de `AdminChatPanel` (Playground + burbuja flotante).
- Miniaturas antes de enviar y en burbuja de usuario (`imagePreviews`).
- Validación cliente alineada con límites del gateway.

## Fuera de alcance v1

- PDF, video, drag-and-drop, paste desde portapapeles.
- Persistencia de binarios en Redis.
- Visión nativa multimodal sin VLM.
