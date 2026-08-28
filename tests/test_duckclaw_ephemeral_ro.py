"""DuckClaw RO ephemeral: no persistent file lock blocking db-writer RW."""

from __future__ import annotations

import multiprocessing
from pathlib import Path


def _hold_ro(path: str, ready, done) -> None:
    from duckclaw import DuckClaw

    db = DuckClaw(path, read_only=True, engine="python")
    try:
        db.execute("SELECT 1")
        ready.set()
        done.wait(20)
    finally:
        db.close()


def _try_rw(path: str, ready, q) -> None:
    import time

    import duckdb

    ready.wait(10)
    time.sleep(0.15)
    try:
        con = duckdb.connect(path, read_only=False)
        con.execute("SELECT 1")
        con.close()
        q.put("ok")
    except Exception as exc:  # noqa: BLE001
        q.put(f"fail:{type(exc).__name__}:{exc}")


def test_ephemeral_ro_allows_other_process_rw(tmp_path: Path) -> None:
    path = str(tmp_path / "hub.duckdb")
    import duckdb

    con = duckdb.connect(path)
    con.execute("CREATE TABLE t(x INT)")
    con.close()

    from duckclaw import DuckClaw

    db = DuckClaw(path, read_only=True, engine="python")
    assert getattr(db, "_ephemeral_ro", False) is True
    assert db._con is None
    assert db.execute("SELECT 1") == [(1,)]
    assert db._con is None

    ready = multiprocessing.Event()
    done = multiprocessing.Event()
    q: multiprocessing.Queue = multiprocessing.Queue()
    # Hold "logical" RO DuckClaw in child while parent opens RW — child must not
    # keep a persistent lock between ops; keep one query in flight only briefly.
    p = multiprocessing.Process(target=_hold_ro, args=(path, ready, done))
    p.start()
    ready.wait(10)
    # While child has DuckClaw RO object alive, RW must still succeed because
    # ephemeral mode does not hold the file lock between ops.
    rw = duckdb.connect(path, read_only=False)
    rw.execute("INSERT INTO t VALUES (1)")
    rw.close()
    done.set()
    p.join(10)
    assert p.exitcode == 0

    db.close()
