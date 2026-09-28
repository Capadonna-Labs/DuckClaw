from __future__ import annotations

import json
import sys
from types import ModuleType, SimpleNamespace


def _install_fake_trading_modules(monkeypatch) -> None:
    ibkr = ModuleType("duckclaw.ibkr_bracket_orders")
    ibkr.cancel_open_orders = lambda *args, **kwargs: {}
    ibkr.connect_ibkr = lambda *args, **kwargs: None

    bridge = ModuleType("duckclaw.signal_execution_bridge")
    bridge.execute_signal_with_bracket = lambda *args, **kwargs: {}

    monkeypatch.setitem(sys.modules, "duckclaw.ibkr_bracket_orders", ibkr)
    monkeypatch.setitem(sys.modules, "duckclaw.signal_execution_bridge", bridge)


def _make_capadonna_root(tmp_path):
    root = tmp_path / "Capadonna-Driller"
    broker_dir = root / "scripts" / "capadonna"
    broker_dir.mkdir(parents=True)
    (broker_dir / "broker_execute_signal.py").write_text("# broker stub\n", encoding="utf-8")
    python_dir = root / ".venv" / "bin"
    python_dir.mkdir(parents=True)
    python_bin = python_dir / "python"
    python_bin.write_text("# python stub\n", encoding="utf-8")
    return root


def _schedule_tool(monkeypatch, tmp_path):
    _install_fake_trading_modules(monkeypatch)
    root = _make_capadonna_root(tmp_path)
    monkeypatch.setenv("CAPADONNA_DRILLER_ROOT", str(root))

    from duckclaw.forge.skills.ibkr_bracket_orders_bridge import (
        register_ibkr_bracket_orders_skill,
    )

    tools = []
    register_ibkr_bracket_orders_skill(
        tools,
        {},
        vault_db_path=str(tmp_path / "vault.duckdb"),
    )
    return root, next(tool for tool in tools if tool.name == "schedule_ibkr_shares_order_cron")


def test_schedule_ibkr_shares_order_cron_dry_run_does_not_write(
    monkeypatch,
    tmp_path,
) -> None:
    root, tool = _schedule_tool(monkeypatch, tmp_path)

    out = json.loads(
        tool.invoke(
            {
                "ticker": "MU",
                "action": "SELL",
                "quantity": 15,
                "run_date_utc": "2026-09-29",
                "cron": "30 13 29 9 *",
            }
        )
    )

    assert out["status"] == "dry_run"
    assert out["dry_run"] is True
    assert out["embedded_order"] == {
        "mode": "shares",
        "ticker": "MU",
        "action": "SELL",
        "quantity": 15,
    }
    assert out["appears_in_crons_ui"] is True
    assert out["pm2_command"][:3] == ["pm2", "start", out["script_path"]]
    assert not (root / "tasks" / "pm2").exists()


def test_schedule_ibkr_shares_order_cron_materializes_pm2_wrapper(
    monkeypatch,
    tmp_path,
) -> None:
    root, tool = _schedule_tool(monkeypatch, tmp_path)
    calls = []

    def _fake_run(cmd, **kwargs):
        calls.append((cmd, kwargs))
        return SimpleNamespace(stdout="started", stderr="")

    monkeypatch.setattr("subprocess.run", _fake_run)

    out = json.loads(
        tool.invoke(
            {
                "ticker": "MU",
                "action": "SELL",
                "quantity": 15,
                "run_date_utc": "2026-09-29",
                "cron": "30 13 29 9 *",
                "name": "mu-open-sell-15",
                "dry_run": False,
            }
        )
    )

    script_path = root / "tasks" / "pm2" / "mu-open-sell-15.sh"
    script = script_path.read_text(encoding="utf-8")

    assert out["status"] == "scheduled"
    assert out["name"] == "mu-open-sell-15"
    assert "DUCKCLAW_EMBEDDED_EXECUTE_JSON" in script
    assert '"ticker":"MU"' in script
    assert '"action":"SELL"' in script
    assert '"quantity":15' in script
    assert calls[0][0] == ["pm2", "delete", "mu-open-sell-15"]
    assert calls[1][0] == [
        "pm2",
        "start",
        str(script_path),
        "--name",
        "mu-open-sell-15",
        "--interpreter",
        "bash",
        "--cron-restart",
        "30 13 29 9 *",
        "--no-autorestart",
    ]
