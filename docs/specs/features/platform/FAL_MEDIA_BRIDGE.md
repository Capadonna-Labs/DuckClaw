# Fal.ai Media Bridge

## Objetivo

Generacion multimedia cloud (Flux, Kling, ComfyUI serverless) via Fal.ai, complementando ComfyUI local en Mac mini. El agente optimiza prompts; el harness despacha HTTPS con `FAL_KEY` inyectada y registra costos en `media_usage_log`.

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
  default_video_endpoint: fal-ai/kling-video/v1.6/standard/text-to-video
  comfy_endpoint: fal-ai/comfy
comfyui:
  enabled: true
```

## Skills

| Tool | Descripcion |
|------|-------------|
| `generate_flux_image` | Imagen Flux Dev/Pro via queue.fal.run |
| `generate_kling_video` | Video Kling/Wan con polling largo |
| `execute_comfy_workflow` | workflow_api.json serverless en Fal |

## Circuit breaker

Pre-call: `assert_media_budget_ok()` suma `media_usage_log` del dia y rechaza si supera el tope.
Post-call: `append_media_usage_log()` con costo estimado y latencia.

## StateDelta

Misma cola `duckclaw:state_delta:visual` y tabla `main.visual_assets` que ComfyUI local.