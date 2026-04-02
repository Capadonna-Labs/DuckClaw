"""Fusión .env + proposed antes de ``serve --pm2 --gateway`` (``.env`` inmutable)."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from duckclaw.ops.manager import _overlay_merged_repo_telegram_env_into_process


def test_overlay_telegram_prefers_proposed_over_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TELEGRAM_JOB_HUNTER_TOKEN", raising=False)
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / ".env").write_text(
        "TELEGRAM_JOB_HUNTER_TOKEN=stale_env\n"
        "TELEGRAM_BOT_TOKEN=stale_generic\n",
        encoding="utf-8",
    )
    (root / "config" / "dotenv_wizard_proposed.env").write_text(
        "TELEGRAM_JOB_HUNTER_TOKEN=fresh_proposed\n",
        encoding="utf-8",
    )
    _overlay_merged_repo_telegram_env_into_process(str(root))
    assert os.environ["TELEGRAM_JOB_HUNTER_TOKEN"] == "fresh_proposed"
    assert os.environ["TELEGRAM_BOT_TOKEN"] == "stale_generic"


def test_overlay_redis_prefers_proposed_over_dotenv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    root = tmp_path / "repo"
    (root / "config").mkdir(parents=True)
    (root / ".env").write_text(
        "REDIS_URL=redis://old:6379/0\n",
        encoding="utf-8",
    )
    (root / "config" / "dotenv_wizard_proposed.env").write_text(
        "REDIS_URL=redis://wizard-proposed:6379/0\n",
        encoding="utf-8",
    )
    _overlay_merged_repo_telegram_env_into_process(str(root))
    assert os.environ["REDIS_URL"] == "redis://wizard-proposed:6379/0"
