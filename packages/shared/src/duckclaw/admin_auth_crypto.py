"""
Password hashing and login delay for admin console users.

Spec: specs/features/platform/ADMIN_CONSOLE_AUTH.md
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable

from duckclaw.admin_console_users import verify_password

ARGON2_TIME = int(os.environ.get("ARGON2_TIME", "2"))
ARGON2_MEMORY_KB = int(os.environ.get("ARGON2_MEMORY_KB", "65536"))
ARGON2_PARALLELISM = int(os.environ.get("ARGON2_PARALLELISM", "4"))

_ph: Any | None = None


def _password_hasher() -> Any:
    global _ph
    if _ph is None:
        from argon2 import PasswordHasher

        _ph = PasswordHasher(
            time_cost=ARGON2_TIME,
            memory_cost=ARGON2_MEMORY_KB,
            parallelism=ARGON2_PARALLELISM,
            hash_len=32,
        )
    return _ph


def hash_password_argon2(plain: str) -> tuple[str, str, dict[str, int]]:
    """Hash new password with Argon2id. Returns (hash, algo, params)."""
    ph = _password_hasher()
    hashed = ph.hash(plain or "")
    params = {
        "time_cost": ARGON2_TIME,
        "memory_cost": ARGON2_MEMORY_KB,
        "parallelism": ARGON2_PARALLELISM,
    }
    return hashed, "argon2id", params


def calculate_login_delay(failed_count: int) -> int:
    """Progressive delay in seconds; no permanent account lock."""
    if failed_count < 5:
        return 0
    return min(2 ** (failed_count - 5), 3600)


def infer_hash_algo(user_row: dict[str, Any]) -> str:
    raw = str(user_row.get("hash_algo") or "").strip()
    if raw:
        return raw
    return "pbkdf2_sha256"


def verify_and_migrate(
    email: str,
    password: str,
    user_row: dict[str, Any],
    db_update_fn: Callable[[str, str, str, dict[str, int]], None],
) -> bool:
    """
    Verify credentials; rehash PBKDF2 → Argon2id on success.
    ``db_update_fn(email, password_hash, hash_algo, hash_params)``.
    """
    algo = infer_hash_algo(user_row)
    stored = str(user_row.get("password_hash") or "").strip()
    if not stored:
        return False

    if algo == "pbkdf2_sha256":
        if not verify_password(password, stored):
            return False
        new_hash, new_algo, new_params = hash_password_argon2(password)
        db_update_fn(email, new_hash, new_algo, new_params)
        return True

    if algo == "argon2id":
        from argon2.exceptions import VerifyMismatchError

        ph = _password_hasher()
        try:
            ph.verify(stored, password)
            if ph.check_needs_rehash(stored):
                new_hash, new_algo, new_params = hash_password_argon2(password)
                db_update_fn(email, new_hash, new_algo, new_params)
            return True
        except VerifyMismatchError:
            return False
        except Exception:
            return False

    return False


def hash_params_to_json(params: dict[str, Any] | None) -> str | None:
    if not params:
        return None
    return json.dumps(params)
