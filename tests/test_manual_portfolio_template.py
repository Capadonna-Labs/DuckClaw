"""Seed template manual-portfolio: loads, its schema runs, it can write its own tables and fetch prices."""

from __future__ import annotations

from pathlib import Path

import duckdb

SEED = Path(__file__).resolve().parents[1] / "packages" / "agents" / "src" / "duckclaw" / "forge" / "seed"
TEMPLATE = SEED / "manual-portfolio"


def test_template_imports_into_the_catalog_with_its_own_tables_and_write_tool(gateway_db: Path) -> None:
    from duckclaw import DuckClaw
    from duckclaw.admin_template_import import import_templates_to_catalog
    from duckclaw.catalog_worker import load_manifest_from_catalog

    class _Adapter:
        def __init__(self, con: duckdb.DuckDBPyConnection) -> None:
            self._con = con

        def execute(self, sql: str, params=None):  # noqa: ANN001
            return self._con.execute(sql, params) if params is not None else self._con.execute(sql)

    con = duckdb.connect(str(gateway_db))
    try:
        out = import_templates_to_catalog(
            _Adapter(con), owner_email="admin@test.local", templates_root=SEED,
            include_template_ids=("manual-portfolio",),
        )
    finally:
        con.close()
    assert [item["worker_id"] for item in out["imported"]] == ["manual-portfolio"]

    with DuckClaw(str(gateway_db), read_only=True) as db:
        spec = load_manifest_from_catalog(db, "manual-portfolio")
    assert spec.schema_name == "agent_worker"
    assert set(spec.allowed_tables) == {"agent_worker.holdings", "agent_worker.price_marks"}
    assert "admin_sql" in (spec.tool_surface_config or {}).get("expose_privileged_mutation_tools", [])


def test_schema_runs_and_holds_a_position() -> None:
    con = duckdb.connect()
    con.execute(TEMPLATE.joinpath("schema.sql").read_text(encoding="utf-8"))
    con.execute(
        "INSERT INTO agent_worker.holdings (id, broker, symbol, price_symbol, quantity, avg_cost) "
        "VALUES (uuid(), 'app', 'ICOLCAP', 'ICOLCAP.CL', 10, 24000)"
    )
    con.execute(
        "INSERT OR REPLACE INTO agent_worker.price_marks (price_symbol, mark_date, close, currency, source) "
        "VALUES ('ICOLCAP.CL', DATE '2026-10-16', 25600.5, 'COP', 'yfinance')"
    )
    assert con.execute("SELECT currency FROM agent_worker.holdings").fetchone()[0] == "COP"


def test_sandbox_can_reach_the_internet_for_prices() -> None:
    from duckclaw.forge.schema import load_security_policy, security_policy_to_docker_kwargs

    policy = load_security_policy("manual-portfolio", worker_dir=TEMPLATE)
    assert security_policy_to_docker_kwargs(policy)["network_mode"] == "bridge"
    assert policy.secrets.allowed_secrets == []
