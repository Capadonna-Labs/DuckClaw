"""Tests for RTVI client action payloads."""

from duckclaw_pipecat.client_actions import (
    CLIENT_MSG_APP_STATE,
    SERVER_MSG_UPDATE_STATE,
    build_update_state,
    parse_app_state,
)


def test_build_update_state_graph_invoke() -> None:
    payload = build_update_state(phase="graph_invoke", worker_id="worker_alpha", elapsed_ms=1200)
    assert payload["type"] == SERVER_MSG_UPDATE_STATE
    assert payload["phase"] == "graph_invoke"
    assert payload["worker_id"] == "worker_alpha"
    assert payload["elapsed_ms"] == 1200


def test_parse_app_state_normalizes_dict() -> None:
    parsed = parse_app_state({"chat_id": "c1", "variant": "bubble"})
    assert parsed["chat_id"] == "c1"
    assert parsed["variant"] == "bubble"


def test_parse_app_state_rejects_non_dict() -> None:
    assert parse_app_state("invalid") == {}
    assert CLIENT_MSG_APP_STATE == "app_state"
