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


def test_manager_worker_reply_formatting_module_exposes_helpers() -> None:
    from duckclaw.manager import worker_reply_formatting

    assert callable(worker_reply_formatting._strip_leading_subagent_instance_headers)
    assert callable(worker_reply_formatting._worker_base_from_subagent_label)
    assert callable(worker_reply_formatting._reply_already_has_worker_header)
    assert callable(worker_reply_formatting._prepend_subagent_label_once)
