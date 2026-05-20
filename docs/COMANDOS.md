# COMANDOS · DuckClaw

```bash
pm2 start config/ecosystem.db-writer.config.cjs
pm2 start config/ecosystem.api.config.cjs --only DuckClaw-Gateway
pm2 start config/ecosystem.mcp.config.cjs
pm2 start config/ecosystem.mlx-vision.config.cjs
pm2 save
pm2 list
```

## Utilidad

```bash
uv run duckops init                              # Reconfig / instalar
uv run python scripts/doctor.py                  # Diagnóstico local
uv run duckops serve --gateway                   # Dev sin PM2
uv run duckops serve --pm2 --gateway             # Regenera ecosystem.api + PM2

# Regenerar gateway JSON/CJS sin secretos (un solo DuckClaw-Gateway)
uv run python -c "from pathlib import Path; from duckops.sovereign.pm2_dotenv_sync import sync_gateway_pm2_from_dotenv; sync_gateway_pm2_from_dotenv(Path('.').resolve(), single_gateway=True)"

pm2 status
pm2 flush                                        # Limpia la consola
pm2 logs DuckClaw-Gateway
pm2 logs DuckClaw-DB-Writer
pm2 logs DuckClaw-MCP
pm2 logs MLX-Vision
pm2 restart DuckClaw-Gateway --update-env        # Tras cambiar .env
pm2 restart all --update-env

# MLX texto local (opcional)
pm2 start config/ecosystem.mlx.config.cjs
```

## TELEGRAM

Webhook (`DUCKCLAW_PUBLIC_URL` con `*.ts.net`) requiere **Tailscale activo** y **Funnel** al puerto del gateway:

```bash
tailscale up                                    # o abrir app Tailscale
tailscale funnel --bg 8000                      # mismo puerto que DUCKCLAW_GATEWAY_PORT
uv run python scripts/check_telegram_ingress.py # diagnóstico
uv run python scripts/register_webhooks.py      # re-registrar tras activar Funnel
```

```bash
/team                         # Verifica usuarios actuales
/team --add id_telegram admin # Agrega un usuairo con permiso 'admin' 
/team --add id_telegram       # Agrega usuario con permiso ' user ' 
/team --rm  id_telegram       # eliminar usuario

/workers                             # Muestra plantillas de trabajadores virtuales
Equipo: 
- cobranzas
- research_worker
- BI-Analyst
- gymbro
- powerseal
- PQRSD-Assistant
- SIATA-Analyst
- Quant-Trader
- finanz
- support
- AXIS
- default
- gitclaw
- Job-Hunter

/workers --add cobranzas
/workers --rm  cobranzas

/vault                        # Muestra la ruta del storage

/heartbeat on                 # Muestra el uso de tools 
/heartbeat off                # oculta el uso de tools

/context on
/context off
/context --summary 
/context --add Documentacion especifica 
```

## Admin UI (pnpm)

```bash
# Gateway con DUCKCLAW_ADMIN_API_KEY en .env raíz
pm2 restart DuckClaw-Gateway --update-env

cd apps/duckclaw-admin && pnpm install && pnpm dev
# o desde raíz: pnpm admin:dev
```

Variables en `apps/duckclaw-admin/.env.local`: `DUCKCLAW_GATEWAY_URL=http://127.0.0.1:8000`, `DUCKCLAW_ADMIN_API_KEY` (misma clave que el gateway). Ver `apps/duckclaw-admin/docs/environment.md`.

Servicios requeridos: Redis + DuckClaw-DB-Writer + DuckClaw-Gateway (+ MLX-Vision si usas VLM). Documentación: `apps/duckclaw-admin/README.md` · `apps/duckclaw-admin/docs/`.

## ComfyUI (generación visual)

**Instalación en esta Mac:** `~/ComfyUI` (repo [Comfy-Org/ComfyUI](https://github.com/Comfy-Org/ComfyUI), venv Python 3.12). UI: http://127.0.0.1:8188

```bash
# Arrancar con PM2 (recomendado)
pm2 start config/ecosystem.comfyui.config.cjs --update-env
pm2 restart ComfyUI --update-env
pm2 logs ComfyUI

# Manual
~/ComfyUI/start_comfyui.sh
```

**Checkpoint:** `v1-5-pruned-emaonly.safetensors` en `~/ComfyUI/models/checkpoints/` (descarga: `hf download runwayml/stable-diffusion-v1-5 v1-5-pruned-emaonly.safetensors --local-dir ~/ComfyUI/models/checkpoints`).

En `.env` raíz:

```bash
COMFYUI_API_URL=http://127.0.0.1:8188
COMFYUI_TIMEOUT_SEC=420
COMFYUI_IMG2IMG_DENOISE=0.55
# Edición foto+caption en Telegram sin MLX-Vision:
DUCKCLAW_COMFYUI_INBOUND_EDIT=1
# Cola StateDelta (opcional; default duckclaw:state_delta:visual)
# DUCKCLAW_VISUAL_STATE_DELTA_QUEUE=duckclaw:state_delta:visual
```

Habilitar en el manifest del worker:

```yaml
comfyui:
  enabled: true
  template: comfy_default
  edit_template: comfy_img2img_edit
```

**Edición (estilo Gemini, solo ComfyUI):** envía foto + caption con instrucciones (ej. *cambiar fondo, quitar lentes*). El gateway guarda la imagen en `db/private/{tenant}/inbound/` y el agente usa `edit_visual_asset` — **no** carga MLX-Vision en ese flujo.

Reiniciar gateway y db-writer tras cambiar `.env`. Specs: `COMFYUI_VISUAL_BRIDGE.md`, `COMFYUI_IMAGE_EDIT.md`.