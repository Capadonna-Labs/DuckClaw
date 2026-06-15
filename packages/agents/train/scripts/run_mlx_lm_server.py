#!/usr/bin/env python3
"""Compatibility wrapper for the canonical MLX server entrypoint."""

from __future__ import annotations

from pathlib import Path
import runpy


if __name__ == "__main__":
    target = Path(__file__).resolve().parent / "serve" / "run_mlx_lm_server.py"
    runpy.run_path(str(target), run_name="__main__")
