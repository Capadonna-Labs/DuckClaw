from __future__ import annotations

from pathlib import Path

import duckdb
from typer.testing import CliRunner

from duckops.cli import app

runner = CliRunner()


def _patch_doctor_basics(monkeypatch, tmp_path: Path) -> None:
    import duckops.commands.doctor as doctor

    env_file = tmp_path / ".env"
    env_file.write_text(
        "DUCKCLAW_ADMIN_API_KEY=real-key-abc\n"
        "DUCKCLAW_ADMIN_EMAIL=admin@test.local\n"
        "DUCKCLAW_ADMIN_PASSWORD=secret-pass-9\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DUCKCLAW_OWNER_ID", raising=False)
    monkeypatch.delenv("DUCKCLAW_ADMIN_CHAT_ID", raising=False)
    monkeypatch.setenv("DUCKCLAW_REPO_ROOT", str(tmp_path))
    monkeypatch.setattr(doctor, "_repo_root", lambda: tmp_path)
    monkeypatch.setattr(
        "duckops.prerequisites.check_all",
        lambda: [],
    )
    monkeypatch.setattr(
        "duckops.sovereign.validate.is_port_in_use",
        lambda *_a, **_k: False,
    )
    monkeypatch.setattr(
        "duckclaw.gateway_port.resolve_gateway_port",
        lambda *_a, **_k: 8000,
    )
    monkeypatch.setattr(
        "duckclaw.schema_migrations.verify_schema_integrity",
        lambda *_a, **_k: (True, "ok"),
    )
    monkeypatch.setattr(
        "duckops.policy_health.check_framework_prompt_policies",
        lambda *_a, **_k: type("H", (), {"ok": True, "degraded": False, "summary": lambda self: "ok"})(),
    )
    monkeypatch.setattr(
        "duckops.policy_health.check_catalog_worker_system_prompts",
        lambda *_a, **_k: type("H", (), {"ok": True, "summary": lambda self: "ok"})(),
    )
    monkeypatch.setattr(
        "duckops.commands.doctor._check_db_writer",
        lambda: (True, "inline"),
    )


def _make_duckdb(path: Path, *, sources: int = 0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        con.execute(
            "CREATE TABLE IF NOT EXISTS main.admin_knowledge_sources (source_id VARCHAR PRIMARY KEY)"
        )
        for index in range(sources):
            con.execute(
                "INSERT INTO main.admin_knowledge_sources VALUES (?)",
                [f"src-{index}"],
            )
    finally:
        con.close()


def test_doctor_session_db_unified_when_paths_match(monkeypatch, tmp_path: Path) -> None:
    _patch_doctor_basics(monkeypatch, tmp_path)
    vault = tmp_path / "db" / "private" / "default" / "duckclaw.duckdb"
    _make_duckdb(vault)
    monkeypatch.setattr(
        "duckclaw.gateway_db.get_gateway_db_path",
        lambda: str(vault),
    )

    result = runner.invoke(app, ["doctor", "-C", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "Session DB unificada" in result.output
    assert "WARN Session DB unificada" not in result.output
    assert "FAIL Session DB unificada" not in result.output


def test_doctor_warns_on_hub_vault_split(monkeypatch, tmp_path: Path) -> None:
    _patch_doctor_basics(monkeypatch, tmp_path)
    legacy = tmp_path / "db" / "duckclaw.duckdb"
    vault = tmp_path / "db" / "private" / "default" / "duckclaw.duckdb"
    _make_duckdb(legacy)
    _make_duckdb(vault)
    monkeypatch.setattr(
        "duckclaw.gateway_db.get_gateway_db_path",
        lambda: str(legacy),
    )

    result = runner.invoke(app, ["doctor", "-C", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "WARN Session DB unificada" in result.output
    assert "split RAG/SQL" in result.output


def test_doctor_strict_fails_on_hub_vault_split(monkeypatch, tmp_path: Path) -> None:
    _patch_doctor_basics(monkeypatch, tmp_path)
    legacy = tmp_path / "db" / "duckclaw.duckdb"
    vault = tmp_path / "db" / "private" / "default" / "duckclaw.duckdb"
    _make_duckdb(legacy)
    _make_duckdb(vault)
    monkeypatch.setattr(
        "duckclaw.gateway_db.get_gateway_db_path",
        lambda: str(legacy),
    )

    result = runner.invoke(app, ["doctor", "--strict", "-C", str(tmp_path)])

    assert result.exit_code == 1, result.output
    assert "FAIL Session DB unificada" in result.output


def test_doctor_repair_session_db_archives_legacy(monkeypatch, tmp_path: Path) -> None:
    _patch_doctor_basics(monkeypatch, tmp_path)
    legacy = tmp_path / "db" / "duckclaw.duckdb"
    vault = tmp_path / "db" / "private" / "default" / "duckclaw.duckdb"
    _make_duckdb(legacy)
    _make_duckdb(vault)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "DUCKCLAW_GATEWAY_DB="
        + str(legacy).replace("\\", "/")
        + "\nDUCKCLAW_REPO_ROOT="
        + str(tmp_path).replace("\\", "/")
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "duckclaw.gateway_db.get_gateway_db_path",
        lambda: str(vault),
    )

    from duckops.commands.doctor import repair_legacy_session_db

    ok, detail = repair_legacy_session_db(tmp_path)
    assert ok, detail
    assert not legacy.is_file()
    assert any(tmp_path.glob(".duckops/migrate-backups/duckclaw.legacy_hub_*.duckdb.bak"))
    env_text = env_file.read_text(encoding="utf-8")
    assert "DUCKCLAW_GATEWAY_DB_PATH=db/private/default/duckclaw.duckdb" in env_text
    assert "DUCKCLAW_GATEWAY_DB=" not in env_text


def test_doctor_warns_when_knowledge_sources_split(monkeypatch, tmp_path: Path) -> None:
    _patch_doctor_basics(monkeypatch, tmp_path)
    legacy = tmp_path / "db" / "duckclaw.duckdb"
    vault = tmp_path / "db" / "private" / "default" / "duckclaw.duckdb"
    _make_duckdb(legacy, sources=2)
    _make_duckdb(vault, sources=0)
    monkeypatch.setattr(
        "duckclaw.gateway_db.get_gateway_db_path",
        lambda: str(legacy),
    )

    result = runner.invoke(app, ["doctor", "-C", str(tmp_path)])

    assert result.exit_code == 0, result.output
    assert "admin_knowledge_sources desalineado" in result.output
