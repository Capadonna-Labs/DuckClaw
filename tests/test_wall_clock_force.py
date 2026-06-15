"""Guardrails for removed wall-clock forcing helpers in worker factory."""

from __future__ import annotations

import inspect


def test_worker_factory_does_not_own_wall_clock_response_heuristic() -> None:
    from duckclaw.workers import factory

    assert not hasattr(factory, "_response_mentions_wall_clock")


def test_worker_factory_has_no_wall_clock_vertical_copy() -> None:
    from duckclaw.workers import factory

    source = inspect.getsource(factory)
    assert "_response_mentions_wall_clock" not in source
