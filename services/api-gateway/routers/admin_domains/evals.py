"""Evals tab: what the golden suites (duckclaw.evals.golden_suite.record_run) reported, newest runs per suite, with what regressed since the run before."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query

from routers.admin_domains.admin_common import require_admin_key

router = APIRouter(prefix="/evals", tags=["admin-evals"])


def summarize(rows: list[dict[str, Any]], runs_per_suite: int = 30) -> list[dict[str, Any]]:
    """``rows``: ``admin_runtime_settings`` rows of domain ``evals``. One entry per suite: the newest run in full, a short history, and its regressions
    (cases that were ``always_pass`` in the run before and are not any more, a dropped case included)."""
    by_suite: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        raw = row.get("value_json") or row.get("value_text") or ""
        try:
            run = json.loads(raw) if isinstance(raw, str) else raw
        except json.JSONDecodeError:
            continue
        if isinstance(run, dict) and run.get("suite") and isinstance(run.get("cases"), dict):
            by_suite.setdefault(str(run["suite"]), []).append(run)
    out = []
    for suite, runs in sorted(by_suite.items()):
        runs.sort(key=lambda r: str(r.get("ts") or ""), reverse=True)
        runs = runs[:runs_per_suite]

        def counts(run: dict[str, Any]) -> dict[str, int]:
            cases = run["cases"].values()
            return {"total": len(run["cases"]), **{s: sum(1 for c in cases if c.get("status") == s) for s in ("always_pass", "flaky", "always_fail")}}

        latest, before = runs[0], (runs[1] if len(runs) > 1 else None)
        regressed = sorted(cid for cid, b in ((before or {}).get("cases") or {}).items()
                           if b.get("status") == "always_pass" and (latest["cases"].get(cid) or {}).get("status") != "always_pass")
        def by_type(run: dict[str, Any] | None) -> dict[str, tuple[int, int]]:
            acc: dict[str, list[int]] = {}
            for c in ((run or {}).get("cases") or {}).values():
                t = acc.setdefault(str(c.get("type") or "?"), [0, 0])
                t[0] += c.get("status") == "always_pass"
                t[1] += 1
            return {k: (v[0], v[1]) for k, v in acc.items()}

        now_t, prev_t = by_type(latest), by_type(before)
        types = [{"type": t, "passing": p, "total": n, "prev_passing": prev_t[t][0] if t in prev_t else None, "prev_total": prev_t[t][1] if t in prev_t else None}
                 for t, (p, n) in sorted(now_t.items())]
        out.append({"suite": suite, "by_type": types, "latest": {"ts": latest.get("ts"), "model": latest.get("model", ""), "cases": latest["cases"], **counts(latest)}, "regressed": regressed,
                    "history": [{"ts": r.get("ts"), "model": r.get("model", ""), **counts(r)} for r in runs]})
    return out


# ponytail: one run at a time per suite, tracked in this process (a gateway restart forgets it; the job itself keeps going).
_RUNNING: dict[str, subprocess.Popen] = {}


def runnable() -> dict[str, dict[str, Any]]:
    """Suites the tab may start: ``DUCKCLAW_EVAL_COMMANDS`` = JSON ``{"suite": {"argv": [...], "cwd": "..."}}``. Never a command from the request."""
    try:
        cfg = json.loads(os.environ.get("DUCKCLAW_EVAL_COMMANDS") or "{}")
    except json.JSONDecodeError:
        return {}
    return {k: v for k, v in cfg.items() if isinstance(v, dict) and isinstance(v.get("argv"), list) and v["argv"]}


def is_running(suite: str) -> bool:
    p = _RUNNING.get(suite)
    return p is not None and p.poll() is None


@router.post("/{suite}/run", dependencies=[Depends(require_admin_key)], status_code=202)
async def run_eval_suite(suite: str) -> dict[str, Any]:
    cmd = runnable().get(suite)
    if cmd is None:
        raise HTTPException(404, "suite is not runnable from the admin")
    if is_running(suite):
        raise HTTPException(409, "suite is already running")
    _RUNNING[suite] = subprocess.Popen([str(a) for a in cmd["argv"]], cwd=cmd.get("cwd") or None, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL, start_new_session=True)
    return {"accepted": True, "suite": suite}


@router.get("/runs", dependencies=[Depends(require_admin_key)])
async def get_eval_runs(limit: int = Query(200, ge=1, le=1000)) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.shared_db_grants import _query_all_dicts

    def _read() -> list[dict[str, Any]]:
        with open_gateway_db(read_only=True) as db:
            return _query_all_dicts(
                db, "SELECT key, value_json, value_text FROM main.admin_runtime_settings "
                    f"WHERE active = true AND domain = 'evals' ORDER BY updated_at DESC LIMIT {int(limit)}")

    try:
        suites = summarize(await asyncio.to_thread(_read))
    except FileNotFoundError:
        suites = []
    have = {s["suite"] for s in suites}
    suites += [{"suite": k, "latest": None, "regressed": [], "history": [], "by_type": []} for k in runnable() if k not in have]   # never run yet: still offer the button
    for s in suites:
        s["runnable"], s["running"] = s["suite"] in runnable(), is_running(s["suite"])
    return {"suites": suites}
