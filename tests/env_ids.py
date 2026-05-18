"""IDs de Telegram para tests — leer desde .env, sin hardcode en el repo."""

from __future__ import annotations

import os
from pathlib import Path

_repo_root = Path(__file__).resolve().parents[1]
_env_file = _repo_root / ".env"
if _env_file.is_file():
    try:
        from dotenv import load_dotenv

        load_dotenv(_env_file, override=False)
    except ImportError:
        pass


def owner_user_id_from_env() -> str:
    return (
        (os.environ.get("DUCKCLAW_OWNER_ID") or "").strip()
        or (os.environ.get("DUCKCLAW_ADMIN_CHAT_ID") or "").strip()
    )


DEFAULT_TEST_TELEGRAM_USER_ID = "999000001"
DEFAULT_TEST_TELEGRAM_USER_ID_ALT = "999000002"


def test_telegram_user_id_from_env() -> str:
    custom = (os.environ.get("DUCKCLAW_TEST_TELEGRAM_USER_ID") or "").strip()
    if custom:
        return custom
    owner = owner_user_id_from_env()
    if owner:
        return owner
    return DEFAULT_TEST_TELEGRAM_USER_ID


TELEGRAM_TEST_USER_ID: str = test_telegram_user_id_from_env()
