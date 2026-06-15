from __future__ import annotations

import hashlib
import json


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


def _seed_worker_fast_plan_capability(con, worker_id: str, policy: dict[str, object]) -> None:
    worker_uid = f"uid-{worker_id}"
    con.execute(
        """
        INSERT INTO main.admin_worker_catalog
          (worker_uid, tenant_id, owner_email, worker_id, display_name, source_kind, source_template_id, active)
        VALUES (?, 'default', 'owner@example.com', ?, ?, 'runtime', 'default', true)
        """,
        [worker_uid, worker_id, worker_id],
    )
    con.execute(
        """
        INSERT INTO main.admin_capabilities
          (capability_id, name, kind, provider, description, active)
        VALUES ('cap-fast-plan', 'fast_plan', 'planning', 'duckdb', 'DB-first fast plan', true)
        """,
    )
    con.execute(
        """
        INSERT INTO main.admin_worker_capabilities
          (worker_uid, capability_id, permission, policy_json, enabled)
        VALUES (?, 'cap-fast-plan', 'use', ?, true)
        """,
        [worker_uid, json.dumps(policy)],
    )


def test_manager_graph_delegates_capability_fast_plan_to_manager_module() -> None:
    from duckclaw.graphs import manager_graph
    from duckclaw.manager import fast_plans

    assert manager_graph._try_capability_fast_plan is fast_plans._try_capability_fast_plan


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


def test_capability_fast_plan_returns_none_without_db_policy() -> None:
    import duckdb

    from duckclaw.manager.fast_plans import _try_capability_fast_plan
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)

    assert (
        _try_capability_fast_plan(
            "prioriza esta solicitud",
            ["plain-worker"],
            db=con,
            tenant_id="default",
        )
        is None
    )


def test_capability_fast_plan_uses_db_first_worker_capability_policy() -> None:
    import duckdb

    from duckclaw.manager.fast_plans import _try_capability_fast_plan
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    _seed_worker_fast_plan_capability(
        con,
        "policy-worker",
        {
            "intent_regex": r"\bprioriza\b",
            "title": "Plan rápido transversal",
            "tasks": [
                "Ejecutar la capability configurada.",
                "No repetir acciones ya confirmadas en este turno.",
            ],
            "planned_template": "Solicitud original:\n{incoming}",
        },
    )

    plan = _try_capability_fast_plan(
        "prioriza esta solicitud",
        ["policy-worker"],
        db=con,
        tenant_id="default",
    )

    assert plan == (
        "Plan rápido transversal",
        [
            "Ejecutar la capability configurada.",
            "No repetir acciones ya confirmadas en este turno.",
        ],
        "Solicitud original:\nprioriza esta solicitud",
        "policy-worker",
    )


def test_capability_fast_plan_ignores_non_matching_policy() -> None:
    import duckdb

    from duckclaw.manager.fast_plans import _try_capability_fast_plan
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    _seed_worker_fast_plan_capability(
        con,
        "policy-worker",
        {
            "intent_regex": r"\bprioriza\b",
            "title": "Plan rápido transversal",
            "tasks": ["Ejecutar la capability configurada."],
            "planned_template": "{incoming}",
        },
    )

    assert (
        _try_capability_fast_plan(
            "solo conversa conmigo",
            ["policy-worker"],
            db=con,
            tenant_id="default",
        )
        is None
    )
