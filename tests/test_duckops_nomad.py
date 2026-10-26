"""Project N.O.M.A.D. is opt-in: the compose never ships default secrets, publishes on loopback, pins its image and does not add a second Docker-socket mount."""

from __future__ import annotations

import re
import stat
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from duckops.cli import app
from duckops.commands import nomad

_COMPOSE = nomad.compose_file()
runner = CliRunner()


def _compose() -> dict:
    return yaml.safe_load(_COMPOSE.read_text(encoding="utf-8"))


def test_compose_has_no_default_secrets_and_requires_every_secret() -> None:
    text = _COMPOSE.read_text(encoding="utf-8")
    assert "replaceme" not in text
    for var in ("NOMAD_APP_KEY", "NOMAD_DB_PASSWORD", "NOMAD_DB_ROOT_PASSWORD", "NOMAD_DATA_DIR"):
        assert f"${{{var}:?" in text, var                                                  # compose refuses to start without it


def test_compose_binds_loopback_pins_the_image_and_mounts_the_socket_once() -> None:
    c = _compose()
    admin = c["services"]["admin"]
    assert admin["ports"] == ["${NOMAD_BIND:-127.0.0.1}:${NOMAD_PORT:-8080}:8080"]
    assert re.search(r"project-nomad:\$\{NOMAD_VERSION:-v\d+\.\d+\.\d+\}$", admin["image"]) and admin["pull_policy"] == "missing"
    sockets = [name for name, svc in c["services"].items() if any("docker.sock" in v for v in svc.get("volumes", []))]
    assert sockets == ["admin"] and set(c["services"]) == {"admin", "mysql", "redis"}     # no Dozzle, no updater sidecar
    assert "ports" not in c["services"]["mysql"] and "ports" not in c["services"]["redis"]


def test_first_up_generates_random_private_secrets_and_keeps_them(tmp_path: Path) -> None:
    env = nomad.ensure_env(tmp_path, "127.0.0.1", 8080)
    assert len({env["NOMAD_APP_KEY"], env["NOMAD_DB_PASSWORD"], env["NOMAD_DB_ROOT_PASSWORD"]}) == 3 and len(env["NOMAD_APP_KEY"]) >= 16
    assert Path(env["NOMAD_DATA_DIR"]).is_dir() and env["NOMAD_URL"] == "http://127.0.0.1:8080"
    mode = stat.S_IMODE((tmp_path / ".env").stat().st_mode)
    assert mode & 0o077 == 0 or not hasattr(__import__("os"), "geteuid")                  # 0600 on POSIX (Windows ignores chmod)
    assert nomad.ensure_env(tmp_path, "127.0.0.1", 9090)["NOMAD_DB_PASSWORD"] == env["NOMAD_DB_PASSWORD"]   # re-running never rotates the DB password


def test_up_refuses_a_public_bind_without_expose(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_NOMAD_HOME", str(tmp_path))
    res = runner.invoke(app, ["nomad", "up", "--bind", "0.0.0.0", "--dry-run"])
    assert res.exit_code == 2 and "--expose" in (res.output or "")
    assert not (tmp_path / ".env").exists()


def test_dry_run_prints_the_compose_command_and_writes_nothing(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_NOMAD_HOME", str(tmp_path))
    res = runner.invoke(app, ["nomad", "up", "--dry-run"])
    assert res.exit_code == 0 and "docker compose" in res.output and "--env-file" in res.output and str(_COMPOSE) in res.output
    assert not (tmp_path / ".env").exists()
    assert runner.invoke(app, ["nomad", "status", "--dry-run"]).exit_code == 0 and runner.invoke(app, ["nomad", "down", "--dry-run"]).exit_code == 0


def test_nothing_in_the_default_stack_mentions_nomad() -> None:
    root = Path(__file__).resolve().parents[1]
    for f in ("deploy/docker/docker-compose.yml", "deploy/docker/docker-compose.release.yml"):
        assert "nomad" not in (root / f).read_text(encoding="utf-8").lower(), f
