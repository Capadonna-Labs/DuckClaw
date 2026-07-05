"""DuckClaw Knowledge Indexer — folder ingest/sync and auto-sync poll (outside Gateway)."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time

_log = logging.getLogger("knowledge-indexer")
logging.basicConfig(level=logging.INFO)

_QUEUE_DEPTH_WARN_INTERVAL_SEC = 60.0


def _poll_seconds() -> float:
    from duckclaw.forge.rag.knowledge_auto_sync import auto_sync_poll_seconds

    return float(auto_sync_poll_seconds())


def _auto_sync_enabled() -> bool:
    from duckclaw.forge.rag.knowledge_auto_sync import auto_sync_enabled

    return auto_sync_enabled()


def _log_job_result(result: dict[str, object]) -> None:
    if result.get("ok"):
        _log.info("knowledge job completed: %s", result)
    elif result.get("deferred"):
        _log.debug("knowledge job deferred: %s", result.get("reason"))
    else:
        _log.warning("knowledge job failed: %s", result)


async def _maybe_warn_queue_depth(*, threshold: int, last_warn_at: float) -> float:
    from duckclaw.knowledge_sync_queue import knowledge_sync_queue_depth

    depth = await asyncio.to_thread(knowledge_sync_queue_depth)
    if depth is None or depth <= threshold:
        return last_warn_at
    now = time.monotonic()
    if now - last_warn_at < _QUEUE_DEPTH_WARN_INTERVAL_SEC:
        return last_warn_at
    _log.warning(
        "knowledge_sync_queue_depth=%s exceeds warn threshold=%s",
        depth,
        threshold,
    )
    return now


async def _indexer_worker() -> None:
    from duckclaw.knowledge_sync_queue import run_knowledge_indexer_cycle

    while True:
        result = await asyncio.to_thread(run_knowledge_indexer_cycle, block_timeout_sec=2.0)
        if result.get("processed"):
            _log_job_result(result)


async def _indexer_supervisor(*, poll_s: float, auto_sync: bool, warn_threshold: int) -> None:
    from duckclaw.knowledge_sync_queue import knowledge_sync_queue_depth

    idle_cycles = 0
    last_warn_at = 0.0
    while True:
        last_warn_at = await _maybe_warn_queue_depth(
            threshold=warn_threshold,
            last_warn_at=last_warn_at,
        )
        depth = await asyncio.to_thread(knowledge_sync_queue_depth)
        if depth and depth > 0:
            idle_cycles = 0
        else:
            idle_cycles += 1
            if auto_sync and idle_cycles * 2 >= poll_s:
                idle_cycles = 0
                try:
                    from duckclaw.forge.rag.knowledge_auto_sync import run_auto_sync_poll

                    outcomes = await asyncio.to_thread(run_auto_sync_poll)
                    if outcomes:
                        _log.info("auto-sync cycle: %s source(s) updated", len(outcomes))
                except Exception as exc:
                    _log.warning("auto-sync cycle error: %s", exc)
        await asyncio.sleep(2.0)


async def _indexer_loop() -> None:
    from duckclaw.knowledge_indexer_config import (
        knowledge_indexer_max_inflight,
        knowledge_queue_depth_warn_threshold,
    )

    poll_s = _poll_seconds()
    auto_sync = _auto_sync_enabled()
    max_inflight = knowledge_indexer_max_inflight()
    warn_threshold = knowledge_queue_depth_warn_threshold()
    _log.info(
        "knowledge-indexer started (queue=%s, auto_sync=%s, poll=%ss, max_inflight=%s)",
        "duckclaw:knowledge_sync_jobs",
        auto_sync,
        poll_s,
        max_inflight,
    )
    workers = [asyncio.create_task(_indexer_worker(), name=f"knowledge-worker-{idx}") for idx in range(max_inflight)]
    supervisor = asyncio.create_task(
        _indexer_supervisor(poll_s=poll_s, auto_sync=auto_sync, warn_threshold=warn_threshold),
        name="knowledge-supervisor",
    )
    await asyncio.gather(supervisor, *workers)


def main() -> None:
    os.environ.setdefault("DUCKCLAW_PROCESS_ROLE", "knowledge-indexer")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    stop = asyncio.Event()

    def _handle_sig(*_args: object) -> None:
        stop.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_sig)
        except NotImplementedError:
            signal.signal(sig, lambda *_a: _handle_sig())

    task = loop.create_task(_indexer_loop(), name="knowledge-indexer-loop")

    async def _wait_stop() -> None:
        await stop.wait()
        task.cancel()

    try:
        loop.run_until_complete(_wait_stop())
    except KeyboardInterrupt:
        task.cancel()
    finally:
        try:
            loop.run_until_complete(task)
        except asyncio.CancelledError:
            pass
        loop.close()
        _log.info("knowledge-indexer stopped")


if __name__ == "__main__":
    main()
