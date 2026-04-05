"""Mensajes de fallo en agent_node: Groq vs MLX (sin culpar al motor equivocado)."""

from duckclaw.workers.factory import _agent_node_llm_failure_user_message


def test_groq_413_mentions_groq_not_mlx() -> None:
    exc_body = (
        "Error code: 413 - {'error': {'message': 'Request too large for model "
        "`llama-3.3-70b-versatile` ... Limit 12000, Requested 19945', "
        "'type': 'tokens', 'code': 'rate_limit_exceeded'}}"
    )
    msg = _agent_node_llm_failure_user_message(RuntimeError(exc_body), provider="groq")
    assert "Groq" in msg
    assert "MLX-Inference" not in msg


def test_mlx_provider_keeps_mlx_hint() -> None:
    msg = _agent_node_llm_failure_user_message(ConnectionError("refused"), provider="mlx")
    assert "MLX-Inference" in msg


def test_non_local_provider_generic_no_mlx_blame() -> None:
    msg = _agent_node_llm_failure_user_message(ValueError("bad payload"), provider="deepseek")
    assert "MLX-Inference" not in msg
    assert "bad payload" in msg
