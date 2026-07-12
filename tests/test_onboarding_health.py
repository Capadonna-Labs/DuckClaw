from __future__ import annotations

from pathlib import Path

import pytest

from duckops.onboarding_health import (
    check_custom_agents_in_catalog,
    check_integration_bootstrap,
    check_llm_bootstrap,
    format_dev_next_steps,
)


def test_check_llm_bootstrap_deepseek_missing_key(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "DUCKCLAW_LLM_PROVIDER=deepseek\nDUCKCLAW_LLM_MODEL=deepseek-chat\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    health = check_llm_bootstrap(tmp_path)
    assert health.ok is False
    assert "DEEPSEEK_API_KEY" in health.detail


def test_check_llm_bootstrap_deepseek_with_key(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / ".env").write_text(
        "DUCKCLAW_LLM_PROVIDER=deepseek\nDEEPSEEK_API_KEY=sk-test\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    health = check_llm_bootstrap(tmp_path)
    assert health.ok is True


def test_check_custom_agents_in_catalog(gateway_db: Path) -> None:
    import duckdb

    con = duckdb.connect(str(gateway_db), read_only=True)
    try:
        health = check_custom_agents_in_catalog(con)
        assert health.custom_count >= 0
    finally:
        con.close()

    con_rw = duckdb.connect(str(gateway_db))
    try:
        con_rw.execute(
            "INSERT INTO main.admin_worker_catalog "
            "(worker_uid, worker_id, display_name, active, tenant_id, owner_email) "
            "VALUES ('u-test-bot', 'mi-bot', 'Mi Bot', true, 'default', 'admin@test.local')"
        )
        health2 = check_custom_agents_in_catalog(con_rw)
        assert health2.ok is True
        assert health2.custom_count >= 1
    finally:
        con_rw.close()


def test_format_dev_next_steps_lists_wizard_when_no_agents() -> None:
    from duckops.onboarding_health import AgentCatalogHealth, LlmBootstrapHealth

    lines = format_dev_next_steps(
        agents=AgentCatalogHealth(ok=False, custom_count=0, detail="x"),
        llm=LlmBootstrapHealth(ok=True, provider="deepseek", detail="ok"),
    )
    assert any("wizard" in line.lower() for line in lines)


def test_check_integration_bootstrap_lists_missing(gateway_db: Path, monkeypatch) -> None:
    import duckdb

    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    con = duckdb.connect(str(gateway_db), read_only=True)
    try:
        health = check_integration_bootstrap(con)
        assert health.ok is False
        assert any(label for label in health.missing_labels)
    finally:
        con.close()
