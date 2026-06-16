from __future__ import annotations


def test_worker_reply_formatting_strips_echoed_instance_headers() -> None:
    from duckclaw.manager.worker_reply_formatting import _strip_leading_subagent_instance_headers

    assert (
        _strip_leading_subagent_instance_headers("platform-orchestrator 2\nJob-Hunter 1\nResultado final")
        == "Resultado final"
    )


def test_worker_reply_formatting_prepends_label_only_once() -> None:
    from duckclaw.manager.worker_reply_formatting import _prepend_subagent_label_once

    assert _prepend_subagent_label_once("Respuesta final", "Quant-Trader 4") == (
        "Quant-Trader 4\n\nRespuesta final"
    )
    assert _prepend_subagent_label_once("Quant-Trader 4\n\nRespuesta final", "Quant-Trader 4") == (
        "Quant-Trader 4\n\nRespuesta final"
    )
    assert _prepend_subagent_label_once("**Quant-Trader 4 · COT**\nRespuesta final", "Quant-Trader 4") == (
        "**Quant-Trader 4 · COT**\nRespuesta final"
    )


def test_manager_graph_delegates_worker_reply_formatting_helpers_to_manager_module() -> None:
    from duckclaw.graphs import manager_graph
    from duckclaw.manager import worker_reply_formatting

    assert (
        manager_graph._strip_leading_subagent_instance_headers
        is worker_reply_formatting._strip_leading_subagent_instance_headers
    )
    assert (
        manager_graph._worker_base_from_subagent_label
        is worker_reply_formatting._worker_base_from_subagent_label
    )
    assert (
        manager_graph._reply_already_has_worker_header
        is worker_reply_formatting._reply_already_has_worker_header
    )
    assert (
        manager_graph._prepend_subagent_label_once
        is worker_reply_formatting._prepend_subagent_label_once
    )
