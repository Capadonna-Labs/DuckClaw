# ComfyUI Image Edit (img2img, sin MLX-Vision)

## Objetivo

Edición de fotos enviadas por Telegram (foto + caption con instrucciones) usando **solo ComfyUI**, sin cargar MLX-Vision/Gemma en ese flujo.

Ejemplo de uso: *"Cambiar fondo, quitar lentes, colocar cabello corto y rubio"* sobre una foto del usuario.

## Relación con COMFYUI_VISUAL_BRIDGE

- **Generación** (txt2img): `generate_visual_asset` + `comfy_default.json`
- **Edición** (img2img): `edit_visual_asset` + `comfy_img2img_edit.json`

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `DUCKCLAW_COMFYUI_INBOUND_EDIT` | `1` / `true`: inbound Telegram foto+caption usa ruta ComfyUI (no VLM) |
| `COMFYUI_API_URL` | Base HTTP ComfyUI (default `http://127.0.0.1:8188`) |
| `COMFYUI_TIMEOUT_SEC` | Timeout generación/edición (default `300`) |
| `COMFYUI_IMG2IMG_DENOISE` | Denoise KSampler img2img (default `0.55`, rango típico 0.35–0.75) |

## Inbound Telegram (sin VLM)

Condiciones para bypass VLM:

1. `DUCKCLAW_COMFYUI_INBOUND_EDIT` activo
2. Mensaje con `photo` o `document` imagen + **caption no vacío**
3. Sin `media_group_id` (v1: un solo archivo; álbumes siguen VLM o se ignoran)

Flujo gateway:

1. `download_telegram_file_bytes` → [`telegram_media_download.py`](../../../services/api-gateway/core/telegram_media_download.py)
2. Guardar en `db/private/{tenant_id}/inbound/{uuid}.jpg`
3. Texto al Manager con bloque `[COMFYUI_EDIT source_image_path=...]`
4. Agente llama `edit_visual_asset(source_image_path, edit_prompt)`

MLX-Vision **no se desactiva globalmente**; solo se omite en esta rama.

## Skill `edit_visual_asset`

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `source_image_path` | str | Ruta absoluta bajo `inbound/` o `artifacts/` del tenant |
| `edit_prompt` | str | Instrucciones de edición (español) |
| `negative_prompt` | str | Negativo CLIP (opcional) |
| `denoise` | float | Fuerza de edición img2img (default env o 0.55) |

### Flujo bridge

1. Validar `source_image_path`
2. `POST /upload/image` → nombre en input ComfyUI
3. Cargar `comfy_img2img_edit` (+ meta)
4. Inyectar imagen, prompts, denoise
5. `POST /prompt` + WebSocket + `GET /history` + `GET /view`
6. Guardar salida en `artifacts/`
7. `VISUAL_ASSET_UPSERT` con `operation=img2img_edit`, `source_image_path`
8. Retorno JSON + `figure_base64` para Telegram

## Manifest

```yaml
comfyui:
  enabled: true
  template: comfy_default
  edit_template: comfy_img2img_edit
```

## Limitaciones v1

- **img2img global**: una pasada de difusión; no inpaint por zonas (lentes/pelo/fondo no garantizados).
- Requiere **checkpoint** en ComfyUI (`~/ComfyUI/models/checkpoints/`).
- v2 futuro: inpaint + máscaras, siempre sin MLX-Vision.

## Código

| Componente | Ruta |
|------------|------|
| Descarga Telegram | `services/api-gateway/core/telegram_media_download.py` |
| Inbound bypass | `services/api-gateway/routers/telegram_inbound_webhook.py` |
| Bridge | `packages/agents/.../forge/skills/comfyui_bridge.py` |
| Workflow | `packages/agents/.../forge/templates/workflows/comfy_img2img_edit.json` |
