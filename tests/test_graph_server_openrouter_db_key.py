"""OpenRouter chat override must resolve Integraciones keys via db+tenant (not MLX fallback)."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from duckclaw.admin_runtime_settings import upsert_runtime_setting
from duckclaw.admin_user_profiles import ensure_profile_for_user
from duckclaw.bootstrap_core import bootstrap_core_schema


class _Adapter:
    def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
        self._con = con

    def execute(self, sql: str, params=None):
        if params is not None:
            return self._con.execute(sql, params)
        return self._con.execute(sql)


def test_build_llm_openrouter_uses_db_key_for_tenant(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    db_path = tmp_path / "hub.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        adapter = _Adapter(con)
        bootstrap_core_schema(adapter, seed_admin=False)
        profile = ensure_profile_for_user(adapter, email="or-user@test.local")
        tenant_id = str(profile["tenant_id"])
        upsert_runtime_setting(
            adapter,
            tenant_id=tenant_id,
            actor_email="",
            domain="integrations",
            key="openrouter.api_key",
            value_text="sk-or-test-db-key",
            secret=True,
            updated_by="or-user@test.local",
        )
    finally:
        con.close()

    from duckclaw import DuckClaw
    from duckclaw.integrations.llm_providers import build_llm

    captured: dict[str, object] = {}

    class _FakeChatOpenAI:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def bind(self, **_kwargs):
            return self

    import langchain_openai

    monkeypatch.setattr(langchain_openai, "ChatOpenAI", _FakeChatOpenAI)

    db = DuckClaw(str(db_path), read_only=True, engine="python")
    try:
        llm = build_llm(
            "openrouter",
            "deepseek/deepseek-v4-flash",
            "https://openrouter.ai/api/v1",
            prefer_env_provider=False,
            db=db,
            tenant_id=tenant_id,
        )
    finally:
        db.close()

    assert llm is not None
    assert captured.get("api_key") == "sk-or-test-db-key"
    assert captured.get("model") == "deepseek/deepseek-v4-flash"
    base = str(captured.get("base_url") or "")
    assert "openrouter.ai" in base


def test_build_llm_openrouter_missing_key_does_not_use_env_mlx(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("DUCKCLAW_LLM_PROVIDER", "mlx")
    monkeypatch.setenv("DUCKCLAW_LLM_BASE_URL", "http://127.0.0.1:8080/v1")

    db_path = tmp_path / "hub2.duckdb"
    con = duckdb.connect(str(db_path))
    try:
        adapter = _Adapter(con)
        bootstrap_core_schema(adapter, seed_admin=False)
    finally:
        con.close()

    from duckclaw import DuckClaw
    from duckclaw.integrations.llm_providers import build_llm

    db = DuckClaw(str(db_path), read_only=True, engine="python")
    try:
        with pytest.raises(RuntimeError, match="OPENROUTER_API_KEY"):
            build_llm(
                "openrouter",
                "deepseek/deepseek-v4-flash",
                "https://openrouter.ai/api/v1",
                prefer_env_provider=False,
                db=db,
                tenant_id="default",
            )
    finally:
        db.close()
