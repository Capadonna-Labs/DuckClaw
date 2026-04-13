#!/usr/bin/env python3
"""
MLX SFT Trainer — entrena con LoRA sobre dataset JSONL con clave \"messages\" (Gemma / mlx_lm).

Requisitos: pip install \"mlx-lm>=0.31.2\" (Gemma 4; extra opcional: pip install -e packages/agents[train])
Variables de entorno:
  SFT_DATASET_PATH   — default train/gemma4/dataset_sft.jsonl
  SFT_ADAPTERS_PATH  — default train/gemma4/adapters
  MLX_MODEL_PATH     — ej. deadbydawn101/gemma-4-E4B-mlx-4bit
  SFT_LORA_LAYERS    — capas LoRA (default 42, Gemma 4 ~42 capas)
  SFT_VALID_FRACTION — fracción para valid.jsonl (default 0.1); con <2 líneas no se crea valid.
  SFT_VALID_SEED     — semilla del shuffle train/valid (default 42)
  MLX_PYTHON
"""

from __future__ import annotations

import json
import os
import random
import subprocess
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


def _split_train_valid_lines(
    lines: list[str],
    val_fraction: float,
    seed: int,
) -> tuple[list[str], list[str]]:
    """Parte líneas JSONL en train y valid (estratificado por shuffle). valid vacío si hay <2 líneas."""
    n = len(lines)
    if n < 2:
        return lines, []
    rng = random.Random(seed)
    shuffled = lines.copy()
    rng.shuffle(shuffled)
    n_val = max(1, int(n * val_fraction))
    n_val = min(n_val, n - 1)
    valid_lines = shuffled[:n_val]
    train_lines = shuffled[n_val:]
    return train_lines, valid_lines


def main() -> int:
    dataset_path = Path(os.environ.get("SFT_DATASET_PATH", str(DEFAULT_DATASET)))
    adapters_path = Path(os.environ.get("SFT_ADAPTERS_PATH", str(DEFAULT_ADAPTERS)))
    model_path = os.environ.get("MLX_MODEL_PATH", DEFAULT_MODEL)
    python_path = os.environ.get("MLX_PYTHON", sys.executable)
    lora_layers = os.environ.get("SFT_LORA_LAYERS", DEFAULT_LORA_LAYERS)

    if not dataset_path.exists():
        print(f"Error: dataset no encontrado: {dataset_path}", file=sys.stderr)
        print(
            "Ejecuta primero: python -c \"from duckclaw.forge.sft import collect_traces_to_sft; collect_traces_to_sft()\"",
            file=sys.stderr,
        )
        return 1

    val_fraction = float(os.environ.get("SFT_VALID_FRACTION", "0.1"))
    val_seed = int(os.environ.get("SFT_VALID_SEED", "42"))

    data_dir = GEMMA4_DIR / "sft_data_dir"
    data_dir.mkdir(parents=True, exist_ok=True)
    train_jsonl = data_dir / "train.jsonl"
    valid_jsonl = data_dir / "valid.jsonl"

    with open(dataset_path, encoding="utf-8") as f:
        all_lines = [line for line in f if line.strip()]

    train_lines, valid_lines = _split_train_valid_lines(all_lines, val_fraction, val_seed)
    train_jsonl.write_text("".join(train_lines), encoding="utf-8")
    if valid_lines:
        valid_jsonl.write_text("".join(valid_lines), encoding="utf-8")
    elif valid_jsonl.exists():
        valid_jsonl.unlink()

    test_jsonl = data_dir / "test.jsonl"
    with open(test_jsonl, "w", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "messages": [
                        {"role": "user", "content": "ok"},
                        {"role": "assistant", "content": "ok"},
                    ]
                },
                ensure_ascii=False,
            )
            + "\n"
        )

    num_lines = len(all_lines)
    iters = max(10, num_lines)

    adapters_path.mkdir(parents=True, exist_ok=True)

    if os.environ.get("SFT_SKIP_MLX", "").lower() in ("1", "true", "yes"):
        print(
            f"Materializado {data_dir} (train/valid/test). "
            f"Train: {len(train_lines)} líneas, valid: {len(valid_lines)}. "
            "Sin ejecutar mlx (SFT_SKIP_MLX).",
            flush=True,
        )
        return 0

    cmd = [
        python_path,
        "-m",
        "mlx_lm",
        "lora",
        "--model",
        model_path,
        "--train",
        "--data",
        str(data_dir),
        "--iters",
        str(iters),
        "--batch-size",
        "1",
        "--learning-rate",
        "2e-5",
        "--num-layers",
        str(lora_layers),
        "--adapter-path",
        str(adapters_path),
    ]
    print("Ejecutando:", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(ROOT))
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
