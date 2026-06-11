"""
Backend soberano: aprueba code_decisions y crea PR en GitHub tras HITL.

Econofísica: la mutación del repositorio es un evento discreto autorizado por el humano,
no una fluctuación espontánea del LLM.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from typing import Any

from duckclaw.forge.skills.github_bridge import (
    compose_github_stdio_server_params,
    github_runtime_owner_repo,
    reject_protected_branch_mutation,
)
from duckclaw.forge.skills.mcp_stdio_util import mcp_stdio_call_tool
from duckclaw.forge.skills.quant_state_delta import push_quant_state_delta_sync

_log = logging.getLogger(__name__)


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _fetch_decision_row(db: Any, decision_id: str) -> dict[str, Any] | None:
    did = (decision_id or "").strip()
    if not did:
        return None
    try:
        rows = db.query(
            """
            SELECT id, repo, file_path, branch_name, proposed_change, title, rationale, status
            FROM quant_core.code_decisions
            WHERE id = ?
            LIMIT 1
            """,
            (did,),
        )
        if isinstance(rows, str):
            parsed = json.loads(rows)
            items = parsed if isinstance(parsed, list) else parsed.get("rows") or []
        elif isinstance(rows, list):
            items = rows
        else:
            items = []
        if not items:
            return None
        row = items[0]
        if isinstance(row, dict):
            return row
        return {
            "id": row[0],
            "repo": row[1],
            "file_path": row[2],
            "branch_name": row[3],
            "proposed_change": row[4],
            "title": row[5],
            "rationale": row[6],
            "status": row[7],
        }
    except Exception:
        _log.exception("fetch code_decision failed")
        return None


def _github_mcp_call(tool_name: str, payload: dict[str, Any]) -> str:
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return json.dumps({"error": "GITHUB_TOKEN missing"})
    branch_err = reject_protected_branch_mutation(tool_name, payload)
    if branch_err:
        return json.dumps({"error": branch_err})
    server_params = compose_github_stdio_server_params(token, read_only=False)

    async def _call() -> str:
        return await mcp_stdio_call_tool(server_params, tool_name, payload)

    return _run_async(_call())


def approve_code_decision(
    db: Any,
    *,
    decision_id: str,
    tenant_id: str,
    user_id: str,
    chat_id: str = "",
) -> dict[str, Any]:
    """
    Crea rama + archivo + PR para una decisión PENDING_HITL.
    """
    row = _fetch_decision_row(db, decision_id)
    if row is None:
        return {"error": f"decision_id {decision_id} no encontrado"}
    if str(row.get("status") or "").upper() not in ("PENDING_HITL", "APPROVED"):
        return {"error": f"status inválido para aprobar: {row.get('status')}"}

    owner, repo_env = github_runtime_owner_repo()
    if not owner or not repo_env:
        return {"error": "GITHUB_OWNER/GITHUB_REPO no configurados"}

    branch = str(row.get("branch_name") or "").strip()
    if branch.lower() in ("main", "master"):
        return {"error": "branch_name protegida"}

    file_path = str(row.get("file_path") or "").strip()
    content = str(row.get("proposed_change") or "")
    title = str(row.get("title") or f"fix: {file_path}")
    rationale = str(row.get("rationale") or "")

    push_payload = {
        "owner": owner,
        "repo": repo_env,
        "branch": branch,
        "files": [{"path": file_path, "content": content}],
        "message": f"{title}\n\n{rationale}"[:500],
    }
    push_raw = _github_mcp_call("push_files", push_payload)
    if "error" in push_raw.lower():
        try:
            parsed = json.loads(push_raw)
            if parsed.get("error"):
                return {"error": parsed["error"], "stage": "push_files"}
        except json.JSONDecodeError:
            return {"error": push_raw[:500], "stage": "push_files"}

    pr_payload = {
        "owner": owner,
        "repo": repo_env,
        "title": title[:200],
        "head": branch,
        "base": "main",
        "body": (
            f"PR generado por DuckClaw CodeDecisionService.\n\n"
            f"**Archivo:** `{file_path}`\n\n"
            f"**Rationale:** {rationale}"
        ),
    }
    pr_raw = _github_mcp_call("create_pull_request", pr_payload)
    pr_number = None
    pr_url = ""
    try:
        pr_parsed = json.loads(pr_raw)
        if isinstance(pr_parsed, dict):
            pr_number = pr_parsed.get("number") or pr_parsed.get("pr_number")
            pr_url = (
                pr_parsed.get("html_url")
                or pr_parsed.get("url")
                or (pr_parsed.get("content") or {}).get("html_url")
                or ""
            )
            if not pr_url and pr_number:
                pr_url = f"https://github.com/{owner}/{repo_env}/pull/{pr_number}"
    except json.JSONDecodeError:
        url_m = re.search(r"https://github\.com/\S+", pr_raw)
        if url_m:
            pr_url = url_m.group(0)

    db_path = str(getattr(db, "_path", "") or "")
    push_quant_state_delta_sync(
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "target_db_path": db_path,
            "delta_type": "CODE_DECISION_APPROVED",
            "mutation": {
                "id": decision_id,
                "pr_number": int(pr_number) if pr_number else None,
                "pr_url": pr_url,
            },
        },
        duckclaw_db=db,
    )

    return {
        "status": "APPROVED",
        "decision_id": decision_id,
        "pr_number": pr_number,
        "pr_url": pr_url,
        "branch": branch,
        "chat_id": chat_id,
    }


def reject_code_decision(
    db: Any,
    *,
    decision_id: str,
    tenant_id: str,
    user_id: str,
    rationale: str = "",
) -> dict[str, Any]:
    """Marca decisión como REJECTED."""
    db_path = str(getattr(db, "_path", "") or "")
    ok = push_quant_state_delta_sync(
        {
            "tenant_id": tenant_id,
            "user_id": user_id,
            "target_db_path": db_path,
            "delta_type": "CODE_DECISION_REJECTED",
            "mutation": {"id": decision_id, "rationale": rationale or "rejected by admin"},
        },
        duckclaw_db=db,
    )
    return {"status": "REJECTED" if ok else "FAILED", "decision_id": decision_id}
