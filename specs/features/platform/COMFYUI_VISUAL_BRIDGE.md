# ComfyUI Visual Bridge

## Objetivo

Integrar ComfyUI como motor de generación de imágenes para workers DuckClaw. El agente invoca `generate_visual_asset` con prompts del LLM; el bridge encola workflows JSON, espera la ejecución y persiste el artefacto en la bóveda del tenant.

## Variables de entorno

| Variable | Descripción |
|----------|-------------|
| `COMFYUI_API_URL` | Base HTTP (default `http://127.0.0.1:8188`). Sin valor → la skill no se registra. |
| `COMFYUI_TIMEOUT_SEC` | Timeout total de generación (default `300`). |
| `COMFYUI_SAMPLER_STEPS` | Pasos del KSampler (opcional; default del workflow `20`). En Mac MPS, `12` reduce ~40% el tiempo. |
| `DUCKCLAW_VISUAL_STATE_DELTA_QUEUE` | Cola Redis (default `duckclaw:state_delta:visual`). |

## Manifest del worker

```yaml
comfyui:
  enabled: true
  template: comfy_default
```

También válido bajo `skills: [{ comfyui: { enabled: true } }]`.

## Workflow templates

- Directorio: `packages/agents/src/duckclaw/forge/templates/workflows/`
- Formato: **API** (Save API Format en ComfyUI), no formato UI.
- Metadatos: `{template}.meta.json` con IDs de nodos CLIP y presets de aspect ratio.
- Re-exportar ambos archivos si el grafo cambia en ComfyUI.

## Skill `generate_visual_asset`

| Parámetro | Tipo | Descripción |
|-----------|------|-------------|
| `prompt` | str | Texto positivo (CLIPTextEncode) |
| `negative_prompt` | str | Texto negativo (opcional) |
| `aspect_ratio` | str | `1:1`, `16:9`, `9:16` (otros según meta) |

### Flujo

1. Cargar template + meta.
2. Inyectar prompts en nodos `CLIPTextEncode`.
3. Ajustar `EmptyLatentImage` según aspect ratio.
4. `POST /prompt` → `prompt_id`.
5. WebSocket `/ws?clientId={uuid}` hasta `executing` con `node=null` (fin de ejecución).
6. `GET /history/{prompt_id}` → filename SaveImage.
7. `GET /view?filename=...` → guardar en `db/private/{tenant_id}/artifacts/{uuid}.png`.
8. `LPUSH` StateDelta `VISUAL_ASSET_UPSERT`.
9. Retornar JSON con `file_path`, `artifacts`, `figure_base64` (si tamaño &lt; umbral).

## StateDelta

```json
{
  "tenant_id": "...",
  "user_id": "...",
  "target_db_path": "...",
  "delta_type": "VISUAL_ASSET_UPSERT",
  "mutation": {
    "id": "uuid",
    "prompt": "...",
    "negative_prompt": "...",
    "file_path": "...",
    "aspect_ratio": "16:9",
    "prompt_id_comfy": "..."
  }
}
```

Cola: `duckclaw:state_delta:visual`. Consumidor: `services/db-writer/visual_state_delta_handler.py`.

**`target_db_path`:** hub del gateway (`get_gateway_db_path()`, p. ej. `finanzdb1.duckdb`), no la bóveda del worker activo. El worker suele mantener un handle DuckDB abierto en su vault durante ComfyUI; escribir `visual_assets` en el mismo `.duckdb` compite con el singleton db-writer (lock). Los PNG siguen en `db/private/{tenant_id}/artifacts/`.

## Esquema DuckDB

```sql
CREATE TABLE IF NOT EXISTS main.visual_assets (
  id VARCHAR PRIMARY KEY,
  prompt TEXT NOT NULL,
  negative_prompt VARCHAR DEFAULT '',
  file_path VARCHAR NOT NULL,
  aspect_ratio VARCHAR DEFAULT '1:1',
  prompt_id_comfy VARCHAR DEFAULT '',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

Solo el db-writer escribe (`read_only=False` en el vault activo).

## Egress Telegram

- La tool devuelve `figure_base64` y/o `artifacts`.
- `factory.tools_node` propaga a `sandbox_photo_base64` (mismo canal que sandbox).
- Gateway: `sendPhoto` con fallback `sendDocument`; soporte PNG/JPEG/WebP.

No se parsean rutas en el texto libre del LLM (v1).

## Discord (fase 2)

Contrato reservado: `outbound_image_paths: list[str]` en estado del grafo. Sin upload multipart en v1.

## Edición de fotos (img2img)

Ver [COMFYUI_IMAGE_EDIT.md](COMFYUI_IMAGE_EDIT.md): foto Telegram + caption → `edit_visual_asset` sin MLX-Vision.

## Código

| Componente | Ruta |
|------------|------|
| Bridge | `packages/agents/src/duckclaw/forge/skills/comfyui_bridge.py` |
| Producer StateDelta | `packages/agents/src/duckclaw/forge/skills/visual_state_delta.py` |
| Templates | `packages/agents/src/duckclaw/forge/templates/workflows/` |
| Handler writer | `services/db-writer/visual_state_delta_handler.py` |
