#!/usr/bin/env python3
"""
MLX SFT Trainer — entrena con LoRA sobre dataset JSONL con clave \"messages\" (Gemma / mlx_lm).

Requisitos: pip install \"mlx-lm>=0.31.2\" (Gemma 4; extra opcional: pip install -e packages/agents[train])
Variables de entorno:
  SFT_DATASET_PATH   — default train/gemma4/dataset_sft.jsonl
  (Para SFT desde trazas ya sanitizadas a gemma4/**/traces.jsonl, no uses este flujo: ejecuta
   scripts/materialize_sft_data_dir_from_gemma4_sanitized.py y luego mlx/duckops con sft_data_dir.)
  SFT_ADAPTERS_PATH  — default train/gemma4/adapters
  MLX_MODEL_PATH     — ej. deadbydawn101/gemma-4-E4B-mlx-4bit
  SFT_LORA_LAYERS    — capas LoRA (default 42, Gemma 4 ~42 capas)
  SFT_VALID_FRACTION — fracción para valid.jsonl (default 0.1); con <2 líneas no se crea valid.
  SFT_VALID_SEED     — semilla del shuffle train/valid (default 42)
  MLX_PYTHON
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TRAIN_DIR = ROOT / "train"
GEMMA4_DIR = TRAIN_DIR / "gemma4"
DEFAULT_DATASET = GEMMA4_DIR / "dataset_sft.jsonl"
DEFAULT_ADAPTERS = GEMMA4_DIR / "adapters"
DEFAULT_MODEL = os.environ.get(
    "MLX_MODEL_PATH",
    "deadbydawn101/gemma-4-E4B-mlx-4bit",
)
DEFAULT_LORA_LAYERS = os.environ.get("SFT_LORA_LAYERS", "42")


def _curate_messages_row(trace: dict) -> dict | None:
    messages = trace.get("messages")
    if not isinstance(messages, list) or len(messages) < 2:
        return None
    return {"messages": messages}


def main() -> int:
    dataset_path = Path(os.environ.get("SFT_DATASET_PATH", str(DEFAULT_DATASET)))
    adapters_path = Path(os.environ.get("SFT_ADAPTERS_PATH", str(DEFAULT_ADAPTERS)))
    model_path = os.environ.get("MLX_MODEL_PATH", DEFAULT_MODEL)
    lora_layers = os.environ.get("SFT_LORA_LAYERS", DEFAULT_LORA_LAYERS)

    if not dataset_path.exists():
        print(f"Error: dataset no encontrado: {dataset_path}", file=sys.stderr)
        print(
            "Genera o copia un dataset JSONL compatible antes de ejecutar este trainer.",
            file=sys.stderr,
        )
        return 1

    val_fraction = float(os.environ.get("SFT_VALID_FRACTION", "0.1"))
    val_seed = int(os.environ.get("SFT_VALID_SEED", "42"))
    train_ratio = max(0.0, min(1.0, 1.0 - val_fraction))

    data_dir = GEMMA4_DIR / "sft_data_dir"

    from duckclaw.train.mlx_sft import MlxSFT

    sft = (
        MlxSFT(str(dataset_path))
        .load_traces(status_filter=None)
        .curate(_curate_messages_row)
        .split_and_save(str(data_dir), train_ratio=train_ratio, seed=val_seed)
    )

    num_lines = len(sft.curated_traces)
    train_lines = sum(1 for _ in open(data_dir / "train.jsonl", encoding="utf-8") if _.strip())
    valid_path = data_dir / "valid.jsonl"
    valid_lines = sum(1 for _ in open(valid_path, encoding="utf-8") if _.strip()) if valid_path.is_file() else 0

    if os.environ.get("SFT_SKIP_MLX", "").lower() in ("1", "true", "yes"):
        print(
            f"Materializado {data_dir} (train/valid/test). "
            f"Train: {train_lines} líneas, valid: {valid_lines}. "
            "Sin ejecutar mlx (SFT_SKIP_MLX).",
            flush=True,
        )
        return 0

    iters = max(10, num_lines)
    print(
        f"Ejecutando MlxSFT.run_train (model={model_path}, data={data_dir}, iters={iters})",
        flush=True,
    )
    try:
        sft.run_train(
            base_model=model_path,
            adapters_path=str(adapters_path),
            iterations=iters,
            batch_size=1,
            lora_layers=str(lora_layers),
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
