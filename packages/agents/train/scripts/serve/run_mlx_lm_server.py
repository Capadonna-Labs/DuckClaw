#!/usr/bin/env python3
"""Canonical MLX text server entrypoint."""

from __future__ import annotations

from pathlib import Path
import runpy


if __name__ == "__main__":
    legacy = Path(__file__).resolve().parents[1] / "run_mlx_lm_server.py"
    runpy.run_path(str(legacy), run_name="__main__")
