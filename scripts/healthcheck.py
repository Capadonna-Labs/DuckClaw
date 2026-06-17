#!/usr/bin/env python3
"""Thin shim: ``uv run python scripts/healthcheck.py`` → ``duckclaw-healthcheck``."""

from __future__ import annotations

from duckclaw.cli.healthcheck import main

if __name__ == "__main__":
    raise SystemExit(main())
