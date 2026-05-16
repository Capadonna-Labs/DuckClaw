# Generación de trazas sintéticas PQRSD (Gemma 4 / SFT)

## Objetivo

Documentar cómo generar líneas JSONL de entrenamiento **coherentes** con el worker Forge **`PQRSD-Assistant`** y con el formato ya usado en `packages/agents/train/conversation_traces/`.

## Fuente de verdad

- **Prompt generador (para LLM):** [`packages/agents/train/prompts/PQRSD_synthetic_traces_gemma4_prompt.md`](../../packages/agents/train/prompts/PQRSD_synthetic_traces_gemma4_prompt.md)
- **Herramientas reales:** `pqrsd_fetch_canonical`, `pqrsd_entity_routing`, `tavily_search`, `read_sql` (DuckDB solo lectura, tablas allow-list); `admin_sql` existe en el gateway para workers **no** `read_only`, no para **PQRSD-Assistant** (ver `factory.py`). Sandbox: `pqrsd_run_identificacion_step1` cuando aplique.
- **Prohibido** en datos sintéticos: herramientas ficticias de “clasificar y guardar” o números de radicado inventados como si el chat los hubiera creado.

## Salida

Archivos bajo `packages/agents/train/conversation_traces/YYYY/MM/DD/traces.jsonl`; pipeline SFT descrito en [`packages/agents/train/SFT_MLX_PIPELINE.md`](../../packages/agents/train/SFT_MLX_PIPELINE.md).
