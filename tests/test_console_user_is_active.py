"""console_user_is_active — stringified DuckDB bools from ephemeral RO."""

from __future__ import annotations

from duckclaw.admin_console_users import console_user_is_active


def test_console_user_is_active_truthy() -> None:
    assert console_user_is_active({"active": True})
    assert console_user_is_active({"active": "True"})
    assert console_user_is_active({"active": "true"})
    assert console_user_is_active({"active": 1})
    assert console_user_is_active({})  # default active


def test_console_user_is_active_falsy() -> None:
    assert not console_user_is_active(None)
    assert not console_user_is_active({"active": False})
    assert not console_user_is_active({"active": "False"})  # bool("False") is True — must not use bool()
    assert not console_user_is_active({"active": "false"})
    assert not console_user_is_active({"active": 0})
    assert not console_user_is_active({"active": "0"})
