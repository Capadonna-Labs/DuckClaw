"""Etiquetas de subagentes según instancias activas (manager → worker)."""

import pytest

from duckclaw.graphs import subagent_run_id as m


def test_acquire_release_reuses_label_one_at_a_time(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("DUCKCLAW_REDIS_URL", raising=False)
    tid = f"tenant-{id(monkeypatch)}"
    w = "BI-Analyst"
    t1, n1 = m.acquire_subagent_slot(tid, w)
    assert n1 == 1
    assert m.active_subagent_label(tid, w, t1) == 1
    m.release_subagent_slot(tid, w, t1)
    t2, n2 = m.acquire_subagent_slot(tid, w)
    assert n2 == 1
    m.release_subagent_slot(tid, w, t2)


def test_two_active_labels_one_and_two(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("DUCKCLAW_REDIS_URL", raising=False)
    tid = f"tenant-{id(monkeypatch)}"
    w = "BI-Analyst"
    ta, na = m.acquire_subagent_slot(tid, w)
    tb, nb = m.acquire_subagent_slot(tid, w)
    assert na >= 1 and nb >= 1
    assert {na, nb} == {1, 2}
    labels_now = {m.active_subagent_label(tid, w, ta), m.active_subagent_label(tid, w, tb)}
    assert labels_now == {1, 2}
    m.release_subagent_slot(tid, w, ta)
    assert m.active_subagent_label(tid, w, tb) == 1
    m.release_subagent_slot(tid, w, tb)


def test_acquire_release_releases_wrong_token_safe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("DUCKCLAW_REDIS_URL", raising=False)
    tid = "t"
    m.release_subagent_slot(tid, "w", "")
    m.release_subagent_slot(tid, "w", "not-there")


def test_same_chat_parallel_one_and_two(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("DUCKCLAW_REDIS_URL", raising=False)
    tid = f"tenant-{id(monkeypatch)}"
    w = "BI-Analyst"
    cid = "1726618406"
    ta, na = m.acquire_subagent_slot(tid, w, cid)
    tb, nb = m.acquire_subagent_slot(tid, w, cid)
    assert {na, nb} == {1, 2}
    m.release_subagent_slot(tid, w, ta, cid)
    assert m.active_subagent_label(tid, w, tb, cid) == 1
    m.release_subagent_slot(tid, w, tb, cid)
    tc, nc = m.acquire_subagent_slot(tid, w, cid)
    assert nc == 1
    m.release_subagent_slot(tid, w, tc, cid)


def test_different_chats_independent_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("DUCKCLAW_REDIS_URL", raising=False)
    tid = f"tenant-{id(monkeypatch)}"
    w = "BI-Analyst"
    ta, na = m.acquire_subagent_slot(tid, w, "111")
    tb, nb = m.acquire_subagent_slot(tid, w, "222")
    assert na == 1 and nb == 1
    m.release_subagent_slot(tid, w, ta, "111")
    m.release_subagent_slot(tid, w, tb, "222")
