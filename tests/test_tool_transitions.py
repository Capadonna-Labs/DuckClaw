"""Tool transitions: outcome labels, call/result pairing, live round capture, dataset build."""

from __future__ import annotations

import json
from pathlib import Path

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from duckclaw.traces import tool_transitions as tt


def test_classify_outcome_labels() -> None:
    assert tt.classify_tool_outcome('[{"a": 1}]') == ("ok", "")
    assert tt.classify_tool_outcome('{"error": "Binder Error: column x not found"}') == ("error", "sql_binder")
    assert tt.classify_tool_outcome('{"ok": false, "hint": "x"}') == ("error", "tool_error_json")
    assert tt.classify_tool_outcome("Error: boom") == ("error", "exception")
    assert tt.classify_tool_outcome("Herramienta desconocida: foo") == ("error", "unknown_tool")


def test_chatml_backfill_pairs_calls_in_order_without_ids() -> None:
    msgs = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "how many rows?"},
        {"role": "assistant", "tool_calls": [
            {"type": "function", "function": {"name": "read_sql", "arguments": '{"query": "select x"}'}},
            {"type": "function", "function": {"name": "get_current_time", "arguments": "{}"}},
        ]},
        {"role": "tool", "name": "read_sql", "content": '{"error": "Binder Error: x"}'},
        {"role": "tool", "name": "get_current_time", "content": "2026-10-05"},
        {"role": "assistant", "tool_calls": [
            {"type": "function", "function": {"name": "read_sql", "arguments": '{"query": "select y"}'}},
        ]},
        {"role": "tool", "name": "read_sql", "content": '[{"n": 3}]'},
    ]
    recs = tt.build_transitions(msgs, session_id="s1", worker_id="w")
    assert [(r["action"]["tool"], r["outcome"]["status"]) for r in recs] == [
        ("read_sql", "error"), ("get_current_time", "ok"), ("read_sql", "ok"),
    ]
    assert json.loads(recs[2]["action"]["args"]) == {"query": "select y"}
    assert recs[2]["context"]["request"] == "how many rows?"
    assert recs[2]["context"]["prior_calls"] == [
        {"tool": "read_sql", "status": "error"}, {"tool": "get_current_time", "status": "ok"},
    ]


def test_live_round_appends_only_this_round(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("DUCKCLAW_TOOL_TRANSITIONS_DIR", str(tmp_path))
    msgs = [
        HumanMessage(content="q"),
        AIMessage(content="", tool_calls=[{"name": "read_sql", "args": {"query": "a"}, "id": "c1"}]),
        ToolMessage(content='{"error": "Catalog Error: t"}', tool_call_id="c1", name="read_sql"),
        AIMessage(content="", tool_calls=[{"name": "inspect_schema", "args": {}, "id": "c2"}]),
    ]
    n_before = len(msgs)
    msgs.append(ToolMessage(content='[{"table": "t"}]', tool_call_id="c2", name="inspect_schema"))

    tt.record_tool_round(msgs, n_before, state={"chat_id": "chat-1", "tenant_id": "t1"}, worker_id="w1")

    files = list(tmp_path.glob("*/*/*/transitions.jsonl"))
    rows = [json.loads(line) for line in files[0].read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 1
    assert rows[0]["action"]["tool"] == "inspect_schema" and rows[0]["outcome"]["status"] == "ok"
    assert rows[0]["context"]["prior_calls"] == [{"tool": "read_sql", "status": "error"}]
    assert (rows[0]["session_id"], rows[0]["worker_id"], rows[0]["tenant_id"]) == ("chat-1", "w1", "t1")


def test_dataset_merges_live_and_backfill_without_duplicates(tmp_path: Path) -> None:
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "build_tool_outcome_dataset", Path(__file__).resolve().parents[1] / "scripts" / "build_tool_outcome_dataset.py"
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    msgs = [
        {"role": "user", "content": "q"},
        {"role": "assistant", "tool_calls": [{"function": {"name": "read_sql", "arguments": '{"query": "a"}'}}]},
        {"role": "tool", "name": "read_sql", "content": "[]"},
    ]
    day = tmp_path / "traces" / "2026" / "10" / "05"
    day.mkdir(parents=True)
    (day / "traces.jsonl").write_text(json.dumps({"messages": msgs, "session_id": "s", "worker_id": "w"}) + "\n")
    live = tmp_path / "tr" / "2026" / "10" / "05"
    live.mkdir(parents=True)
    rec = tt.build_transitions(msgs, session_id="s", worker_id="w")[0]
    (live / "transitions.jsonl").write_text(json.dumps(rec) + "\n")

    rows = mod.collect(tmp_path / "traces", tmp_path / "tr", since="")
    assert len(rows) == 1 and rows[0]["source"] == "live"
    assert "transitions=1 errors=0" in mod.report(rows)


def test_allowed_tables_columns_hint(monkeypatch) -> None:
    from duckclaw.workers import read_pool

    cols = {"main.orders": ["id", "side", "timestamp"], "main.notes": ["id", "body"]}

    def run_query(sql: str) -> str:
        for table, names in cols.items():
            schema, name = table.split(".")
            if f"table_schema = '{schema}'" in sql and f"table_name = '{name}'" in sql:
                return json.dumps([{"column_name": c} for c in names])
        return "[]"

    hint = read_pool.allowed_tables_columns_hint(run_query, ["main.orders", "main.missing", "main.notes"])
    assert "main.orders(id, side, timestamp)" in hint and "main.notes(id, body)" in hint
    assert "missing" not in hint
    monkeypatch.setenv("DUCKCLAW_SQL_SCHEMA_HINT_MAX_CHARS", "40")
    capped = read_pool.allowed_tables_columns_hint(run_query, ["main.orders", "main.notes"])
    assert "main.orders" in capped and "main.notes(" not in capped and "inspect_schema" in capped
    monkeypatch.setenv("DUCKCLAW_SQL_SCHEMA_HINT_MAX_CHARS", "0")
    assert read_pool.allowed_tables_columns_hint(run_query, ["main.orders"]) == ""
    assert read_pool.allowed_tables_columns_hint(run_query, []) == ""
