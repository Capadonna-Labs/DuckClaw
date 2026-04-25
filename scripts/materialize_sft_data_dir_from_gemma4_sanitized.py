#!/usr/bin/env python3
"""
Agrega los `**/traces.jsonl` sanitizados bajo `packages/agents/train/gemma4/`
(excluye `sft_data_dir/`, `adapters*`, `deprecated/`) y escribe
`sft_data_dir/{train,valid,test}.jsonl` con clave `text` (mlx_lm TextDataset).

Ejecutar **después** de:
  uv run python scripts/sanitize_traces_for_gemma.py

Mismas variables que `train_sft.py` para el split:
  SFT_VALID_FRACTION (default 0.1), SFT_VALID_SEED (default 42)

Opcional:
  SFT_MATERIALIZE_DEDUP=1 — deduplica por contenido de `text` (primera ocurrencia gana).
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
from pathlib import Path


def _split_train_valid_lines(
    lines: list[str],
    val_fraction: float,
    seed: int,
) -> tuple[list[str], list[str]]:
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


def _should_skip_trace_file(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True
    for part in rel.parts:
        if part == "sft_data_dir" or part == "deprecated":
            return True
        if part.startswith("adapters"):
            return True
    return False


def _collect_text_lines(gemma4_root: Path) -> tuple[list[str], int, int]:
    """Returns (jsonl_lines, files_read, lines_skipped)."""
    out_lines: list[str] = []
    files_read = 0
    lines_skipped = 0
    dedup = os.environ.get("SFT_MATERIALIZE_DEDUP", "").lower() in (
        "1",
        "true",
        "yes",
    )
    seen: set[str] = set()

    for fp in sorted(gemma4_root.rglob("traces.jsonl")):
        if _should_skip_trace_file(fp, gemma4_root):
            continue
        files_read += 1
        with open(fp, encoding="utf-8") as f:
            for raw in f:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    lines_skipped += 1
                    continue
                text = obj.get("text")
                if not isinstance(text, str) or not text.strip():
                    lines_skipped += 1
                    continue
                if dedup:
                    if text in seen:
                        lines_skipped += 1
                        continue
                    seen.add(text)
                # Una sola clave "text" evita ambigüedad con ChatDataset.
                out_lines.append(
                    json.dumps({"text": text}, ensure_ascii=False) + "\n"
                )
    return out_lines, files_read, lines_skipped


def main() -> int:
    p = argparse.ArgumentParser(
        description="Materializa sft_data_dir desde traces.jsonl sanitizados (Gemma4)."
    )
    repo = Path(__file__).resolve().parents[1]
    default_gemma4 = repo / "packages" / "agents" / "train" / "gemma4"
    p.add_argument(
        "--gemma4-root",
        type=Path,
        default=default_gemma4,
        help="Raíz con YYYY/MM/DD/traces.jsonl (default: packages/.../gemma4)",
    )
    p.add_argument(
        "--out-dir",
        type=Path,
        default=None,
        help="Salida (default: <gemma4-root>/sft_data_dir)",
    )
    args = p.parse_args()
    gemma4_root: Path = args.gemma4_root.resolve()
    out_dir: Path = (
        (args.out_dir or (gemma4_root / "sft_data_dir")).resolve()
    )
    if not gemma4_root.is_dir():
        print(f"Error: no existe {gemma4_root}", file=sys.stderr)
        return 1

    val_fraction = float(os.environ.get("SFT_VALID_FRACTION", "0.1"))
    val_seed = int(os.environ.get("SFT_VALID_SEED", "42"))

    all_lines, n_files, n_skipped = _collect_text_lines(gemma4_root)
    if not all_lines:
        print(
            f"No se encontraron ejemplos con clave 'text' en {gemma4_root} "
            f"(archivos leídos={n_files}, líneas omitidas={n_skipped}). "
            "¿Ejecutaste sanitize_traces_for_gemma.py?",
            file=sys.stderr,
        )
        return 1

    train_lines, valid_lines = _split_train_valid_lines(
        all_lines, val_fraction, val_seed
    )
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "train.jsonl").write_text("".join(train_lines), encoding="utf-8")
    if valid_lines:
        (out_dir / "valid.jsonl").write_text("".join(valid_lines), encoding="utf-8")
    else:
        valid_path = out_dir / "valid.jsonl"
        if valid_path.exists():
            valid_path.unlink()
    (out_dir / "test.jsonl").write_text(
        json.dumps({"text": "ok"}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(
        f"Materializado {out_dir}: train={len(train_lines)} valid={len(valid_lines)} "
        f"test=1 (archivos traces.jsonl={n_files} líneas_totales={len(all_lines)} "
        f"omitidas={n_skipped})",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
