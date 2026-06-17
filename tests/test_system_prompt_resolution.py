from __future__ import annotations

import hashlib
from pathlib import Path

from duckclaw.workers.manifest import WorkerSpec


def _seed_policy(con, policy_type: str, policy_name: str, content: str) -> None:
    con.execute(
        "DELETE FROM main.prompt_policy_registry WHERE policy_type = ? AND policy_name = ?",
        [policy_type, policy_name],
    )
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


def _spec(worker_dir: Path) -> WorkerSpec:
    return WorkerSpec(
        worker_id="default",
        logical_worker_id="default",
        name="default",
        schema_name="default",
        llm_required=None,
        temperature=0.0,
        topology="general",
        skills_list=[],
        allowed_tables=[],
        read_only=True,
        worker_dir=worker_dir,
    )


def test_resolve_effective_system_prompt_prefers_db_over_filesystem(tmp_path: Path) -> None:
    import duckdb

    from duckclaw.prompt_policies.system_prompt import resolve_effective_system_prompt_for_worker
    from duckclaw.schema_migrations import run_pending_migrations

    worker_dir = tmp_path / "default"
    worker_dir.mkdir()
    (worker_dir / "soul.md").write_text("LEGACY_SOUL", encoding="utf-8")
    (worker_dir / "system_prompt.md").write_text("LEGACY_SYS", encoding="utf-8")

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    _seed_policy(
        con,
        "system_prompt",
        "default",
        "DB PROMPT tenant={tenant_id} worker={worker_id}",
    )

    resolved = resolve_effective_system_prompt_for_worker(
        con,
        _spec(worker_dir),
        tenant_id="acme",
    )

    assert resolved == "DB PROMPT tenant=acme worker=default"
    assert "LEGACY_SOUL" not in resolved
    assert "LEGACY_SYS" not in resolved


def test_resolve_effective_system_prompt_uses_capa0_when_db_row_removed(
    tmp_path: Path,
) -> None:
    import duckdb

    from duckclaw.prompt_policies.system_prompt import resolve_effective_system_prompt_for_worker
    from duckclaw.schema_migrations import run_pending_migrations

    worker_dir = tmp_path / "default"
    worker_dir.mkdir()
    (worker_dir / "system_prompt.md").write_text("FS_ONLY", encoding="utf-8")

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)
    con.execute(
        "DELETE FROM main.prompt_policy_registry WHERE policy_type = 'system_prompt'"
    )

    resolved = resolve_effective_system_prompt_for_worker(
        con,
        _spec(worker_dir),
        tenant_id="tenant-z",
    )

    assert "## IDENTITY" in resolved
    assert "tenant-z" in resolved
    assert "FS_ONLY" not in resolved


def test_get_effective_system_prompt_uses_db_identity_pack(tmp_path: Path) -> None:
    import duckdb

    from duckclaw.commands.model_setup import get_effective_system_prompt
    from duckclaw.schema_migrations import run_pending_migrations

    con = duckdb.connect(":memory:")
    run_pending_migrations(con)

    prompt = get_effective_system_prompt(con, "default", tenant_id="tenant-x")

    assert "## IDENTITY" in prompt
    assert "tenant-x" in prompt
    assert "soul.md" not in prompt.lower()
