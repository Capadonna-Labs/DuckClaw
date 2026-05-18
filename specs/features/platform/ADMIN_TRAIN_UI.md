# Admin UI — Train (SFT / GRPO / trazas)

## Objetivo

Pestaña **Train** en `apps/duckclaw-admin` para operar el pipeline documentado en `packages/agents/train/SFT_MLX_PIPELINE.md` sin shell manual.

## API (`/api/v1/admin/train/*`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/status` | Rutas, conteos, pasos del pipeline, formato `sft`/`grpo` |
| GET | `/traces/sample` | Muestra líneas JSONL (`lake=conversation_traces\|gemma4`) |
| POST | `/pipeline/collect` | `collect_traces_to_sft` → `gemma4/dataset_sft.jsonl` |
| POST | `/pipeline/sanitize` | `scripts/sanitize_traces_for_gemma.py` |
| POST | `/pipeline/materialize` | `scripts/materialize_sft_data_dir_from_gemma4_sanitized.py` |
| POST | `/pipeline/run` | `duckops train -c config/lora_config.yaml` o `train_sft.py` |

Auth: `X-Admin-Key` (igual que el resto del admin).

## UI

- Ruta `/train` (redirect `/traces` → `/train`).
- Secciones: estado del pipeline, acciones SFT, explorador de trazas, historial Redis (legacy), referencia GRPO.

## Seguridad

- Lectura de archivos solo bajo `packages/agents/train/conversation_traces` y `packages/agents/train/gemma4`.
- Sin path traversal (`..` rechazado).
