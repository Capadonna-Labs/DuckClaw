from __future__ import annotations

from types import SimpleNamespace


def _spec_with_skill_configs(**configs):
    return SimpleNamespace(skill_configs=configs)


def test_skill_tool_registry_uses_declarative_descriptors() -> None:
    from duckclaw.workers import skill_tool_registry as registry

    assert registry.DEFAULT_SKILL_TOOL_REGISTRY
    assert all(
        isinstance(item, registry.SkillToolRegistrar)
        for item in registry.DEFAULT_SKILL_TOOL_REGISTRY
    )
    assert {item.phase for item in registry.DEFAULT_SKILL_TOOL_REGISTRY} == {"pre_llm", "post_llm"}


def test_pre_llm_registry_activates_by_surface_and_hint(monkeypatch) -> None:
    from duckclaw.workers import skill_tool_registry as registry

    calls: list[str] = []

    def _fake_loader(path: str):
        def _registrar(_tools, _config, *_args, **_kwargs):
            calls.append(path)

        return _registrar

    monkeypatch.setattr(registry, "_load_callable", _fake_loader)

    spec = _spec_with_skill_configs(
        google_trends={},
        reddit={"enabled": True},
    )
    registry.register_pre_llm_skill_tools(
        [],
        spec,
        tool_surface="full",
        incoming_hint="https://reddit.com/r/example/comments/abc",
    )

    assert calls == [
        "duckclaw.forge.skills.google_trends_bridge:register_google_trends_skill",
        "duckclaw.forge.skills.reddit_bridge:register_reddit_skill",
    ]

    calls.clear()
    registry.register_pre_llm_skill_tools(
        [],
        spec,
        tool_surface="url_research",
        incoming_hint="https://example.com/post",
    )

    assert calls == []


def test_post_llm_registry_passes_declared_context(monkeypatch) -> None:
    from duckclaw.workers import skill_tool_registry as registry

    calls: list[tuple[str, tuple, dict]] = []

    def _fake_loader(path: str):
        def _registrar(_tools, _config, *args, **kwargs):
            calls.append((path, args, kwargs))

        return _registrar

    monkeypatch.setattr(registry, "_load_callable", _fake_loader)

    llm = object()
    db = object()
    research_config = {"enabled": True}
    spec = _spec_with_skill_configs(
        research=research_config,
        openweather={},
        tailscale={"enabled": True},
        comfyui={},
        fal={"enabled": True},
    )

    registry.register_post_llm_skill_tools([], spec, db=db, llm=llm)

    by_path = {path: (args, kwargs) for path, args, kwargs in calls}
    assert by_path["duckclaw.forge.skills.research_bridge:register_research_skill"] == (
        (),
        {"llm": llm, "db": db, "tenant_id": "default"},
    )
    assert by_path["duckclaw.forge.skills.openweather_bridge:register_openweather_skill"] == (
        (research_config,),
        {"db": db, "tenant_id": "default"},
    )
    assert by_path["duckclaw.forge.skills.tailscale_bridge:register_tailscale_skill"] == (
        (),
        {},
    )
    assert by_path["duckclaw.forge.skills.comfyui_bridge:register_comfyui_skill"] == (
        (),
        {"duckclaw_db": db},
    )
    assert by_path["duckclaw.forge.skills.fal_bridge:register_fal_skill"] == (
        (),
        {"duckclaw_db": db},
    )


def test_fal_is_in_skill_tool_registry() -> None:
    from duckclaw.workers.skill_tool_registry import DEFAULT_SKILL_TOOL_REGISTRY

    names = {item.skill_name for item in DEFAULT_SKILL_TOOL_REGISTRY}
    assert "fal" in names
    fal = next(item for item in DEFAULT_SKILL_TOOL_REGISTRY if item.skill_name == "fal")
    assert fal.registrar_path.endswith("fal_bridge:register_fal_skill")
    assert fal.phase == "post_llm"
