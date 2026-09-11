from __future__ import annotations

import json


class _Db:
    def __init__(self, rows: list[dict]) -> None:
        self.rows = rows
        self.sql = ""

    def query(self, sql: str) -> str:
        self.sql = sql
        return json.dumps(self.rows)


def test_fetch_operational_lessons_scopes_tenant_and_formats_rows() -> None:
    from duckclaw.memory.operational_lessons import fetch_operational_lessons

    db = _Db(
        [
            {
                "topic": "tool_skipped/CEG",
                "lesson": "Siempre verificar el precio antes de declarar TP.",
            }
        ]
    )

    result = fetch_operational_lessons(db, tenant_id="tenant'one")

    assert "[tool_skipped/CEG]" in result
    assert "verificar el precio" in result
    assert "tenant_id = 'tenant''one'" in db.sql
    assert "operational_lesson" in db.sql


def test_fetch_operational_lessons_hides_query_failures() -> None:
    from duckclaw.memory.operational_lessons import fetch_operational_lessons

    class _BrokenDb:
        def query(self, _sql: str) -> str:
            raise RuntimeError("missing table")

    assert fetch_operational_lessons(_BrokenDb(), tenant_id="tenant") == ""


def test_homeostasis_node_injects_lessons_only_for_proactive_ticks() -> None:
    from duckclaw.workers.factory_graph_nodes_routing import make_homeostasis_node

    ctx = type(
        "Ctx",
        (),
        {"db": _Db([{"topic": "tool_skipped/CEG", "lesson": "Verifica el feed."}])},
    )()
    node = make_homeostasis_node(ctx)

    proactive = node(
        {
            "incoming": "[SYSTEM_EVENT: Ciclo de auto-mejora /loop]",
            "tenant_id": "tenant",
        }
    )
    ordinary = node({"incoming": "hola", "tenant_id": "tenant"})

    assert "Verifica el feed." in proactive["operational_lessons"]
    assert "operational_lessons" not in ordinary
