"""Transversal HITL service for ``main.code_decisions`` approve/reject flows."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from duckclaw.github.mcp_bridge import (
    compose_github_stdio_server_params,
    github_runtime_owner_repo,
    reject_protected_branch_mutation,
)
from duckclaw.hitl.db_access import _query_rows, table_exists
from duckclaw.write_commands import UpdateCodeDecisionStatusCommand

_log = logging.getLogger(__name__)

_CODE_DECISIONS_TABLE = "code_decisions"
_GITHUB_MCP_WRITABLE = False


def _run_async(coro: Any) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _github_mcp_call(tool_name: str, payload: dict[str, Any]) -> str:
    token = (os.environ.get("GITHUB_TOKEN") or "").strip()
    if not token:
        return json.dumps({"error": "GITHUB_TOKEN missing"})
    branch_err = reject_protected_branch_mutation(tool_name, payload)
    if branch_err:
        return json.dumps({"error": branch_err})
    from duckclaw.forge.skills.mcp_stdio_util import mcp_stdio_call_tool

    server_params = compose_github_stdio_server_params(token, read_only=_GITHUB_MCP_WRITABLE)

    async def _call() -> str:
        return await mcp_stdio_call_tool(server_params, tool_name, payload)

    return _run_async(_call())


def _infer_user_id_for_queue(db_path: str) -> str:
    parts = Path(db_path).expanduser().resolve().parts
    if "private" in parts:
        idx = parts.index("private")
        if idx + 1 < len(parts):
            return str(parts[idx + 1])
    return "default"


def _release_ro_handle_for_writer(db: Any) -> tuple[bool, Any]:
    release = getattr(db, "release_file_handle_for_external_writer", None)
    suspend = getattr(db, "suspend_readonly_file_handle", None)
    resume = getattr(db, "resume_readonly_file_handle", None)
    if callable(release):
        release()
        return bool(callable(resume)), resume
    if callable(suspend) and callable(resume):
        suspend()
        return True, resume
    return False, resume


def _enqueue_hitl_command(db: Any, command: UpdateCodeDecisionStatusCommand) -> None:
    from duckclaw.db_write_fire_and_forget import (
        enqueue_write_and_resolve,
        write_poll_timeout_sec,
    )

    raw_path = str(getattr(db, "_path", "") or "").strip()
    if not raw_path or raw_path == ":memory:":
        raise RuntimeError("vault db path required for HITL mutation")
    resolved = str(Path(raw_path).expanduser().resolve())
    user_id = _infer_user_id_for_queue(resolved)
    released_ro, resume = _release_ro_handle_for_writer(db)
    try:
        ok, err = enqueue_write_and_resolve(command, db_path=resolved, user_id=user_id)
        if not ok and write_poll_timeout_sec() > 0:
            raise RuntimeError(err or "code decision write failed")
    finally:
        if released_ro and callable(resume):
            try:
                resume()
            except Exception:
                pass


def _apply_status_update_rw(db: Any, command: UpdateCodeDecisionStatusCommand) -> None:
    from duckclaw.write_command_handlers import dispatch_command

    dispatch_command(db, command.model_dump())


def _persist_status(db: Any, command: UpdateCodeDecisionStatusCommand) -> None:
    if bool(getattr(db, "_read_only", False)):
        _enqueue_hitl_command(db, command)
        return
    _apply_status_update_rw(db, command)


def fetch_code_decision_row(db: Any, decision_id: str) -> dict[str, Any] | None:
    did = (decision_id or "").strip()
    if not did or not table_exists(db, _CODE_DECISIONS_TABLE):
        return None
    rows = _query_rows(
        db,
        """
        SELECT id, repo, file_path, branch_name, proposed_change, title, rationale, status, pr_url
        FROM main.code_decisions
        WHERE id = ?
        LIMIT 1
        """,
        (did,),
    )
    return rows[0] if rows else None


def approve_code_decision(
    db: Any,
    *,
    decision_id: str,
    tenant_id: str,
    user_id: str,
    chat_id: str = "",
) -> dict[str, Any]:
    """Approve a PENDING_HITL code decision and open a GitHub PR when configured."""
    row = fetch_code_decision_row(db, decision_id)
    if row is None:
        return {"error": f"decision_id {decision_id} no encontrado"}

    status = str(row.get("status") or "").upper()
    if status not in ("PENDING_HITL", "APPROVED"):
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
            f"PR generado por DuckClaw HITL.\n\n"
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
        url_match = re.search(r"https://github\.com/\S+", pr_raw)
        if url_match:
            pr_url = url_match.group(0)

    command = UpdateCodeDecisionStatusCommand(
        tenant_id=tenant_id or "default",
        actor_email=f"chat:{chat_id}" if chat_id else user_id or "system",
        decision_id=decision_id,
        status="APPROVED",
        pr_url=pr_url,
        pr_number=int(pr_number) if pr_number else None,
        rationale=rationale,
        resolved_by=user_id or tenant_id or "system",
    )
    try:
        _persist_status(db, command)
    except Exception as exc:
        _log.exception("persist approved code decision failed")
        return {"error": str(exc), "stage": "persist", "pr_url": pr_url}

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
    chat_id: str = "",
) -> dict[str, Any]:
    """Reject a PENDING_HITL code decision."""
    row = fetch_code_decision_row(db, decision_id)
    if row is None:
        return {"error": f"decision_id {decision_id} no encontrado", "status": "FAILED"}
    if str(row.get("status") or "").upper() != "PENDING_HITL":
        return {"error": f"status inválido para rechazar: {row.get('status')}", "status": "FAILED"}

    command = UpdateCodeDecisionStatusCommand(
        tenant_id=tenant_id or "default",
        actor_email=f"chat:{chat_id}" if chat_id else user_id or "system",
        decision_id=decision_id,
        status="REJECTED",
        rationale=rationale or "rejected by operator",
        resolved_by=user_id or tenant_id or "system",
    )
    try:
        _persist_status(db, command)
    except Exception as exc:
        _log.exception("persist rejected code decision failed")
        return {"status": "FAILED", "decision_id": decision_id, "error": str(exc)}
    return {"status": "REJECTED", "decision_id": decision_id}
