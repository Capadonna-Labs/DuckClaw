"""Tests for llm_bootstrap DB-first resolution."""

from __future__ import annotations

import duckdb
import pytest

from duckclaw.admin_runtime_settings import upsert_runtime_setting
from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.bootstrap_core import bootstrap_core_schema
from duckclaw.llm_bootstrap import (
    build_llm_gap,
    evaluate_llm_bootstrap,
    llm_api_key_configured,
    resolve_llm_api_key,
)


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


def test_resolve_deepseek_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-test")
    assert resolve_llm_api_key("deepseek") == "sk-test"


def test_resolve_deepseek_db_over_env(gateway_db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "env-key")
    con = duckdb.connect(str(gateway_db))
    try:
        adapter = _Adapter(con)
        bootstrap_core_schema(adapter, seed_admin=False)
        profile = ensure_profile_for_user(adapter, email="llm@test.local")
        upsert_runtime_setting(
            adapter,
            tenant_id=profile["tenant_id"],
            actor_email="",
            domain="integrations",
            key="deepseek.api_key",
            value_text="db-deepseek",
            secret=True,
            updated_by="llm@test.local",
        )
        assert (
            resolve_llm_api_key("deepseek", db=adapter, tenant_id=profile["tenant_id"])
            == "db-deepseek"
        )
    finally:
        con.close()


def test_build_llm_gap_when_missing_key(gateway_db, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    con = duckdb.connect(str(gateway_db), read_only=True)
    try:
        gap = build_llm_gap(con, provider="deepseek")
    finally:
        con.close()
    assert gap is not None
    assert gap["label"] == "DeepSeek"
    assert "/integraciones" in gap["admin_href"]


def test_evaluate_llm_bootstrap_ok_with_env(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / ".env").write_text(
        "DUCKCLAW_LLM_PROVIDER=deepseek\nDEEPSEEK_API_KEY=sk-x\n",
        encoding="utf-8",
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-x")
    status = evaluate_llm_bootstrap(repo_root=tmp_path)
    assert status.ok is True


def test_llm_api_key_configured_mlx_needs_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_LLM_BASE_URL", raising=False)
    assert llm_api_key_configured("mlx", base_url="") is False
    assert llm_api_key_configured("mlx", base_url="http://127.0.0.1:8080/v1") is True


def test_spawn_local_first_demotes_openrouter_without_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw.llm_bootstrap import apply_spawn_local_first_llm, resolve_platform_llm_triplet

    monkeypatch.setenv("DUCKCLAW_SPAWN_PROFILE", "1")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("DUCKCLAW_LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("DUCKCLAW_LLM_BASE_URL", "http://127.0.0.1:8080/v1")
    p, _m, url = apply_spawn_local_first_llm(
        "openrouter", "", "http://127.0.0.1:8080/v1"
    )
    assert p == "mlx"
    assert "8080" in url
    triplet = resolve_platform_llm_triplet()
    assert triplet["provider"] == "mlx"


def test_spawn_keeps_openrouter_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.llm_bootstrap import apply_spawn_local_first_llm

    monkeypatch.setenv("DUCKCLAW_SPAWN_PROFILE", "1")
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    p, _m, _u = apply_spawn_local_first_llm(
        "openrouter", "model", "https://openrouter.ai/api/v1"
    )
    assert p == "openrouter"


def test_infer_ollama_from_base_url() -> None:
    from duckclaw.llm_bootstrap import infer_local_llm_provider

    assert infer_local_llm_provider("http://127.0.0.1:11434/v1") == "ollama"
    assert infer_local_llm_provider("http://127.0.0.1:8080/v1") == "mlx"
