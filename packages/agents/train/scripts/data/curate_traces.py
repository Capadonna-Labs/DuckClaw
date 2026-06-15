#!/usr/bin/env python3
"""Training data curation entrypoint.

The sanitizer implementation lives in the repo-level ``scripts`` directory so
training layout wrappers do not duplicate curation rules.
"""

from __future__ import annotations

from pathlib import Path
import runpy


def _repo_root() -> Path:
    for parent in Path(__file__).resolve().parents:
        if (parent / "pyproject.toml").is_file():
            return parent
    raise RuntimeError("Could not locate DuckClaw repository root.")


def main() -> None:
    sanitizer = _repo_root() / "scripts" / "sanitize_traces_for_gemma.py"
    runpy.run_path(str(sanitizer), run_name="__main__")


if __name__ == "__main__":
    main()
