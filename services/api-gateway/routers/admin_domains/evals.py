"""Evals tab: what the golden suites (duckclaw.evals.golden_suite.record_run) reported, newest runs per suite, with what regressed since the run before."""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time
from datetime import date, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from routers.admin_domains.admin_common import actor_from_header, require_admin_key

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
        for c in latest["cases"].values():   # failure x consequence: a high-severity failure is fixed now, the rest can wait (low alone does not even alert)
            c["priority"] = "" if c.get("status") == "always_pass" else "fix_now" if c.get("severity") == "high" else "improve_later"
        regressed = sorted(cid for cid, b in ((before or {}).get("cases") or {}).items()
                           if b.get("status") == "always_pass" and (latest["cases"].get(cid) or {}).get("status") != "always_pass")
        def by_type(run: dict[str, Any] | None) -> dict[str, tuple[int, int]]:
            acc: dict[str, list[int]] = {}
            for c in ((run or {}).get("cases") or {}).values():
                t = acc.setdefault(str(c.get("type") or "?"), [0, 0])
                t[0] += c.get("status") == "always_pass"
                t[1] += 1
            return {k: (v[0], v[1]) for k, v in acc.items()}

        def by_requirement(run: dict[str, Any]) -> list[dict[str, Any]]:
            """Each requirement the run declared with its cases (a requirement with none is a gap), plus the cases that name one it does not declare."""
            reqs = {str(r["id"]): {"id": str(r["id"]), "text": r.get("text", ""), "question": r.get("question", "")} for r in run.get("requirements") or [] if r.get("id")}
            for c in run["cases"].values():
                if c.get("requirement"):
                    reqs.setdefault(str(c["requirement"]), {"id": str(c["requirement"]), "text": "", "question": ""})
            return [{**r, "cases": sorted(cid for cid, c in run["cases"].items() if c.get("requirement") == r["id"]),
                     "failing": sorted(cid for cid, c in run["cases"].items() if c.get("requirement") == r["id"] and c.get("status") != "always_pass")}
                    for r in reqs.values()]

        def by_difficulty(run: dict[str, Any]) -> dict[str, list[int]]:
            acc: dict[str, list[int]] = {}
            for c in run["cases"].values():
                a = acc.setdefault(str(c.get("difficulty") or "?"), [0, 0])
                a[0] += c.get("status") == "always_pass"
                a[1] += 1
            return acc

        def review_due(run: dict[str, Any]) -> list[str]:
            """Cases nobody has reviewed in 90 days (or ever): the benchmark is curated, not write-once."""
            try:
                today = datetime.fromisoformat(str(run.get("ts") or "").replace("Z", "+00:00")).date()
            except ValueError:
                return []
            due = []
            for cid, c in run["cases"].items():
                try:
                    stale = (today - date.fromisoformat(str(c.get("reviewed") or ""))).days > 90
                except ValueError:
                    stale = True
                if stale:
                    due.append(cid)
            return sorted(due)

        now_t, prev_t = by_type(latest), by_type(before)
        types = [{"type": t, "passing": p, "total": n, "prev_passing": prev_t[t][0] if t in prev_t else None, "prev_total": prev_t[t][1] if t in prev_t else None}
                 for t, (p, n) in sorted(now_t.items())]
        out.append({"suite": suite, "by_type": types, "by_difficulty": by_difficulty(latest), "review_due": review_due(latest), "requirements": by_requirement(latest) if latest.get("requirements") or any(c.get("requirement") for c in latest["cases"].values()) else [], "latest": {"ts": latest.get("ts"), "model": latest.get("model", ""), "cases": latest["cases"], **counts(latest)}, "regressed": regressed,
                    "edited": sorted(cid for cid in regressed if (b := ((before or {}).get("cases") or {}).get(cid, {}).get("hash")) and b != (latest["cases"].get(cid) or {}).get("hash")),   # the case itself changed since the run before: read the regression with that in mind
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


class ReviewBody(BaseModel):
    """What a person wrote after reading a failed case: the finding, an explanation not yet checked, and the verdict."""

    note: str = Field("", max_length=2000)
    possibility: str = Field("", max_length=1000)
    verdict: str = Field("", pattern="^(pass|fail|unsure|)$")


@router.put("/{suite}/notes/{case_id}", dependencies=[Depends(require_admin_key)])
async def put_case_review(suite: str, case_id: str, body: ReviewBody, actor: str = Depends(actor_from_header)) -> dict[str, Any]:
    from duckclaw.db_write_queue import enqueue_typed_command
    from duckclaw.gateway_db import get_gateway_db_path
    from duckclaw.write_commands import UpsertRuntimeSettingCommand

    if not (0 < len(suite) <= 64 and 0 < len(case_id) <= 128) or ":" in suite:
        raise HTTPException(422, "bad suite or case id")
    payload = {**body.model_dump(), "by": actor, "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    cmd = UpsertRuntimeSettingCommand(tenant_id="global", actor_email=actor, domain="eval_notes", key=f"{suite}:{case_id}", value="", value_json=payload,
                                      value_kind="json", secret=False, updated_by=actor)
    task_id = await asyncio.to_thread(enqueue_typed_command, cmd, db_path=str(get_gateway_db_path()), user_id=actor)
    return {"ok": True, "queued": True, "task_id": task_id}


def attach_reviews(suites: list[dict[str, Any]], rows: list[dict[str, Any]]) -> None:
    """Put each saved review (``eval_notes`` rows, key ``suite:case``) on its case of the newest run."""
    notes: dict[str, Any] = {}
    for r in rows:
        if r.get("domain") == "eval_notes":
            raw = r.get("value_json") or ""
            try:
                notes[str(r.get("key"))] = json.loads(raw) if isinstance(raw, str) else raw
            except json.JSONDecodeError:
                continue
    for s in suites:
        for cid, c in ((s.get("latest") or {}).get("cases") or {}).items():
            if f"{s['suite']}:{cid}" in notes:
                c["review"] = notes[f"{s['suite']}:{cid}"]


@router.get("/runs", dependencies=[Depends(require_admin_key)])
async def get_eval_runs(limit: int = Query(200, ge=1, le=1000)) -> dict[str, Any]:
    from core.admin_identity import open_gateway_db
    from duckclaw.shared_db_grants import _query_all_dicts

    def _read() -> list[dict[str, Any]]:
        with open_gateway_db(read_only=True) as db:
            return _query_all_dicts(
                db, "SELECT domain, key, value_json, value_text FROM main.admin_runtime_settings "
                    f"WHERE active = true AND domain IN ('evals', 'eval_notes') ORDER BY updated_at DESC LIMIT {int(limit)}")

    try:
        rows = await asyncio.to_thread(_read)
        suites = summarize([r for r in rows if r.get("domain") == "evals"])
        attach_reviews(suites, rows)
    except FileNotFoundError:
        suites = []
    have = {s["suite"] for s in suites}
    suites += [{"suite": k, "latest": None, "regressed": [], "history": [], "by_type": [], "by_difficulty": {}, "review_due": [], "requirements": []} for k in runnable() if k not in have]   # never run yet: still offer the button
    for s in suites:
        s["runnable"], s["running"] = s["suite"] in runnable(), is_running(s["suite"])
    return {"suites": suites}
