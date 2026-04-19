"""POST /api/broker/execute (IBKR_EXECUTE_ORDER_URL reference implementation)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

_ROOT = Path(__file__).resolve().parents[1]
_SVC = _ROOT / "services" / "ibkr-ohlcv-api"
if str(_SVC) not in sys.path:
    sys.path.insert(0, str(_SVC))

import ohlcv_market_routes as om


@pytest.fixture
def broker_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.delenv("OHLCV_API_KEY", raising=False)
    monkeypatch.delenv("IBKR_PORTFOLIO_API_KEY", raising=False)
    monkeypatch.delenv("OHLCV_EXECUTE_ORDER_PYTHON", raising=False)
    monkeypatch.delenv("OHLCV_EXECUTE_ORDER_SCRIPT", raising=False)
    monkeypatch.delenv("OHLCV_BROKER_EXECUTE_FORCE_PAPER", raising=False)
    app = FastAPI()
    app.include_router(om.router)
    return TestClient(app)


def test_broker_execute_no_hook_501(broker_client: TestClient) -> None:
    r = broker_client.post(
        "/api/broker/execute",
        json={"signal_id": "11111111-1111-1111-1111-111111111111", "paper": True},
    )
    assert r.status_code == 501
    body = r.json()
    assert body.get("status") == "error"
    assert "hook" in (body.get("message") or "").lower()


def test_broker_execute_bearer_required(broker_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OHLCV_API_KEY", "secret")
    r = broker_client.post(
        "/api/broker/execute",
        json={"signal_id": "11111111-1111-1111-1111-111111111111", "paper": True},
    )
    assert r.status_code == 401


def test_broker_execute_bearer_ok_no_hook(broker_client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OHLCV_API_KEY", "secret")
    r = broker_client.post(
        "/api/broker/execute",
        json={"signal_id": "11111111-1111-1111-1111-111111111111", "paper": True},
        headers={"Authorization": "Bearer secret"},
    )
    assert r.status_code == 501


def test_broker_execute_header_live_overrides_body_paper(
    broker_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "hook.py"
    script.write_text(
        "import json, sys\n"
        "print(json.dumps({'paper_arg': sys.argv[2]}))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_PYTHON", sys.executable)
    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_SCRIPT", str(script))
    r = broker_client.post(
        "/api/broker/execute",
        json={"signal_id": "11111111-1111-1111-1111-111111111111", "paper": True},
        headers={"X-Duckclaw-IBKR-Account-Mode": "live"},
    )
    assert r.status_code == 200
    assert r.json().get("paper_arg") == "0"


def test_broker_execute_header_paper_overrides_body_live(
    broker_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "hook.py"
    script.write_text(
        "import json, sys\n"
        "print(json.dumps({'paper_arg': sys.argv[2]}))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_PYTHON", sys.executable)
    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_SCRIPT", str(script))
    r = broker_client.post(
        "/api/broker/execute",
        json={"signal_id": "11111111-1111-1111-1111-111111111111", "paper": False},
        headers={"X-Duckclaw-IBKR-Account-Mode": "paper"},
    )
    assert r.status_code == 200
    assert r.json().get("paper_arg") == "1"


def test_broker_execute_subprocess_env_has_embedded_weight_json(
    broker_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def _fake_run(*_a: object, **_kw: object) -> object:
        captured["env"] = _kw.get("env") or {}

        class _R:
            returncode = 0
            stdout = "{}"
            stderr = ""

        return _R()

    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_PYTHON", sys.executable)
    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_SCRIPT", "hook.py")
    monkeypatch.setattr(om.subprocess, "run", _fake_run)
    r = broker_client.post(
        "/api/broker/execute",
        json={
            "signal_id": "11111111-1111-1111-1111-111111111111",
            "paper": True,
            "ticker": "SPY",
            "signal_type": "ENTRY",
            "proposed_weight": 4.0,
            "mandate_id": "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        },
    )
    assert r.status_code == 200
    env = captured.get("env")
    assert isinstance(env, dict)
    raw = env.get("DUCKCLAW_EMBEDDED_EXECUTE_JSON")
    assert isinstance(raw, str)
    d = json.loads(raw)
    assert d["mode"] == "weight"
    assert d["ticker"] == "SPY"
    assert d["proposed_weight"] == 4.0
    assert d["mandate_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"


def test_broker_execute_subprocess_env_has_embedded_shares_json(
    broker_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    captured: dict[str, object] = {}

    def _fake_run(*_a: object, **_kw: object) -> object:
        captured["env"] = _kw.get("env") or {}

        class _R:
            returncode = 0
            stdout = "{}"
            stderr = ""

        return _R()

    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_PYTHON", sys.executable)
    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_SCRIPT", "hook.py")
    monkeypatch.setattr(om.subprocess, "run", _fake_run)
    r = broker_client.post(
        "/api/broker/execute",
        json={
            "signal_id": "11111111-1111-1111-1111-111111111111",
            "paper": True,
            "ticker": "GLD",
            "action": "BUY",
            "quantity": 7.0,
        },
    )
    assert r.status_code == 200
    env = captured.get("env")
    assert isinstance(env, dict)
    d = json.loads(str(env.get("DUCKCLAW_EMBEDDED_EXECUTE_JSON")))
    assert d["mode"] == "shares"
    assert d["action"] == "BUY"
    assert d["quantity"] == 7.0


def test_broker_execute_force_paper_overrides_live_header(
    broker_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "hook.py"
    script.write_text(
        "import json, sys\n"
        "print(json.dumps({'paper_arg': sys.argv[2]}))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_PYTHON", sys.executable)
    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_SCRIPT", str(script))
    monkeypatch.setenv("OHLCV_BROKER_EXECUTE_FORCE_PAPER", "1")
    r = broker_client.post(
        "/api/broker/execute",
        json={"signal_id": "11111111-1111-1111-1111-111111111111", "paper": False},
        headers={"X-Duckclaw-IBKR-Account-Mode": "live"},
    )
    assert r.status_code == 200
    assert r.json().get("paper_arg") == "1"


def test_broker_execute_hook_success(
    broker_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    script = tmp_path / "hook.py"
    script.write_text(
        "import json, sys\n"
        "print(json.dumps({'ok': True, 'signal_id': sys.argv[1], 'paper': sys.argv[2]}))\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_PYTHON", sys.executable)
    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_SCRIPT", str(script))
    r = broker_client.post(
        "/api/broker/execute",
        json={"signal_id": "11111111-1111-1111-1111-111111111111", "paper": False},
    )
    assert r.status_code == 200
    data = r.json()
    assert data.get("status") == "success"
    assert data.get("ok") is True
    assert data.get("paper") == "0"


def test_broker_execute_hook_nonzero(broker_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    script = tmp_path / "bad.py"
    script.write_text("import sys\nsys.stderr.write('nope')\nsys.exit(1)\n", encoding="utf-8")
    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_PYTHON", sys.executable)
    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_SCRIPT", str(script))
    r = broker_client.post(
        "/api/broker/execute",
        json={"signal_id": "11111111-1111-1111-1111-111111111111", "paper": True},
    )
    assert r.status_code == 502
    assert "nope" in (r.json().get("message") or "")


def test_broker_execute_hook_nonzero_json_stdout_message(
    broker_client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """broker_execute_signal imprime JSON en stdout y rc≠1; stderr puede ir vacío."""
    script = tmp_path / "emit_json_exit1.py"
    script.write_text(
        'import json, sys\nprint(json.dumps({"status":"error","message":"Sin NetLiquidation USD"}))\nsys.exit(1)\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_PYTHON", sys.executable)
    monkeypatch.setenv("OHLCV_EXECUTE_ORDER_SCRIPT", str(script))
    r = broker_client.post(
        "/api/broker/execute",
        json={"signal_id": "11111111-1111-1111-1111-111111111111", "paper": True},
    )
    assert r.status_code == 502
    assert "NetLiquidation" in (r.json().get("message") or "")


def test_broker_execute_invalid_body(broker_client: TestClient) -> None:
    r = broker_client.post(
        "/api/broker/execute",
        json={"signal_id": "short", "paper": True},
    )
    assert r.status_code == 422
