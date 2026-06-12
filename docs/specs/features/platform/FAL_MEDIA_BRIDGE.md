# Fal.ai Media Bridge

## Objetivo

Generacion multimedia cloud (Flux, Kling, ComfyUI serverless) via Fal.ai, con **prioridad Fal sobre ComfyUI local** cuando `FAL_KEY` esta configurada. El agente optimiza prompts; el harness despacha HTTPS con `FAL_KEY` inyectada y registra costos en `media_usage_log`.

## Variables de entorno

| Variable | Descripcion |
|----------|-------------|
| `FAL_KEY` | API key Fal.ai (zero-trust; nunca en args del LLM) |
| `DUCKCLAW_MEDIA_DAILY_BUDGET_USD` | Tope diario por tenant (default `2.0`) |
| `DUCKCLAW_MEDIA_KLING_USD_PER_SEC` | Costo estimado video/s (default `0.07`) |
| `FAL_POLL_TIMEOUT_SEC` | Timeout poll imagen (default `120`) |
| `FAL_POLL_TIMEOUT_VIDEO_SEC` | Timeout poll video (default `300`) |

## Comando `/comfyui`

```
/comfyui --provider local   # ComfyUI en Mac mini (COMFYUI_API_URL)
/comfyui --provider fal     # Fal.ai cloud (FAL_KEY)
/comfyui                    # estado actual
```

Persistencia por chat en `agent_config` (`comfyui_provider`).

## Manifest

```yaml
fal:
  enabled: true
  token_env: FAL_KEY
  default_image_endpoint: fal-ai/flux/dev
  default_image_edit_endpoint: fal-ai/flux-pro/kontext
  default_video_endpoint: fal-ai/kling-video/v1.6/standard/text-to-video
  comfy_endpoint: fal-ai/comfy
comfyui:
  enabled: true
  edit_template: comfy_img2img_edit
```

## Skills

| Tool | Descripcion |
|------|-------------|
| `generate_flux_image` | Imagen Flux Dev/Pro via queue.fal.run |
| `edit_visual_asset` | FLUX Kontext [pro] (`fal-ai/flux-pro/kontext`); fallback ComfyUI local si Fal falla |
| `generate_kling_video` | Video Kling/Wan con polling largo |
| `execute_comfy_workflow` | workflow_api.json serverless en Fal |

## Edicion img2img (FLUX Kontext)

1. Telegram foto + caption → gateway guarda en `inbound/` y fuerza `edit_visual_asset`.
2. Fal Kontext [pro]: imagen local como data URI en `image_url`; prompt enriquecido para preservar persona/escena; `guidance_scale` 3.5 (configurable via `kontext_guidance_scale` en manifest).
3. Legacy `fal-ai/flux/dev/image-to-image` sigue soportado si se configura en `default_image_edit_endpoint` (`strength` desde `denoise`).
4. Si Fal falla (timeout, presupuesto, API) y `COMFYUI_API_URL` + `comfyui.enabled`, reintento automatico con ComfyUI `comfy_img2img_edit`.

## Circuit breaker

Pre-call: `assert_media_budget_ok()` suma `media_usage_log` del dia y rechaza si supera el tope.
Post-call: `append_media_usage_log()` con costo estimado y latencia.

## StateDelta

Misma cola `duckclaw:state_delta:visual` y tabla `main.visual_assets` que ComfyUI local.