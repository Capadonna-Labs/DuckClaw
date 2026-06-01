#!/usr/bin/env python3
"""Canonical data-curation entrypoint for Gemma SFT traces."""

from __future__ import annotations

from pathlib import Path
import runpy


if __name__ == "__main__":
    legacy = Path(__file__).resolve().parents[1] / "curate_traces.py"
    runpy.run_path(str(legacy), run_name="__main__")
