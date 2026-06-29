"""Tests for progress timer during graph invoke."""

from __future__ import annotations

import asyncio

import pytest

from duckclaw_pipecat.graph_bridge import GraphBridgeOutcome
from duckclaw_pipecat.processors.progress_tts import invoke_graph_with_progress

PROGRESS = "Un momento, estoy consultando datos."


@pytest.mark.asyncio
async def test_progress_emitted_while_waiting() -> None:
    progress: list[str] = []

    async def slow_invoke() -> GraphBridgeOutcome:
        await asyncio.sleep(0.15)
        return GraphBridgeOutcome(kind="worker_reply", text="ok")

    outcome = await invoke_graph_with_progress(
        slow_invoke,
        progress_phrase=PROGRESS,
        delay_sec=0.05,
        on_progress=progress.append,
    )
    assert outcome.text == "ok"
    assert progress == [PROGRESS]


@pytest.mark.asyncio
async def test_no_progress_when_fast() -> None:
    progress: list[str] = []

    async def fast_invoke() -> GraphBridgeOutcome:
        return GraphBridgeOutcome(kind="worker_reply", text="instant")

    outcome = await invoke_graph_with_progress(
        fast_invoke,
        progress_phrase=PROGRESS,
        delay_sec=0.2,
        on_progress=progress.append,
    )
    assert outcome.text == "instant"
    assert progress == []
