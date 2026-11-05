"""Evals tab: what the golden suites (duckclaw.evals.golden_suite.record_run) reported, newest runs per suite, with what regressed since the run before."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, Query

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
        out.append({"suite": suite, "latest": {"ts": latest.get("ts"), "model": latest.get("model", ""), "cases": latest["cases"], **counts(latest)}, "regressed": regressed,
                    "history": [{"ts": r.get("ts"), "model": r.get("model", ""), **counts(r)} for r in runs]})
    return out


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
        return {"suites": summarize(await asyncio.to_thread(_read))}
    except FileNotFoundError:
        return {"suites": []}
