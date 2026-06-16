#!/usr/bin/env python3
"""Thin shim: ``uv run python scripts/migrate.py`` → ``duckclaw-migrate``."""

from __future__ import annotations

from duckclaw.cli.migrate import main

if __name__ == "__main__":
    raise SystemExit(main())
