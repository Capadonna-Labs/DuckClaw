from __future__ import annotations

import hashlib


def _seed_prompt_policy(con, policy_type: str, policy_name: str, content: str) -> None:
    checksum = hashlib.sha256(content.encode("utf-8")).hexdigest()
    con.execute(
        """
        INSERT INTO main.prompt_policy_registry
          (policy_id, policy_type, policy_name, version, status, content, checksum, active)
        VALUES (?, ?, ?, 1, 'active', ?, ?, true)
        """,
        [
            f"{policy_type}_{policy_name}_1",
            policy_type,
            policy_name,
            content,
            checksum,
        ],
    )


def test_manager_graph_delegates_selected_fast_plans_to_manager_module() -> None:
    from duckclaw.graphs import manager_graph
    from duckclaw.manager import fast_plans

    assert manager_graph._manager_visual_generation_intent is fast_plans._manager_visual_generation_intent
    assert manager_graph._manager_video_generation_intent is fast_plans._manager_video_generation_intent
    assert manager_graph._try_visual_generation_fast_plan is fast_plans._try_visual_generation_fast_plan
    assert manager_graph._try_quant_url_research_fast_plan is fast_plans._try_quant_url_research_fast_plan


def test_manager_graph_delegates_fast_replies_to_manager_module() -> None:
    from duckclaw.graphs import manager_graph
    from duckclaw.manager import fast_replies

    assert manager_graph._manager_greeting_fast_path_ok is fast_replies._manager_greeting_fast_path_ok
    assert manager_graph._manager_capabilities_fast_path_ok is fast_replies._manager_capabilities_fast_path_ok
    assert manager_graph._greeting_fast_reply_text is fast_replies._greeting_fast_reply_text
    assert manager_graph._capabilities_fast_reply_text is fast_replies._capabilities_fast_reply_text


def test_capabilities_fast_reply_uses_prompt_policy_resolver_db_first() -> None:
    import duckdb

    from duckclaw.manager.fast_replies import _capabilities_fast_reply_text
    from duckclaw.prompt_policies import PromptPolicyResolver
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    _seed_prompt_policy(con, "capability", "generic_worker", "DB capability for {worker_id}")

    assert _capabilities_fast_reply_text(
        "custom-worker",
        prompt_policies=PromptPolicyResolver(con),
    ) == "DB capability for custom-worker"


def test_manager_graph_capabilities_shortcut_uses_prompt_policy_resolver_db_first(monkeypatch) -> None:
    import duckdb

    from duckclaw.graphs.manager_graph import build_manager_graph
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    _seed_prompt_policy(con, "capability", "generic_worker", "DB graph capability for {worker_id}")

    monkeypatch.setattr(
        "duckclaw.graphs.on_the_fly_commands.get_effective_team_templates",
        lambda db, chat_id, tenant_id, templates_root: ["custom-worker"],
    )
    monkeypatch.setattr(
        "duckclaw.graphs.on_the_fly_commands.append_task_audit",
        lambda *args, **kwargs: None,
    )
    monkeypatch.setattr(
        "duckclaw.workers.factory.list_workers",
        lambda *args, **kwargs: ["custom-worker"],
    )

    graph = build_manager_graph(con)
    out = graph.invoke(
        {
            "incoming": "¿qué puedes hacer?",
            "chat_id": "chat-1",
            "tenant_id": "default",
        }
    )

    assert out["reply"] == "DB graph capability for custom-worker"


def test_visual_generation_fast_plan_uses_fal_image_provider(monkeypatch) -> None:
    from duckclaw.manager.fast_plans import _try_visual_generation_fast_plan

    monkeypatch.setattr(
        "duckclaw.forge.skills.visual_provider.resolve_visual_provider",
        lambda db, chat_id: "fal",
    )

    plan = _try_visual_generation_fast_plan(
        "Genera una imagen de un pato robot",
        ["Quant-Trader"],
        db=object(),
        chat_id="chat-1",
    )

    assert plan is not None
    title, tasks, planned, worker = plan
    assert title == "Generar imagen elite (Fal.ai Flux)"
    assert "generate_flux_image" in tasks[0]
    assert planned == "Genera una imagen de un pato robot"
    assert worker == "Quant-Trader"


def test_fast_plans_exports_video_generation_intent_helper() -> None:
    from duckclaw.manager.fast_plans import _manager_video_generation_intent

    assert _manager_video_generation_intent("Crea un video corto de un pato robot")
    assert not _manager_video_generation_intent("Genera una imagen de un pato robot")
