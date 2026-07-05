"""DuckClaw Knowledge Indexer — folder ingest/sync and auto-sync poll (outside Gateway)."""

from __future__ import annotations

import asyncio
import logging
import os
import signal

_log = logging.getLogger("knowledge-indexer")
logging.basicConfig(level=logging.INFO)


def _poll_seconds() -> float:
    from duckclaw.forge.rag.knowledge_auto_sync import auto_sync_poll_seconds

    return float(auto_sync_poll_seconds())


def _auto_sync_enabled() -> bool:
    from duckclaw.forge.rag.knowledge_auto_sync import auto_sync_enabled

    return auto_sync_enabled()


async def _indexer_loop() -> None:
    from duckclaw.knowledge_sync_queue import run_knowledge_indexer_cycle

    poll_s = _poll_seconds()
    auto_sync = _auto_sync_enabled()
    _log.info(
        "knowledge-indexer started (queue=%s, auto_sync=%s, poll=%ss)",
        "duckclaw:knowledge_sync_jobs",
        auto_sync,
        poll_s,
    )
    idle_cycles = 0
    while True:
        result = await asyncio.to_thread(run_knowledge_indexer_cycle, block_timeout_sec=2.0)
        if result.get("processed"):
            idle_cycles = 0
            if result.get("ok"):
                _log.info("knowledge job completed: %s", result)
            elif result.get("deferred"):
                _log.debug("knowledge job deferred: %s", result.get("reason"))
            else:
                _log.warning("knowledge job failed: %s", result)
            continue

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
