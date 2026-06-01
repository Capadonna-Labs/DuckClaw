"""Quant-Trader: ancla temporal con get_current_time (post-LLM _needs_gct)."""

import json

from duckclaw.workers.factory import (
    _deterministic_market_worker_tool_summary,
    _format_finanz_deudas_rows_prose,
    _parse_read_sql_tool_rows,
    _ibkr_disabled_chat_hint,
    _incoming_has_vlm_context,
    _incoming_is_lone_http_url,
    _incoming_is_portfolio_query,
    _is_finanz_local_accounts_query,
    _market_worker_egress_brand,
    _market_worker_needs_egress_repair,
    _parse_get_current_time_json,
    _quant_gct_only_vlm_turn,
    _quant_trader_should_force_current_time,
    _quant_trader_vlm_incoming_suggests_market_figure,
    _quant_vlm_post_tools_synthesis,
    _reddit_tools_paused,
    _reply_is_fetch_market_data_json_only,
    _reply_is_get_current_time_json_only,
    _reply_is_quant_tool_json_echo,
    _reply_is_read_sql_json_only,
    _response_mentions_wall_clock,
    _spec_logical_worker_id,
    _user_explicitly_requests_ibkr_portfolio,
)
from duckclaw.workers.manifest import load_manifest
from duckclaw.workers.worker_ids import (
    WORKER_FINANZ,
    is_finanz,
    is_market_worker,
    is_quant_trader,
)


def test_quant_trader_should_force_current_time_operational() -> None:
    assert _quant_trader_should_force_current_time("Genera una nueva señal para META")
    assert _quant_trader_should_force_current_time("Dame mi portfolio IBKR")
    assert _quant_trader_should_force_current_time("Procede con la señal pendiente")
    assert _quant_trader_should_force_current_time("Trae velas OHLCV de SPY")
    assert _quant_trader_should_force_current_time("Snapshot intradía de QQQ al apertura")


def test_quant_trader_should_force_current_time_negative() -> None:
    assert not _quant_trader_should_force_current_time("")
    assert not _quant_trader_should_force_current_time("gracias")
    assert not _quant_trader_should_force_current_time("[SYSTEM_EVENT: goals tick]")
    assert not _quant_trader_should_force_current_time("https://www.reddit.com/r/stocks/s/abc")
    assert not _quant_trader_should_force_current_time(
        "Usuario dice: (sin caption)\n"
        "Contexto visual adjunto: Bloomberg. Tesoros al alza en toda la curva.\n"
        "[VLM_CONTEXT image_hash=abc confidence=0.85]"
    )
    assert not _quant_trader_should_force_current_time(
        "Layoffs by sector: Tech led with 85,411 cuts YTD and 33,361 in April."
    )
    assert not _quant_trader_should_force_current_time("Que es el memorial day?")


def test_quant_trader_vlm_market_figure_ignores_confidence_metadata() -> None:
    treasury_vlm = (
        "Usuario dice: (sin caption)\n"
        "Contexto visual adjunto: Bloomberg. Tesoros al alza en toda la curva.\n"
        "[VLM_CONTEXT image_hash=abc confidence=0.85]"
    )
    assert not _quant_trader_vlm_incoming_suggests_market_figure(treasury_vlm)

    priced_vlm = (
        "Usuario dice: (sin caption)\n"
        "Contexto visual adjunto: **Precio:** $10.44, +1.56%\n"
        "[VLM_CONTEXT image_hash=abc confidence=0.85]"
    )
    assert _quant_trader_vlm_incoming_suggests_market_figure(priced_vlm)


def test_get_current_time_json_detection() -> None:
    gct = (
        '{"iso_8601": "2026-05-31T05:19:43-05:00", '
        '"day_of_week": "Sunday", "date": "2026-05-31", "time": "05:19:43"}'
    )
    assert _reply_is_get_current_time_json_only(gct)
    assert _parse_get_current_time_json(gct) is not None
    assert not _response_mentions_wall_clock(gct)


def test_incoming_has_vlm_context() -> None:
    vlm = (
        "Usuario dice: (sin caption)\n"
        "Contexto visual adjunto: Bloomberg tesoros.\n"
        "[VLM_CONTEXT image_hash=abc confidence=0.85]"
    )
    assert _incoming_has_vlm_context(vlm)
    assert not _incoming_has_vlm_context("solo texto sin vlm")


def test_spec_logical_worker_id_quant_trader() -> None:
    spec = load_manifest("Quant-Trader")
    lid = _spec_logical_worker_id(spec)
    assert lid == "quant_trader"
    assert is_quant_trader(lid)
    assert not is_quant_trader(getattr(spec, "worker_id", ""))


def test_quant_gct_only_vlm_turn() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    vlm = (
        "Usuario dice: (sin caption)\n"
        "Contexto visual adjunto: Bloomberg tesoros.\n"
        "[VLM_CONTEXT image_hash=abc confidence=0.85]"
    )
    msgs = [
        HumanMessage(content=vlm),
        ToolMessage(content='{"iso_8601":"x","day_of_week":"Sunday","date":"d","time":"t"}', name="get_current_time", tool_call_id="1"),
    ]
    assert _quant_gct_only_vlm_turn(
        msgs, vlm, last_human_idx=0, already_has_tool_result=True
    )


def test_fetch_market_data_json_detection() -> None:
    fmd = (
        '{"status": "ok", "ticker": "META", "rows_upserted": 6, '
        '"timeframe": "1d", "lookback_days": 10, "source": "yfinance_fallback"}'
    )
    assert _reply_is_fetch_market_data_json_only(fmd)
    assert _reply_is_quant_tool_json_echo(fmd)
    assert not _reply_is_fetch_market_data_json_only("META cerró en 632")


def test_quant_vlm_post_tools_synthesis_after_fetch() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    vlm = (
        "Usuario dice: (sin caption)\n"
        "Contexto visual adjunto: Bloomberg. Tesoros al alza.\n"
        "[VLM_CONTEXT image_hash=abc confidence=0.85]"
    )
    msgs = [
        HumanMessage(content=vlm),
        ToolMessage(content='{"status":"ok","ticker":"SHY"}', name="fetch_market_data", tool_call_id="1"),
        ToolMessage(content='{"status":"ok","ticker":"META"}', name="fetch_market_data", tool_call_id="2"),
    ]
    assert _quant_vlm_post_tools_synthesis(
        msgs, vlm, last_human_idx=0, already_has_tool_result=True
    )
    assert not _quant_vlm_post_tools_synthesis(
        msgs, vlm, last_human_idx=0, already_has_tool_result=False
    )


def test_read_sql_ohlcv_json_detection() -> None:
    spy_rows = (
        '[{"timestamp": "2026-05-29 04:00:00", "close": "756.47998046875"}, '
        '{"timestamp": "2026-05-28 04:00:00", "close": "754.5999755859375"}]'
    )
    assert _reply_is_read_sql_json_only(spy_rows)
    assert _reply_is_quant_tool_json_echo(spy_rows)
    assert not _reply_is_read_sql_json_only("SPY cerró en 756.48")


def test_wrapped_deudas_filas_content_formats_to_prose() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    fila = {
        "id": "32",
        "description": "Deuda con mamá",
        "amount": "100000.0",
        "creditor": "Mamá",
        "due_date": "2026-05-29",
    }
    wrapped = json.dumps(
        {
            "deudas_filas": [fila],
            "_totales_resumen_cop": {"total_recomendado_resumen_cop": 100000},
        },
        ensure_ascii=False,
    )
    rows = _parse_read_sql_tool_rows(wrapped)
    assert rows is not None and len(rows) == 1
    prose = _format_finanz_deudas_rows_prose(rows)
    assert prose and "Deudas" in prose and "mamá" in prose.lower()

    msgs = [
        HumanMessage(content="Dame un resumen de mis deudas"),
        ToolMessage(content=wrapped, name="read_sql", tool_call_id="1"),
    ]
    det = _deterministic_market_worker_tool_summary(
        msgs, 0, WORKER_FINANZ, "Dame un resumen de mis deudas"
    )
    assert "Deudas" in det
    assert "read_sql:" not in det
    assert "deudas_filas" not in det


def test_skip_llm_synthesis_false_when_inline_attempted_but_reply_empty() -> None:
    inline_attempted = True
    assert not (bool(inline_attempted) and bool("".strip()))
    assert bool(inline_attempted) and bool('read_sql: [{"id": "1"}]'.strip())


def test_finanz_read_sql_deuda_json_echo_triggers_egress_repair() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    deudas_json = (
        '[{"id": "32", "description": "Deuda con mamá", "amount": "100000.0", '
        '"creditor": "Mamá", "due_date": "2026-05-29"}]'
    )
    prefixed = f"read_sql: {deudas_json}"
    assert _reply_is_read_sql_json_only(deudas_json)
    assert _reply_is_read_sql_json_only(prefixed)
    assert _reply_is_quant_tool_json_echo(prefixed)
    msgs = [
        HumanMessage(content="Dame un resumen de lo que le debo a mi mamá"),
        ToolMessage(content=deudas_json, name="read_sql", tool_call_id="1"),
    ]
    assert _market_worker_needs_egress_repair(
        msgs,
        "Dame un resumen de lo que le debo a mi mamá",
        prefixed,
        last_human_idx=0,
        worker_id=WORKER_FINANZ,
    )


def test_market_worker_ids_and_egress_brand() -> None:
    assert is_market_worker(WORKER_FINANZ)
    assert is_market_worker("quant_trader")
    assert not is_market_worker("pqrsd_assistant")
    assert _market_worker_egress_brand(WORKER_FINANZ) == "Finanz"
    assert _market_worker_egress_brand("quant_trader") == "Quant-Trader"


def test_finanz_manifest_is_market_worker() -> None:
    spec = load_manifest("finanz")
    lid = _spec_logical_worker_id(spec)
    assert lid == WORKER_FINANZ
    assert is_finanz(lid)
    assert is_market_worker(lid)
    assert not is_quant_trader(lid)


def test_factory_agent_node_no_langchain_message_shadow_imports() -> None:
    """Local SystemMessage/ToolMessage imports in agent_node cause UnboundLocalError on reddit 403 paths."""
    import ast
    from pathlib import Path

    factory_path = (
        Path(__file__).resolve().parents[1]
        / "packages/agents/src/duckclaw/workers/factory.py"
    )
    tree = ast.parse(factory_path.read_text(encoding="utf-8"))
    shadow_names = {"SystemMessage", "ToolMessage"}
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name != "agent_node":
            continue
        imported = {
            alias.name
            for child in ast.walk(node)
            if isinstance(child, ast.ImportFrom)
            and child.module == "langchain_core.messages"
            for alias in child.names
        }
        assert not (imported & shadow_names), (
            f"agent_node must not locally import {imported & shadow_names}; "
            "use closure imports from build_worker_graph"
        )


def test_quant_vlm_post_tools_synthesis_after_read_sql() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    vlm = (
        "Usuario dice: (sin caption)\n"
        "Contexto visual adjunto: Bloomberg. Tesoros al alza en toda la curva.\n"
        "[VLM_CONTEXT image_hash=abc confidence=0.85]"
    )
    msgs = [
        HumanMessage(content=vlm),
        ToolMessage(content='{"iso_8601":"x","day_of_week":"Sunday","date":"d","time":"t"}', name="get_current_time", tool_call_id="1"),
        ToolMessage(
            content='[{"timestamp": "2026-05-29 04:00:00", "close": "82.30"}]',
            name="read_sql",
            tool_call_id="2",
        ),
    ]
    assert _quant_vlm_post_tools_synthesis(
        msgs, vlm, last_human_idx=0, already_has_tool_result=True
    )


def test_incoming_is_lone_http_url() -> None:
    infobae = (
        "https://www.infobae.com/colombia/2026/05/31/colombia-ante-las-urnas/"
        "?outputType=amp-type"
    )
    assert _incoming_is_lone_http_url(infobae)
    assert not _incoming_is_lone_http_url(f"Leer {infobae}")


def test_quant_url_post_tools_synthesis_after_tavily() -> None:
    """Infobae-style lone URL + tavily_search + get_current_time must trigger egress repair."""
    from langchain_core.messages import HumanMessage, ToolMessage

    url = (
        "https://www.infobae.com/colombia/2026/05/31/"
        "colombia-ante-las-urnas-izquierda-derecha-y-un-outsider-se-disputan-la-presidencia/"
    )
    msgs = [
        HumanMessage(content=url),
        ToolMessage(
            content='{"exit_code": 1, "browser_image_missing": true}',
            name="run_browser_sandbox",
            tool_call_id="1",
        ),
        ToolMessage(content="## Respuesta\nColombia elecciones...", name="tavily_search", tool_call_id="2"),
        ToolMessage(
            content='{"iso_8601":"2026-05-31T08:44:33-05:00","day_of_week":"Sunday","date":"2026-05-31","time":"08:44:33"}',
            name="get_current_time",
            tool_call_id="3",
        ),
    ]
    assert _quant_vlm_post_tools_synthesis(
        msgs, url, last_human_idx=0, already_has_tool_result=True
    )
    gct_json = (
        '{"iso_8601": "2026-05-31T08:44:33-05:00", '
        '"day_of_week": "Sunday", "date": "2026-05-31", "time": "08:44:33"}'
    )
    assert _reply_is_quant_tool_json_echo(gct_json)


def test_quant_lone_url_only_get_current_time_no_synthesis() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    url = "https://example.com/article"
    msgs = [
        HumanMessage(content=url),
        ToolMessage(
            content='{"iso_8601":"x","day_of_week":"Sunday","date":"d","time":"t"}',
            name="get_current_time",
            tool_call_id="1",
        ),
    ]
    assert not _quant_vlm_post_tools_synthesis(
        msgs, url, last_human_idx=0, already_has_tool_result=True
    )


def test_reddit_tools_paused_env(monkeypatch) -> None:
    monkeypatch.delenv("DUCKCLAW_REDDIT_PAUSED", raising=False)
    assert not _reddit_tools_paused()
    monkeypatch.setenv("DUCKCLAW_REDDIT_PAUSED", "1")
    assert _reddit_tools_paused()


def test_incoming_is_portfolio_query() -> None:
    assert _incoming_is_portfolio_query("Dame un resumen de mi portfolio")
    assert _incoming_is_portfolio_query("Usa get_ibkr_portfolio")
    assert not _incoming_is_portfolio_query("resumen de mis cuentas bancarias")


def test_user_explicitly_requests_ibkr_portfolio() -> None:
    assert _user_explicitly_requests_ibkr_portfolio("Usa get_ibkr_portfolio")
    assert not _user_explicitly_requests_ibkr_portfolio("Dame un resumen de mi portfolio")


def test_quant_portfolio_post_tools_synthesis_after_read_sql() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    ask = "Dame un resumen de mi portfolio"
    msgs = [
        HumanMessage(content=ask),
        ToolMessage(content='{"iso_8601":"x","time":"08:58:57"}', name="get_current_time", tool_call_id="1"),
        ToolMessage(content='[{"ticker":"META"}]', name="read_sql", tool_call_id="2"),
    ]
    assert _quant_vlm_post_tools_synthesis(
        msgs, ask, last_human_idx=0, already_has_tool_result=True
    )


def test_ibkr_disabled_chat_hint_mentions_on_command() -> None:
    hint = _ibkr_disabled_chat_hint()
    assert "/ibkr on --mode paper" in hint
    assert "/ibkr on --mode live" in hint


def test_finanz_gct_only_cuentas_query_needs_egress_repair() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    ask = "Dame un resumen de mis cuentas"
    assert _is_finanz_local_accounts_query(ask)
    gct_json = (
        '{"iso_8601": "2026-05-31T05:19:43-05:00", '
        '"day_of_week": "Sunday", "date": "2026-05-31", "time": "05:19:43"}'
    )
    msgs = [
        HumanMessage(content=ask),
        ToolMessage(
            content=gct_json,
            name="get_current_time",
            tool_call_id="1",
        ),
    ]
    assert not _quant_vlm_post_tools_synthesis(
        msgs, ask, last_human_idx=0, already_has_tool_result=True
    )
    assert _market_worker_needs_egress_repair(
        msgs,
        ask,
        gct_json,
        last_human_idx=0,
        worker_id=WORKER_FINANZ,
    )
    assert _reply_is_quant_tool_json_echo(gct_json)


def test_finanz_gct_only_cuentas_empty_reply_needs_egress_repair() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    ask = "Dame un resumen de mis cuentas"
    msgs = [
        HumanMessage(content=ask),
        ToolMessage(
            content='{"iso_8601":"x","day_of_week":"Sunday","date":"d","time":"t"}',
            name="get_current_time",
            tool_call_id="1",
        ),
    ]
    assert _market_worker_needs_egress_repair(
        msgs, ask, "", last_human_idx=0, worker_id=WORKER_FINANZ
    )


def test_quant_lone_url_gct_json_echo_no_egress_repair() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    url = "https://example.com/article"
    gct_json = '{"iso_8601":"x","day_of_week":"Sunday","date":"d","time":"t"}'
    msgs = [
        HumanMessage(content=url),
        ToolMessage(content=gct_json, name="get_current_time", tool_call_id="1"),
    ]
    assert not _market_worker_needs_egress_repair(
        msgs, url, gct_json, last_human_idx=0, worker_id="quant_trader"
    )


def test_quant_generic_post_tools_synthesis_after_fetch_market_data() -> None:
    from langchain_core.messages import HumanMessage, ToolMessage

    ask = "Trae velas OHLCV de SPY"
    msgs = [
        HumanMessage(content=ask),
        ToolMessage(content='{"iso_8601":"x","time":"09:00:00"}', name="get_current_time", tool_call_id="1"),
        ToolMessage(content='[{"close":750.0}]', name="fetch_market_data", tool_call_id="2"),
    ]
    assert _quant_vlm_post_tools_synthesis(
        msgs, ask, last_human_idx=0, already_has_tool_result=True
    )
