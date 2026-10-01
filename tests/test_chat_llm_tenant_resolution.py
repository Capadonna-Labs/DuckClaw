"""The turn must use the model the admin selector shows (chat's tenant), not a stale 'default' row."""

from __future__ import annotations


def _fake_settings(monkeypatch, rows: dict[tuple[str, str], str]) -> None:
    from duckclaw.commands import model_setup as ms

    monkeypatch.setattr(
        ms, "_llm_runtime_value", lambda _db, _cid, key, *, tenant_id="default": rows.get((tenant_id, key), "")
    )
    monkeypatch.setattr(ms, "_get_global_config", lambda _db, _key: "")


def test_turn_uses_chat_tenant_selection_over_stale_default(monkeypatch) -> None:
    from duckclaw.commands.model_setup import resolve_llm_triplet_for_chat_invocation

    _fake_settings(
        monkeypatch,
        {
            ("default", "llm_provider"): "openrouter",
            ("default", "llm_model"): "deepseek/deepseek-v4-pro",  # stale
            ("user-t", "llm_provider"): "openrouter",
            ("user-t", "llm_model"): "deepseek/deepseek-v4-flash",  # what the UI shows
        },
    )
    trip = resolve_llm_triplet_for_chat_invocation(None, "admin-conv-x", tenant_id="user-t")
    assert trip is not None and trip[1] == "deepseek/deepseek-v4-flash"


def test_falls_back_to_default_tenant_for_fly_model_command(monkeypatch) -> None:
    from duckclaw.commands.model_setup import resolve_llm_triplet_for_chat_invocation

    _fake_settings(monkeypatch, {("default", "llm_provider"): "openrouter", ("default", "llm_model"): "z-ai/glm-5.2"})
    trip = resolve_llm_triplet_for_chat_invocation(None, "admin-conv-x", tenant_id="user-t")
    assert trip is not None and trip[1] == "z-ai/glm-5.2"
    _fake_settings(monkeypatch, {})
    assert resolve_llm_triplet_for_chat_invocation(None, "admin-conv-x", tenant_id="user-t") is None
