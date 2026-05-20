# Admin Gen — Image (ComfyUI)

## Objetivo

Exponer generación de imágenes ComfyUI desde **duckclaw-admin** (pestaña **Gen → Image**) y operar el servicio local vía **PM2** (`ComfyUI`), reutilizando el bridge existente (`COMFYUI_VISUAL_BRIDGE.md`).

## Rutas UI

| Ruta | Descripción |
|------|-------------|
| `/gen` | Redirect a `/gen/image` |
| `/gen/image` | Formulario de generación, health ComfyUI, ops PM2 |

Navegación: grupo colapsable **Gen** en sidebar (`adminNav.ts`).

## API Admin (Gateway)

Prefijo: `/api/v1/admin/comfyui`

| Método | Path | Descripción |
|--------|------|-------------|
| GET | `/status` | Health contra `COMFYUI_API_URL` (`/system_stats`) |
| GET | `/templates` | Lista workflows API (`comfy_default`, …) |
| POST | `/generate` | Genera imagen vía `_generate_visual_asset_impl` |

Auth: `X-Admin-Key` (igual que resto admin).

### POST `/generate` body

```json
{
  "prompt": "string (required)",
  "negative_prompt": "",
  "aspect_ratio": "1:1",
  "template": "comfy_default",
  "tenant_id": "default"
}
```

Respuesta: mismo JSON que la tool (`ok`, `file_path`, `figure_base64`, `prompt_id`, `error`).

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `COMFYUI_API_URL` | Base HTTP (default `http://127.0.0.1:8188`) |
| `COMFYUI_TIMEOUT_SEC` | Timeout generación (default `300`) |
| `COMFYUI_HOME` | Ruta instalación ComfyUI (default `~/ComfyUI`) — solo PM2 |

## PM2

```bash
pm2 start config/ecosystem.comfyui.config.cjs --update-env
pm2 restart ComfyUI --update-env
pm2 restart DuckClaw-Gateway --update-env
```

Proceso: `ComfyUI`. Script: `scripts/start_comfyui.sh`.

Ops admin: `pm2_start_comfyui`, `pm2_restart_comfyui`, `pm2_logs_comfyui`.

## Criterios de aceptación

1. `pm2 list` muestra `ComfyUI` online tras `pm2 start`.
2. `GET /api/v1/admin/comfyui/status` → `ok: true` con ComfyUI arriba.
3. Admin **Gen → Image**: pill verde, generación con preview.
4. Artefacto bajo `db/private/{tenant_id}/artifacts/`.

## Código

| Componente | Ruta |
|------------|------|
| Spec bridge | `specs/features/platform/COMFYUI_VISUAL_BRIDGE.md` |
| Bridge | `packages/agents/src/duckclaw/forge/skills/comfyui_bridge.py` |
| Gateway routes | `services/api-gateway/routers/admin.py` |
| Admin UI | `apps/duckclaw-admin/src/app/(admin)/gen/image/page.tsx` |
| PM2 | `config/ecosystem.comfyui.config.cjs`, `scripts/start_comfyui.sh` |
