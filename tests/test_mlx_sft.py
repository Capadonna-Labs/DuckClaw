"""Tests for duckclaw.train.MlxSFT."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from duckclaw.train.mlx_sft import MlxSFT, split_curated_traces


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def test_load_traces_filters_status(tmp_path: Path) -> None:
    src = tmp_path / "traces.jsonl"
    _write_jsonl(
        src,
        [
            {
                "status": "SUCCESS",
                "messages": [
                    {"role": "user", "content": "a"},
                    {"role": "assistant", "content": "b"},
                ],
            },
            {
                "status": "FAILED",
                "messages": [
                    {"role": "user", "content": "x"},
                    {"role": "assistant", "content": "y"},
                ],
            },
        ],
    )
    sft = MlxSFT(str(src)).load_traces(status_filter="SUCCESS")
    assert len(sft.raw_traces) == 1
    assert sft.raw_traces[0]["status"] == "SUCCESS"


def test_curate_and_split_and_save_writes_train_valid(tmp_path: Path) -> None:
    src = tmp_path / "in" / "traces.jsonl"
    _write_jsonl(
        src,
        [
            {
                "status": "SUCCESS",
                "messages": [
                    {"role": "user", "content": f"u{i}"},
                    {"role": "assistant", "content": f"a{i}"},
                ],
            }
            for i in range(3)
        ],
    )
    out = tmp_path / "sft_data_dir"

    def _curator(trace: dict) -> dict | None:
        return {"messages": trace["messages"]}

    MlxSFT(str(src)).load_traces().curate(_curator).split_and_save(str(out), train_ratio=0.67, seed=1)
    train_lines = (out / "train.jsonl").read_text(encoding="utf-8").strip().splitlines()
    valid_lines = (out / "valid.jsonl").read_text(encoding="utf-8").strip().splitlines()
    assert len(train_lines) >= 1
    assert len(valid_lines) >= 1
    assert "messages" in json.loads(train_lines[0])
    assert (out / "test.jsonl").is_file()


def test_split_curated_traces_forces_valid_sample() -> None:
    traces = [{"messages": [{"role": "user", "content": str(i)}]} for i in range(2)]
    train, valid = split_curated_traces(traces, 0.9, seed=0)
    assert len(train) == 1
    assert len(valid) == 1


def test_run_train_respects_skip_mlx(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SFT_SKIP_MLX", "1")
    out = tmp_path / "data"
    out.mkdir()
    (out / "train.jsonl").write_text('{"messages":[]}\n', encoding="utf-8")
    sft = MlxSFT(str(tmp_path))
    sft._output_dir = out
    sft.curated_traces = [{"messages": [{"role": "user", "content": "x"}]}]
    result = sft.run_train(base_model="model", adapters_path=str(tmp_path / "adapters"))
    assert result is sft


def test_run_train_requires_data_dir(tmp_path: Path) -> None:
    sft = MlxSFT(str(tmp_path))
    with pytest.raises(ValueError, match="data_dir"):
        sft.run_train(base_model="m", adapters_path=str(tmp_path / "adapters"))


def test_mlx_sft_module_has_no_redis_or_extensions_import() -> None:
    repo = Path(__file__).resolve().parents[1]
    mlx_py = repo / "packages" / "agents" / "src" / "duckclaw" / "train" / "mlx_sft.py"
    text = mlx_py.read_text(encoding="utf-8")
    assert "import redis" not in text
    assert "from redis" not in text
    assert "db_write_queue" not in text
    assert "duckclaw.extensions" not in text
