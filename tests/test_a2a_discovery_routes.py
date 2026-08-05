"""Public A2A discovery route behavior."""

from __future__ import annotations

import pytest


def test_worker_is_a2a_public_flag() -> None:
    from duckclaw.agent_card_builder import worker_is_a2a_public

    assert worker_is_a2a_public({"visibility": "private", "a2a_discoverable": True}, worker_id="x")
    assert not worker_is_a2a_public({"visibility": "private", "a2a_discoverable": False}, worker_id="x")
    assert worker_is_a2a_public({"visibility": "public", "a2a_discoverable": False}, worker_id="x")
