# Trazas para entrenamiento (SFT Gemma / MLX por defecto)

Este directorio almacena trazas en formato JSONL. El **pipeline por defecto** es **SFT** (Supervised Fine-Tuning) con **mlx_lm** y modelos **Gemma** (solo roles `user` / `assistant` en el dataset tras *role flattening*). GRPO (Group Relative Policy Optimization) sigue disponible como alternativa documentada en otras rutas.

## Pipeline SFT (por defecto)

### 1. Guardar trazas (Gateway / workers)

Las conversaciones con herramientas se guardan en el datalake:

- **`conversation_traces/YYYY/MM/DD/traces.jsonl`** — una línea por turno con `messages`, `status`, `session_id`, etc.
- Raíz configurable: `DUCKCLAW_CONVERSATION_TRACES_DIR` (por defecto: `train/conversation_traces`).

### 2. Generar dataset SFT Gemma (`train/gemma4/`)

```python
from duckclaw.forge.sft import collect_traces_to_sft

# Lee todos los *.jsonl bajo conversation_traces/, solo status == "SUCCESS"
# Escribe train/gemma4/dataset_sft.jsonl (sobrescribe si ya existe)
records, stats = collect_traces_to_sft()
print(stats)
# files_scanned, lines_read, total_output, skipped_non_success, skipped_sql, skipped_malformed
```

Parámetros opciones: `traces_root`, `output_path`, `require_valid_sql` (default True), `datamasker`.

### 3. Entrenar con MLX

Desde la raíz de `packages/agents`:

```bash
# Requiere: pip install "mlx-lm[train]"
python train/train_sft.py
```

Variables útiles: `SFT_DATASET_PATH` (default `train/gemma4/dataset_sft.jsonl`), `SFT_ADAPTERS_PATH` (default `train/gemma4/adapters`), `MLX_MODEL_PATH` (ej. `deadbydawn101/gemma-4-E4B-mlx-4bit`), `SFT_LORA_LAYERS` (default `42`).

Salida LoRA: **`train/gemma4/adapters/`**. Los datos de entrenamiento copiados para mlx_lm viven en **`train/gemma4/sft_data_dir/`** (`train.jsonl` / `test.jsonl`; se regeneran en cada ejecución).

### 4. Model-Guard y Hot-Swap

Antes del hot-swap, `mlx_hotswap.sh` ejecuta **Model-Guard** (`scripts/eval_model.py`): evalúa el modelo contra `golden_dataset.jsonl` (Accuracy: SQL válido). Si accuracy >= 95%, procede con el hot-swap; si no, aborta y alerta por Telegram.

```bash
./scripts/mlx_hotswap.sh
```

Evaluación manual (con DuckDB para LogicScore):

```bash
python scripts/eval_model.py --model train/model_finetuned --db-path olist.duckdb
```

---

## Pipeline GRPO (alternativa)

Para entrenamiento GRPO con Unsloth u otros frameworks que requieren múltiples completions por prompt, usar flujos y archivos `grpo_*` documentados históricamente (p. ej. `grpo_olist_groups.jsonl`).

---

## Formato de trazas (conversation_traces)

Cada línea es un objeto JSON con al menos:

- **`messages`**: historial ChatML / OpenAI (`system`, `user`, `assistant`, `tool`).
- **`status`**: `SUCCESS` | `FAILED` | … (solo `SUCCESS` entra al dataset SFT).
- **`session_id`**, **`timestamp`**, **`worker_id`**, etc.

El collector aplica **role flattening para Gemma**: sin `system` ni `tool` en la salida; ver spec *Formateo de Datasets (SFT & GRPO)*.

## API directa (legacy BI / GRPO)

```python
from duckclaw.bi.grpo_traces import save_grpo_trace, load_grpo_traces, trace_stats

save_grpo_trace("¿Cuál es el tiempo de entrega?", "<thought>...</thought>...", provider="mlx")
traces = load_grpo_traces(limit=100)
print(trace_stats())
```

## LangSmith

Para enviar trazas a [LangSmith](https://smith.langchain.com/):

1. Crea `.env` con `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`
2. `save_traces=True, send_to_langsmith=True` en flujos que lo soporten

## Archivos

| Ruta | Descripción |
|------|-------------|
| **`conversation_traces/YYYY/MM/DD/traces.jsonl`** | Datalake de conversaciones (entrada del collector). |
| **`gemma4/dataset_sft.jsonl`** | Dataset SFT por defecto (`{"messages":[...]}` por línea). Se **sobrescribe** al regenerar. |
| **`gemma4/adapters/`** | Pesos LoRA tras `train/train_sft.py`. |
| **`gemma4/sft_data_dir/`** | Copia temporal para `mlx_lm.lora` (`train.jsonl` / `test.jsonl`). |
| `grpo_olist_traces.jsonl` / `grpo_olist_rewarded.jsonl` | Flujos legacy GRPO / BI. |
| `model_finetuned/` | Modelo fusionado tras `scripts/mlx_hotswap.sh`. |
| **`golden_dataset.jsonl`** | Golden dataset para Model-Guard. |
