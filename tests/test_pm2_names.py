"""Tests for PM2 app name resolution."""

from __future__ import annotations

import json
from unittest.mock import patch

from duckclaw.ops.pm2_names import (
    apply_pm2_name_to_argv,
    resolve_gateway_pm2_name,
)


def test_resolve_gateway_prefers_legacy_lowercase_name():
    jlist = json.dumps([{"name": "duckclaw-gateway", "pm2_env": {"status": "online"}}])
    with patch("duckclaw.ops.pm2_names.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = jlist
        assert resolve_gateway_pm2_name() == "duckclaw-gateway"


def test_apply_pm2_name_to_argv_gateway_restart():
    jlist = json.dumps([{"name": "duckclaw-gateway"}])
    with patch("duckclaw.ops.pm2_names.subprocess.run") as run:
        run.return_value.returncode = 0
        run.return_value.stdout = jlist
        argv = apply_pm2_name_to_argv(
            "pm2_restart_gateway",
            ["pm2", "restart", "DuckClaw-Gateway", "--update-env"],
        )
    assert argv == ["pm2", "restart", "duckclaw-gateway", "--update-env"]
