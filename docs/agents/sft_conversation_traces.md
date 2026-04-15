# SFT & conversation traces (Gemma / MLX)

**Language:** this page mirrors the operational README under `packages/agents/train/` so it appears in the MkDocs site. Paths below are relative to **`packages/agents`** unless noted.

## Overview

Conversation turns with tools are appended as **JSONL** (one JSON object per line). The default training path is **SFT** (Supervised Fine-Tuning) with **mlx_lm** and **Gemma** models. After *role flattening*, only `user` / `assistant` roles are kept in the exported dataset. **GRPO** remains available via legacy flows documented in the repo.

## Environment (gateway / workers)

Controlled from the API Gateway and graph code:

| Variable | Role |
|----------|------|
| `DUCKCLAW_SAVE_CONVERSATION_TRACES` | `true` / `1` / `yes` (default) enables writing traces; set `false` to disable. |
| `DUCKCLAW_CONVERSATION_TRACES_DIR` | Root directory for the trace lake (default: `train/conversation_traces` under the agents package). |
| `DUCKCLAW_CONVERSATION_TRACES_FORMAT` | `sft` or `grpo` (see `duckclaw.graphs.conversation_traces`). |

Typical files:

- `train/conversation_traces/YYYY/MM/DD/traces.jsonl`

**Operations cheat sheet:** [Commands (COMANDOS)](../COMANDOS.md) §5.3.

## SFT pipeline (default)

### 1. Collect traces

Production or dev runs write JSONL as above.

### 2. Build Gemma SFT dataset (`train/gemma4/`)

```python
from duckclaw.forge.sft import collect_traces_to_sft

# Scans *.jsonl under conversation_traces/; only status == "SUCCESS"
# Writes train/gemma4/dataset_sft.jsonl (overwrites if present)
records, stats = collect_traces_to_sft()
print(stats)
# files_scanned, lines_read, total_output, skipped_non_success, skipped_sql, skipped_malformed
```

Optional kwargs: `traces_root`, `output_path`, `require_valid_sql` (default `True`), `datamasker`.

### 3. Train with MLX

From **`packages/agents`**:

```bash
# Requires: pip install "mlx-lm[train]"
python train/train_sft.py
```

Useful env vars: `SFT_DATASET_PATH` (default `train/gemma4/dataset_sft.jsonl`), `SFT_ADAPTERS_PATH` (default `train/gemma4/adapters`), `MLX_MODEL_PATH` (e.g. a Gemma MLX repo id), `SFT_LORA_LAYERS` (default `42`).

Outputs:

- **LoRA:** `train/gemma4/adapters/`
- **mlx_lm staging:** `train/gemma4/sft_data_dir/` (`train.jsonl` / `test.jsonl`, regenerated each run)

### 4. Model-Guard and hot-swap

`scripts/mlx_hotswap.sh` runs **Model-Guard** (`scripts/eval_model.py`) against `golden_dataset.jsonl` (SQL validity). If accuracy ≥ 95%, hot-swap proceeds; otherwise it aborts and can alert via Telegram.

```bash
./scripts/mlx_hotswap.sh
```

Manual eval (with DuckDB for LogicScore):

```bash
python scripts/eval_model.py --model train/model_finetuned --db-path olist.duckdb
```

## Trace record shape

Each JSONL line includes at least:

- **`messages`**: ChatML / OpenAI-style (`system`, `user`, `assistant`, `tool`).
- **`status`**: `SUCCESS` | `FAILED` | … — only **`SUCCESS`** is exported to SFT by default.
- **`session_id`**, **`timestamp`**, **`worker_id`**, etc.

The collector applies **Gemma role flattening** (no `system` / `tool` in the final training messages). See the repo spec *Formateo de Datasets (SFT & GRPO)*.

## GRPO (alternative)

For GRPO / Unsloth-style multi-completion flows, use historical `grpo_*` assets (e.g. `grpo_olist_groups.jsonl`) as documented in the repo.

## Legacy BI trace API

```python
from duckclaw.bi.grpo_traces import save_grpo_trace, load_grpo_traces, trace_stats

save_grpo_trace("¿Cuál es el tiempo de entrega?", "<thought>...</thought>...", provider="mlx")
traces = load_grpo_traces(limit=100)
print(trace_stats())
```

## LangSmith

1. `.env`: `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`
2. In supported flows: `save_traces=True`, `send_to_langsmith=True`

## File reference

| Path | Description |
|------|-------------|
| `train/conversation_traces/YYYY/MM/DD/traces.jsonl` | Trace lake input |
| `train/gemma4/dataset_sft.jsonl` | Default SFT dataset (`{"messages":[...]}` per line); overwritten on rebuild |
| `train/gemma4/adapters/` | LoRA weights after `train_sft.py` |
| `train/gemma4/sft_data_dir/` | Temporary copy for `mlx_lm.lora` |
| `grpo_olist_traces.jsonl` / `grpo_olist_rewarded.jsonl` | Legacy GRPO / BI |
| `train/model_finetuned/` | Fused model after `mlx_hotswap.sh` |
| `golden_dataset.jsonl` | Golden set for Model-Guard |

## Related

- [COMANDOS §5.3](../COMANDOS.md) — Spanish runbook for the same env vars
- [VLM Integration](../specs/vlm_integration.md) — vision context that feeds user turns
- [Specs index](../specs/index.md) — canonical feature specs in `specs/features/`
