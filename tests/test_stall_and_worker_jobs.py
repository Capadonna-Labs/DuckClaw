"""StallDetector (repeats) and WorkerJobs (background calls, concurrency cap, stop)."""

import threading

from duckclaw.stall_detector import StallDetector
from duckclaw.workers.worker_jobs import WorkerJobs


def test_stall_detector_needs_n_identical_in_a_row():
    d = StallDetector(repeats=3)
    assert [d.observe("k", s) for s in ("a", "a", "b", "a", "a")] == [False] * 5
    assert d.observe("k", "a") is True            # a, a, a
    assert d.observe("k", "a") is False           # history restarted
    assert d.observe("other", "a") is False       # keys are independent


def test_worker_jobs_start_result_cap_and_stop():
    gate, started = threading.Event(), threading.Event()

    def slow():
        started.set()
        gate.wait(5)
        return {"status": "success"}

    jobs = WorkerJobs(max_running=1)
    a = jobs.start(slow)
    assert a and started.wait(2)
    assert jobs.result(a) == {"status": "running"}
    assert jobs.start(slow) is None               # cap reached
    assert jobs.stop(a) is True
    gate.set()
    assert jobs.result(a) == {"status": "cancelled"}   # the late result is discarded
    b = jobs.start(lambda: {"status": "success"})
    assert b
    for _ in range(100):
        if jobs.result(b)["status"] == "done":
            break
        threading.Event().wait(0.02)
    assert jobs.result(b) == {"status": "done", "result": {"status": "success"}}
    assert jobs.result("nope") == {"status": "unknown"}


def test_async_tools_only_with_the_flag(monkeypatch):
    from types import SimpleNamespace

    from duckclaw.forge.skills.worker_delegate_bridge import register_worker_delegate_tools

    spec = SimpleNamespace(allowed_delegates=("helper",), logical_worker_id="boss")

    def names():
        tools: list = []
        register_worker_delegate_tools(tools, db=None, spec=spec)
        return {t.name for t in tools}

    monkeypatch.delenv("DUCKCLAW_ASYNC_WORKERS_MAX", raising=False)
    assert names() == {"invoke_worker"}
    monkeypatch.setenv("DUCKCLAW_ASYNC_WORKERS_MAX", "2")
    assert names() == {"invoke_worker", "start_worker", "worker_result", "stop_worker"}
