from __future__ import annotations

import json


def _seed_worker_with_capability(
    con,
    *,
    worker_id: str,
    capability_name: str,
    policy: dict | None = None,
) -> dict[str, str]:
    from duckclaw.admin_worker_catalog import (
        create_worker,
        grant_worker_capability,
        register_capability,
    )

    worker = create_worker(
        con,
        owner_email="owner@example.com",
        worker_id=worker_id,
        display_name=worker_id.replace("_", " ").title(),
        source_kind="catalog",
        source_template_id=worker_id,
    )
    capability = register_capability(
        con,
        name=capability_name,
        kind="runtime_policy",
        provider="duckclaw",
    )
    grant_worker_capability(
        con,
        worker_uid=worker["worker_uid"],
        capability_id=capability["capability_id"],
        policy=policy,
    )
    return worker


def _seed_runtime_policy(
    con,
    *,
    worker_uid: str,
    policy_key: str,
    policy_scope: str,
    policy_value: dict,
) -> None:
    con.execute(
        """
        INSERT INTO main.worker_runtime_policies
          (runtime_policy_id, worker_uid, policy_key, policy_scope, policy_value_json)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            f"wrp_{worker_uid}_{policy_scope}_{policy_key}",
            worker_uid,
            policy_key,
            policy_scope,
            json.dumps(policy_value, sort_keys=True),
        ],
    )


def test_normalize_worker_id_is_stable_and_pure() -> None:
    from duckclaw.workers.identity import normalize_worker_id

    assert normalize_worker_id(None) == ""
    assert normalize_worker_id("  Worker_Alpha  ") == "worker_alpha"
    assert normalize_worker_id("Worker-Beta") == "worker-beta"


def test_runtime_policy_reads_identity_capabilities_and_policy_from_db() -> None:
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations
    from duckclaw.workers.identity import WorkerRuntimePolicyReader

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    worker = _seed_worker_with_capability(
        con,
        worker_id="worker_alpha",
        capability_name="capability_alpha",
        policy={"mode": "read"},
    )
    _seed_runtime_policy(
        con,
        worker_uid=worker["worker_uid"],
        policy_key="routing_alpha",
        policy_scope="tool_policy",
        policy_value={"priority": 10},
    )

    runtime_policy = WorkerRuntimePolicyReader(con).load(
        "  worker_alpha  ",
        tenant_id=worker["tenant_id"],
    )

    assert runtime_policy.identity is not None
    assert runtime_policy.identity.worker_uid == worker["worker_uid"]
    assert runtime_policy.identity.worker_id == "worker_alpha"
    assert runtime_policy.has_capability("capability_alpha")
    assert runtime_policy.policy_for("capability_alpha") == {"mode": "read"}
    assert runtime_policy.runtime_policy_value("routing_alpha", policy_scope="tool_policy") == {
        "priority": 10
    }

    con.close()


def test_runtime_policy_can_be_loaded_by_worker_uid() -> None:
    import duckdb

    from duckclaw.schema_migrations import run_pending_migrations
    from duckclaw.workers.identity import load_worker_runtime_policy_by_uid

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    worker = _seed_worker_with_capability(
        con,
        worker_id="worker_beta",
        capability_name="capability_beta",
    )
    _seed_runtime_policy(
        con,
        worker_uid=worker["worker_uid"],
        policy_key="flag_beta",
        policy_scope="flag",
        policy_value={"enabled": True},
    )

    runtime_policy = load_worker_runtime_policy_by_uid(con, worker["worker_uid"])

    assert runtime_policy.worker_id == "worker_beta"
    assert runtime_policy.has_capability("capability_beta")
    assert runtime_policy.runtime_policy_value("flag_beta") == {"enabled": True}

    con.close()


def test_worker_runtime_policy_table_rejects_invalid_json() -> None:
    import duckdb
    import pytest

    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)

    with pytest.raises(Exception, match="Constraint"):
        con.execute(
            """
            INSERT INTO main.worker_runtime_policies
              (runtime_policy_id, worker_uid, policy_key, policy_scope, policy_value_json)
            VALUES ('wrp_invalid', 'wrk_invalid', 'flag_invalid', 'flag', 'not-json')
            """
        )

    con.close()
