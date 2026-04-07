"""BI Analyst worker: seed, tools, SELECT * guard, sandbox JSON."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from duckclaw import DuckClaw
from duckclaw.graphs import sandbox as sandbox_mod
from duckclaw.workers.factory import _build_worker_tools, list_workers
from duckclaw.workers.loader import load_seed_sql, run_schema
from duckclaw.workers.manifest import load_manifest


def test_list_workers_includes_bi_analyst() -> None:
    names = list_workers()
    assert "BI-Analyst" in names or "bi_analyst" in names


def test_run_schema_loads_seed_data(tmp_path: Path) -> None:
    db_path = tmp_path / "bi.duckdb"
    db = DuckClaw(str(db_path))
    spec = load_manifest("BI-Analyst")
    assert "DELETE FROM analytics_core.sales" in load_seed_sql(spec)
    run_schema(db, spec)
    raw = db.query("SELECT COUNT(*) AS c FROM analytics_core.sales")
    rows = json.loads(raw)
    assert int(rows[0]["c"]) == 1000
    raw_m = db.query("SELECT COUNT(*) AS c FROM analytics_core.system_metrics")
    assert int(json.loads(raw_m)[0]["c"]) == 200


def test_bi_analyst_tools_readonly_no_run_sql(tmp_path: Path) -> None:
    db = DuckClaw(str(tmp_path / "w.duckdb"))
    spec = load_manifest("BI-Analyst")
    run_schema(db, spec)
    tools = _build_worker_tools(db, spec)
    names = {t.name for t in tools}
    assert "read_sql" in names
    assert "run_sql" not in names
    assert "get_schema_info" in names
    assert "explain_sql" in names
    assert "admin_sql" not in names


def test_bi_analyst_select_star_requires_limit(tmp_path: Path) -> None:
    db = DuckClaw(str(tmp_path / "w2.duckdb"))
    spec = load_manifest("BI-Analyst")
    run_schema(db, spec)
    tools = _build_worker_tools(db, spec)
    by_name = {t.name: t for t in tools}
    bad = by_name["read_sql"].invoke({"query": "SELECT * FROM analytics_core.sales"})
    assert "error" in bad.lower()
    assert "LIMIT" in bad
    good = by_name["read_sql"].invoke({"query": "SELECT * FROM analytics_core.sales LIMIT 3"})
    parsed = json.loads(good)
    assert isinstance(parsed, list)
    assert len(parsed) == 3


def test_manifest_context_pruning_config() -> None:
    spec = load_manifest("BI-Analyst")
    cp = getattr(spec, "context_pruning_config", None)
    assert isinstance(cp, dict)
    assert cp.get("enabled") is True
    assert "max_messages" in cp


def test_split_for_pruning_keeps_tool_tail() -> None:
    from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

    from duckclaw.workers.factory import _split_for_pruning

    ai = AIMessage(content="", tool_calls=[{"name": "read_sql", "id": "1", "args": {}}])
    t1 = ToolMessage(content="ok", tool_call_id="1", name="read_sql")
    h = HumanMessage(content="siguiente")
    non_sys = [HumanMessage(content="a"), ai, t1, h]
    head, tail = _split_for_pruning(non_sys, keep_last=2)
    assert len(head) == 1
    assert isinstance(tail[0], AIMessage)
    assert len(tail) == 3


def test_sandbox_python_header_injected() -> None:
    from duckclaw.graphs.sandbox import _inject_sandbox_python_header

    out = _inject_sandbox_python_header("print(1)")
    assert "Available:" in out
    assert "pandas" in out
    assert "_plt_dc.rcParams" in out
    assert "savefig.dpi" in out
    assert "print(1)" in out


def test_sandbox_tool_failure_message_for_llm(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import sandbox as sandbox_mod

    def _fail(**_kwargs: object) -> sandbox_mod.ExecutionResult:
        return sandbox_mod.ExecutionResult(
            exit_code=1,
            stdout="",
            stderr="ModuleNotFoundError: No module named 'foo'",
        )

    monkeypatch.setattr(sandbox_mod, "run_in_sandbox", _fail)
    tool = sandbox_mod.sandbox_tool_factory(db=None, llm=None)
    raw = tool.invoke({"code": "import foo"})
    data = json.loads(raw)
    assert "Error en Sandbox" in data["output"]
    assert data.get("missing_pip_packages") == ["foo"]
    assert "pip install --no-cache-dir foo" in data["output"]
    assert "docker/sandbox/Dockerfile" in data["output"]


def test_sandbox_module_error_maps_sklearn_to_scikit_learn(monkeypatch: pytest.MonkeyPatch) -> None:
    from duckclaw.graphs import sandbox as sandbox_mod

    def _fail(**_kwargs: object) -> sandbox_mod.ExecutionResult:
        return sandbox_mod.ExecutionResult(
            exit_code=1,
            stdout="",
            stderr="ModuleNotFoundError: No module named 'sklearn'",
        )

    monkeypatch.setattr(sandbox_mod, "run_in_sandbox", _fail)
    tool = sandbox_mod.sandbox_tool_factory(db=None, llm=None)
    raw = tool.invoke({"code": "import sklearn"})
    data = json.loads(raw)
    assert data.get("missing_pip_packages") == ["scikit-learn"]
    assert "scikit-learn" in data["output"]


def test_compact_run_sandbox_tool_content_for_llm_caps_huge_output() -> None:
    """Workers sin context_monitor (p. ej. SIATA-Analyst) necesitan acotar el JSON de run_sandbox."""
    import json

    from duckclaw.workers.factory import _compact_run_sandbox_tool_content_for_llm

    huge = "x" * 150_000
    payload = json.dumps(
        {
            "exit_code": 0,
            "output": huge,
            "figure_base64": "Y" * 8_000,
            "figures_base64": ["Y" * 4_000, "Z" * 4_000],
        },
        ensure_ascii=False,
    )
    cap = 12_000
    out = _compact_run_sandbox_tool_content_for_llm(payload, cap)
    assert len(out) <= cap + 200
    assert "figure_base64" not in out
    assert "figures_base64" not in out
    data = json.loads(out.split("\n…[truncado por tamaño]")[0])
    assert data.get("exit_code") == 0
    assert isinstance(data.get("output"), str)
    assert len(data["output"]) < len(huge)


def test_truncate_tool_messages_strips_huge_run_sandbox_base64() -> None:
    from langchain_core.messages import ToolMessage

    from duckclaw.workers.factory import _truncate_tool_messages

    huge = "Zg==" * 50_000
    payload = json.dumps(
        {"exit_code": 0, "stdout": "Gráfico listo", "figure_base64": huge},
        ensure_ascii=False,
    )
    assert len(payload) > 20_000
    m = ToolMessage(content=payload, tool_call_id="1", name="run_sandbox")
    out = _truncate_tool_messages([m], max_chars=8000)
    assert len(out) == 1
    data = json.loads(out[0].content.split("\n…[truncado")[0])
    assert "figure_base64" not in data


def test_extract_latest_sandbox_figure_base64_from_messages() -> None:
    import base64

    from langchain_core.messages import ToolMessage

    from duckclaw.graphs.sandbox import extract_latest_sandbox_figure_base64

    png_raw = b"\x89PNG\r\n\x1a\n" + b"x" * 200
    b64_ok = base64.b64encode(png_raw).decode("ascii")
    payload = json.dumps(
        {"exit_code": 0, "stdout": "ok", "figure_base64": b64_ok},
        ensure_ascii=False,
    )
    tm = ToolMessage(content=payload, tool_call_id="x", name="run_sandbox")
    assert extract_latest_sandbox_figure_base64([tm]) == b64_ok
    not_image = ToolMessage(
        content=json.dumps({"exit_code": 0, "stdout": "ok", "figure_base64": "aGVsbG8=" * 8}),
        tool_call_id="z",
        name="run_sandbox",
    )
    assert extract_latest_sandbox_figure_base64([not_image]) is None
    bad = ToolMessage(
        content=json.dumps({"exit_code": 1, "figure_base64": b64_ok}),
        tool_call_id="y",
        name="run_sandbox",
    )
    assert extract_latest_sandbox_figure_base64([bad, tm]) == b64_ok


def test_extract_latest_sandbox_figures_base64_prefers_list() -> None:
    import base64

    from langchain_core.messages import ToolMessage

    from duckclaw.graphs.sandbox import extract_latest_sandbox_figures_base64

    png_raw = b"\x89PNG\r\n\x1a\n" + b"x" * 200
    b64_ok = base64.b64encode(png_raw).decode("ascii")
    payload = json.dumps(
        {"exit_code": 0, "stdout": "ok", "figures_base64": [b64_ok, b64_ok], "figure_base64": b64_ok},
        ensure_ascii=False,
    )
    tm = ToolMessage(content=payload, tool_call_id="x", name="run_sandbox")
    assert extract_latest_sandbox_figures_base64([tm]) == [b64_ok, b64_ok]


def test_sandbox_tool_figure_base64_from_artifact(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    png = tmp_path / "plot.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

    def _fake_run_in_sandbox(**_kwargs: object) -> sandbox_mod.ExecutionResult:
        return sandbox_mod.ExecutionResult(
            exit_code=0,
            stdout="done",
            stderr="",
            artifacts=[str(png)],
        )

    monkeypatch.setattr(sandbox_mod, "run_in_sandbox", _fake_run_in_sandbox)
    tool = sandbox_mod.sandbox_tool_factory(db=None, llm=None)
    raw = tool.invoke({"code": "x = 1"})
    data = json.loads(raw)
    assert data["stdout"] == "done"
    assert data.get("figure_base64")
    assert isinstance(data["figure_base64"], str)
    assert len(data["figure_base64"]) > 20
    assert data.get("figures_base64") == [data["figure_base64"]]


def test_sandbox_tool_figures_base64_multiple_png(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    from duckclaw.graphs import sandbox as sandbox_mod

    png_a = tmp_path / "a.png"
    png_b = tmp_path / "b.png"
    minimal = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
        b"\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    png_a.write_bytes(minimal)
    png_b.write_bytes(minimal)

    def _fake_run_in_sandbox(**_kwargs: object) -> sandbox_mod.ExecutionResult:
        return sandbox_mod.ExecutionResult(
            exit_code=0,
            stdout="done",
            stderr="",
            artifacts=[str(png_b), str(png_a)],
        )

    monkeypatch.setattr(sandbox_mod, "run_in_sandbox", _fake_run_in_sandbox)
    tool = sandbox_mod.sandbox_tool_factory(db=None, llm=None)
    data = json.loads(tool.invoke({"code": "x = 1"}))
    figs = data.get("figures_base64") or []
    assert len(figs) == 2
    assert data["figure_base64"] == figs[0]


def test_sandbox_tool_includes_document_paths_sorted(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    csv_f = tmp_path / "plan.csv"
    txt_f = tmp_path / "note.txt"
    xlsx_f = tmp_path / "bud.xlsx"
    skip_pdf = tmp_path / "x.pdf"
    csv_f.write_text("a,b\n1,2", encoding="utf-8")
    txt_f.write_text("hi", encoding="utf-8")
    xlsx_f.write_bytes(b"PK\x03\x04mini")
    skip_pdf.write_bytes(b"%PDF")

    def _fake_run_in_sandbox(**_kwargs: object) -> sandbox_mod.ExecutionResult:
        return sandbox_mod.ExecutionResult(
            exit_code=0,
            stdout="done",
            stderr="",
            artifacts=[str(skip_pdf), str(txt_f), str(csv_f), str(xlsx_f)],
        )

    monkeypatch.setattr(sandbox_mod, "run_in_sandbox", _fake_run_in_sandbox)
    tool = sandbox_mod.sandbox_tool_factory(db=None, llm=None)
    data = json.loads(tool.invoke({"code": "x = 1"}))
    docs = data.get("sandbox_document_paths") or []
    names = [Path(p).name for p in docs]
    assert names == ["bud.xlsx", "note.txt", "plan.csv"]


def test_extract_latest_sandbox_document_paths_prefers_key(tmp_path: Path) -> None:
    from langchain_core.messages import ToolMessage

    from duckclaw.graphs.sandbox import extract_latest_sandbox_document_paths

    p1 = str(tmp_path / "a.csv")
    payload = json.dumps(
        {"exit_code": 0, "sandbox_document_paths": [p1, "/other/b.txt"]},
        ensure_ascii=False,
    )
    tm = ToolMessage(content=payload, tool_call_id="x", name="run_sandbox")
    assert extract_latest_sandbox_document_paths([tm]) == [p1, "/other/b.txt"]


def test_extract_latest_sandbox_document_paths_from_artifacts(tmp_path: Path) -> None:
    from langchain_core.messages import ToolMessage

    from duckclaw.graphs.sandbox import extract_latest_sandbox_document_paths

    csv_f = tmp_path / "z.csv"
    csv_f.write_text("1", encoding="utf-8")
    payload = json.dumps({"exit_code": 0, "artifacts": [str(csv_f)]}, ensure_ascii=False)
    tm = ToolMessage(content=payload, tool_call_id="y", name="run_sandbox")
    assert extract_latest_sandbox_document_paths([tm]) == [str(csv_f.resolve())]


def test_compact_run_sandbox_strips_document_paths_adds_names() -> None:
    from duckclaw.workers.factory import _compact_run_sandbox_tool_content_for_llm

    payload = json.dumps(
        {
            "exit_code": 0,
            "sandbox_document_paths": ["/abs/output/sandbox/default/a.csv", "/abs/x/b.txt"],
        },
        ensure_ascii=False,
    )
    out = _compact_run_sandbox_tool_content_for_llm(payload, 8000)
    data = json.loads(out)
    assert "sandbox_document_paths" not in data
    assert data.get("sandbox_document_names") == ["a.csv", "b.txt"]
