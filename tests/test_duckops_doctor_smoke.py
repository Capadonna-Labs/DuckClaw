from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from duckops.cli import app

runner = CliRunner()


def test_doctor_smoke_fails_when_gateway_down(monkeypatch, tmp_path: Path) -> None:
    import duckops.commands.doctor as doctor

    env_file = tmp_path / ".env"
    env_file.write_text(
        "DUCKCLAW_ADMIN_API_KEY=real-key-abc\n"
        "DUCKCLAW_ADMIN_EMAIL=admin@test.local\n"
        "DUCKCLAW_ADMIN_PASSWORD=secret-pass-9\n"
        "REDIS_URL=redis://127.0.0.1:6379/0\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(doctor, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "duckops.sovereign.validate.redis_ping_url",
        lambda *_a, **_k: (True, "pong"),
    )
    monkeypatch.setattr(
        "duckclaw.gateway_db.get_gateway_db_path",
        lambda: "",
    )
    monkeypatch.setattr(
        "duckops.sovereign.validate.is_port_in_use",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "duckclaw.gateway_port.resolve_gateway_port",
        lambda *_a, **_k: 8000,
    )

    result = runner.invoke(app, ["doctor", "--smoke", "-C", str(tmp_path)])

    assert result.exit_code == 1
    assert "Smoke /health" in result.output


def test_doctor_smoke_ok_when_health_responds(monkeypatch, tmp_path: Path) -> None:
    import duckops.commands.doctor as doctor

    env_file = tmp_path / ".env"
    env_file.write_text(
        "DUCKCLAW_ADMIN_API_KEY=real-key-abc\n"
        "DUCKCLAW_ADMIN_EMAIL=admin@test.local\n"
        "DUCKCLAW_ADMIN_PASSWORD=secret-pass-9\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(doctor, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "duckops.sovereign.validate.redis_ping_url",
        lambda *_a, **_k: (True, "pong"),
    )
    monkeypatch.setattr(
        "duckclaw.gateway_db.get_gateway_db_path",
        lambda: "",
    )
    monkeypatch.setattr(
        "duckops.sovereign.validate.is_port_in_use",
        lambda *_a, **_k: True,
    )
    monkeypatch.setattr(
        "duckclaw.gateway_port.resolve_gateway_port",
        lambda *_a, **_k: 8000,
    )

    class _Resp:
        status = 200

        def read(self, _n: int) -> bytes:
            return b'{"ok":true}'

        def __enter__(self):
            return self

        def __exit__(self, *_a: object) -> None:
            return None

    monkeypatch.setattr("urllib.request.urlopen", lambda *_a, **_k: _Resp())

    result = runner.invoke(app, ["doctor", "--smoke", "-C", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Smoke /health" in result.output


def test_smoke_command_does_not_bootstrap_or_repair(monkeypatch, tmp_path: Path) -> None:
    import duckops.commands.doctor as doctor

    seen: dict[str, object] = {}

    def fake_cmd_doctor(_ctx, **kwargs):
        seen.update(kwargs)

    monkeypatch.setattr(doctor, "cmd_doctor", fake_cmd_doctor)

    result = runner.invoke(app, ["smoke", "-C", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert seen["repo"] == tmp_path
    assert seen["smoke"] is True
    assert seen["bootstrap"] is False
    assert seen["repair_session_db"] is False
