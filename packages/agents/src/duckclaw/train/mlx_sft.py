"""MLOps pipeline: load traces, curate, split, and run MLX LoRA training."""

from __future__ import annotations

import json
import os
import random
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, Optional

ROOT = Path(__file__).resolve().parents[3]
TRAIN_DIR = ROOT / "train"


def split_curated_traces(
    traces: list[dict[str, Any]],
    train_ratio: float,
    *,
    seed: int = 42,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Shuffle and split curated traces; ensure valid has at least one row when possible."""
    if not traces:
        return [], []
    if len(traces) < 2:
        return list(traces), []
    items = list(traces)
    rng = random.Random(seed)
    rng.shuffle(items)
    split_idx = int(len(items) * train_ratio)
    train_set = items[:split_idx]
    valid_set = items[split_idx:]
    if len(valid_set) == 0 and len(train_set) > 1:
        valid_set.append(train_set.pop())
    return train_set, valid_set


class MlxSFT:
    """Prepare conversation traces and run local MLX LoRA fine-tuning."""

    def __init__(self, raw_dataset_path: str, project_name: str = "Agnostic-Agent"):
        self.project_name = project_name
        self.raw_path = Path(raw_dataset_path)
        self.raw_traces: list[dict[str, Any]] = []
        self.curated_traces: list[dict[str, Any]] = []
        self._output_dir: Path | None = None

    def load_traces(self, status_filter: Optional[str] = "SUCCESS") -> MlxSFT:
        """Load JSONL traces from a file or directory tree."""
        if not self.raw_path.exists():
            raise FileNotFoundError(f"Trace source not found: {self.raw_path}")

        files = [self.raw_path] if self.raw_path.is_file() else sorted(self.raw_path.glob("**/*.jsonl"))
        loaded: list[dict[str, Any]] = []
        for file in files:
            with open(file, encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    try:
                        trace = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if status_filter:
                        st = trace.get("status")
                        if st is not None and st != status_filter:
                            continue
                    loaded.append(trace)
        self.raw_traces = loaded
        return self

    def curate(
        self,
        filter_and_format_fn: Callable[[dict[str, Any]], Optional[dict[str, Any]]],
    ) -> MlxSFT:
        """Apply curation filter; curated rows must expose ``messages``."""
        curated: list[dict[str, Any]] = []
        for trace in self.raw_traces:
            row = filter_and_format_fn(trace)
            if not row:
                continue
            if "messages" not in row:
                raise KeyError("curated trace must include messages")
            curated.append(row)
        self.curated_traces = curated
        return self

    def split_and_save(
        self,
        output_dir: str,
        train_ratio: float = 0.9,
        *,
        seed: int | None = None,
        write_test_stub: bool = True,
    ) -> MlxSFT:
        """Partition curated traces into train.jsonl / valid.jsonl (idempotent rewrite)."""
        if not self.curated_traces:
            raise ValueError("No curated traces; run curate() first")

        out_path = Path(output_dir)
        out_path.mkdir(parents=True, exist_ok=True)
        split_seed = seed if seed is not None else int(os.environ.get("SFT_VALID_SEED", "42"))
        train_set, valid_set = split_curated_traces(
            self.curated_traces,
            train_ratio,
            seed=split_seed,
        )

        def _write(dataset: list[dict[str, Any]], filename: str) -> None:
            target = out_path / filename
            with open(target, "w", encoding="utf-8") as handle:
                for item in dataset:
                    handle.write(
                        json.dumps({"messages": item["messages"]}, ensure_ascii=False) + "\n"
                    )

        _write(train_set, "train.jsonl")
        if valid_set:
            _write(valid_set, "valid.jsonl")
        else:
            stale_valid = out_path / "valid.jsonl"
            if stale_valid.exists():
                stale_valid.unlink()
        if write_test_stub:
            test_path = out_path / "test.jsonl"
            with open(test_path, "w", encoding="utf-8") as handle:
                handle.write(
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
        self._output_dir = out_path
        return self

    def _run_lora_in_process(self, argv: list[str]) -> None:
        old_argv = sys.argv
        sys.argv = argv
        try:
            from duckops.mlx_train_tqdm_patch import apply_mlx_train_tqdm_patch

            apply_mlx_train_tqdm_patch()
            from mlx_lm.lora import main as lora_main

            lora_main()
        finally:
            sys.argv = old_argv

    def _run_lora_subprocess(self, argv: list[str], *, cwd: Path | None = None) -> int:
        python_path = os.environ.get("MLX_PYTHON", sys.executable)
        cmd = [python_path, "-m", "mlx_lm", "lora", *argv[1:]]
        result = subprocess.run(cmd, cwd=str(cwd or ROOT))
        return int(result.returncode)

    def run_train(
        self,
        *,
        base_model: str,
        adapters_path: str,
        data_dir: str | None = None,
        iterations: int | None = None,
        batch_size: int = 2,
        config_path: Path | str | None = None,
        lora_layers: str | None = None,
    ) -> MlxSFT:
        """Run ``mlx_lm.lora`` in-process (or subprocess when config YAML is used)."""
        if os.environ.get("SFT_SKIP_MLX", "").lower() in ("1", "true", "yes"):
            return self

        resolved_data = Path(data_dir) if data_dir else self._output_dir
        if resolved_data is None or not resolved_data.is_dir():
            raise ValueError("data_dir is required; call split_and_save() first or pass data_dir")

        adapters = Path(adapters_path)
        adapters.mkdir(parents=True, exist_ok=True)

        if config_path is not None:
            cfg = Path(config_path).expanduser().resolve()
            cmd = [
                sys.executable,
                "-m",
                "duckops.mlx_lora_runner",
                "--config",
                str(cfg),
            ]
            repo_root = ROOT.parent.parent
            subprocess.run(cmd, cwd=str(repo_root), check=True)
            return self

        iters = iterations if iterations is not None else max(10, len(self.curated_traces) or 1)
        layers = lora_layers or os.environ.get("SFT_LORA_LAYERS", "42")
        argv = [
            "mlx_lm.lora",
            "--model",
            base_model,
            "--train",
            "--data",
            str(resolved_data),
            "--iters",
            str(iters),
            "--batch-size",
            str(batch_size),
            "--learning-rate",
            "2e-5",
            "--num-layers",
            str(layers),
            "--adapter-path",
            str(adapters),
        ]
        try:
            self._run_lora_in_process(argv)
        except ImportError:
            rc = self._run_lora_subprocess(argv)
            if rc != 0:
                raise RuntimeError(f"mlx_lm lora failed with exit code {rc}")
        return self
