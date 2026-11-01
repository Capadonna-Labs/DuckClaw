"""Background worker calls: start returns at once, the result is collected later (Super-agent style start/stop)."""

from __future__ import annotations

import os
import threading
import uuid
from typing import Any, Callable


def async_workers_max() -> int:
    """0 (default) = the async tools are not offered at all."""
    try:
        return max(0, int(os.environ.get("DUCKCLAW_ASYNC_WORKERS_MAX") or "0"))
    except ValueError:
        return 0


class WorkerJobs:
    # ponytail: stop() discards the result, it does not interrupt the graph: the interrupt is keyed by chat_id, so it would also cut the caller's own turn. Add a per-job
    # cancel key to the graph state if a stopped worker must free its vault before its timeout.
    def __init__(self, max_running: int, keep: int = 64) -> None:
        self._max_running = max_running
        self._keep = keep
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def start(self, fn: Callable[[], Any]) -> str | None:
        """Runs ``fn`` in its own thread. None when the concurrency cap is reached. The new thread starts with an empty context, so the worker takes the vault lock itself and waits
        for the caller's turn to release it, instead of running beside a caller that still holds the vault."""
        with self._lock:
            if sum(1 for j in self._jobs.values() if j["state"] == "running") >= self._max_running:
                return None
            job_id = uuid.uuid4().hex[:8]
            self._jobs[job_id] = {"state": "running", "result": None}
            while len(self._jobs) > self._keep:
                old = next((k for k, j in self._jobs.items() if j["state"] != "running"), None)
                if old is None:
                    break
                self._jobs.pop(old)

        def _run() -> None:
            try:
                out = fn()
            except Exception as exc:  # noqa: BLE001
                out = {"status": "error", "error": str(exc)[:500]}
            with self._lock:
                job = self._jobs.get(job_id)
                if job is not None and job["state"] == "running":
                    job["state"], job["result"] = "done", out

        threading.Thread(target=_run, name=f"worker-job-{job_id}", daemon=True).start()
        return job_id

    def result(self, job_id: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return {"status": "unknown"}
            return {"status": job["state"], **({"result": job["result"]} if job["state"] == "done" else {})}

    def stop(self, job_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None or job["state"] != "running":
                return False
            job["state"] = "cancelled"
            return True


_JOBS: WorkerJobs | None = None


def get_worker_jobs() -> WorkerJobs:
    global _JOBS
    if _JOBS is None:
        _JOBS = WorkerJobs(async_workers_max())
    return _JOBS


__all__ = ["WorkerJobs", "async_workers_max", "get_worker_jobs"]
