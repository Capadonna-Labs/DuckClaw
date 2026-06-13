"""Deterministic GitHub PR workflow for worker tool orchestration."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable

_log = logging.getLogger(__name__)


def _default_identity_fields(state: dict) -> dict:
    return {
        "chat_id": state.get("chat_id") or state.get("session_id"),
        "tenant_id": state.get("tenant_id") or "default",
        "user_id": state.get("user_id") or "",
        "username": (state.get("username") or "").strip(),
        "vault_db_path": state.get("vault_db_path") or "",
    }

def _user_requests_github_pr(text: str) -> bool:
    """Usuario pide abrir/montar PR o patch vía GitHub."""
    if not text or not str(text).strip():
        return False
    low = text.strip().lower()
    if "[system_directive:" in low or "[system_event:" in low:
        return False
    if re.search(r"\b(create|crea(r|)\s+un?\s*)?pull\s*request\b", low):
        return True
    if re.search(r"\bmerge\s+request\b", low):
        return True
    if re.search(
        r"\b(intenta(r|)|monta(r|)|abre(r|)|crea(r|)|sube(r|)|haz(me)?)\b", low
    ) and re.search(r"\b(pr|pull\s*request|patch)\b", low):
        return True
    if re.search(r"\b(sigue|continua|continúa|retoma|prosigue)\b", low) and re.search(
        r"\b(pr|pull\s*request)\b", low
    ):
        return True
    if re.search(r"\bretroalimentaci[oó]n\b", low) and re.search(r"\bpr\b", low):
        return True
    return False


_GITHUB_DEFAULT_OWNER = ""  # debe definirse vía entorno o variable
_GITHUB_DEFAULT_REPO = "DuckClaw"
_GITHUB_REFS_HEADS_PREFIX = "refs/heads/"


def _github_tool_message_fields(msg: Any) -> tuple[str, str] | None:
    """Nombre y contenido de ToolMessage (LangChain o dict serializado)."""
    from langchain_core.messages import ToolMessage

    if isinstance(msg, ToolMessage):
        return str(getattr(msg, "name", "") or ""), str(getattr(msg, "content", "") or "")
    if isinstance(msg, dict):
        role = str(msg.get("role") or msg.get("type") or "").lower()
        if role not in ("tool", "toolmessage"):
            return None
        return str(msg.get("name") or ""), str(msg.get("content") or "")
    msg_type = str(getattr(msg, "type", "") or "").lower()
    if msg_type == "tool":
        return str(getattr(msg, "name", "") or ""), str(getattr(msg, "content", "") or "")
    return None


def _github_tool_called_since(messages: list[Any], from_idx: int, tool_name: str) -> bool:
    for i, msg in enumerate(messages[max(0, from_idx + 1) :]):
        fields = _github_tool_message_fields(msg)
        if fields and fields[0] == tool_name:
            return True
    return False


def _github_parse_push_files_success(content: str) -> tuple[str, str, str] | None:
    """Extrae owner, repo y rama de la respuesta JSON de push_files."""
    raw = str(content or "").strip()
    if not raw or raw.startswith("failed"):
        return None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict):
        return None
    ref = str(payload.get("ref") or "").strip()
    if not ref.startswith(_GITHUB_REFS_HEADS_PREFIX):
        return None
    head = ref[len(_GITHUB_REFS_HEADS_PREFIX) :].strip()
    if not head:
        return None
    owner = _GITHUB_DEFAULT_OWNER
    repo = _GITHUB_DEFAULT_REPO
    url = str(payload.get("url") or "")
    m = re.search(r"github\.com/repos/([^/]+)/([^/]+)/", url, re.IGNORECASE)
    if m:
        owner = m.group(1)
        repo = m.group(2)
    return owner, repo, head


def _github_pr_title_from_branch(branch: str) -> str:
    """Título legible a partir del nombre de rama."""
    slug = str(branch or "").strip().split("/")[-1]
    slug = slug.replace("-", " ").replace("_", " ").strip()
    if not slug:
        return "DuckClaw PR"
    return slug[0].upper() + slug[1:] if len(slug) > 1 else slug.upper()


def _github_extract_open_pr_url(content: str) -> str | None:
    """URL de PR abierto desde list_pull_requests / pull_request_read."""
    raw = str(content or "").strip()
    if not raw or raw.startswith("failed"):
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"https://github\.com/[^\s\"']+/pull/\d+", raw, re.IGNORECASE)
        return m.group(0) if m else None
    if isinstance(data, dict):
        for key in ("html_url", "url"):
            url = str(data.get(key) or "")
            if "/pull/" in url:
                return url
    if isinstance(data, list):
        for item in data:
            if not isinstance(item, dict):
                continue
            state = str(item.get("state") or "open").lower()
            if state not in ("open", ""):
                continue
            url = str(item.get("html_url") or item.get("url") or "")
            if "/pull/" in url:
                return url
    return None


def _github_infer_feature_branch(messages: list[Any]) -> str | None:
    """Rama feat/* candidata desde list_branches (historial sin push_files)."""
    raw = None
    for msg in reversed(messages or []):
        fields = _github_tool_message_fields(msg)
        if fields and fields[0] == "list_branches":
            raw = fields[1]
            break
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return None
    names: list[str] = []
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                name = str(item.get("name") or "").strip()
                if name and name not in ("main", "master"):
                    names.append(name)
    if not names:
        return None
    for prefer in ("feat/cancel-trade-signal-tool", "feat/cancel", "feat/"):
        for name in names:
            if name == prefer or name.startswith(prefer) or prefer.rstrip("/") in name:
                return name
    for name in names:
        if name.startswith("feat/"):
            return name
    return names[0]


_GITHUB_CANCEL_TRADE_SIGNAL_MANIFEST: tuple[str, ...] = (
    "packages/agents/src/duckclaw/forge/skills/quant_trade_signal_cancel.py",
    "packages/agents/src/duckclaw/forge/skills/quant_trader_bridge.py",
    "packages/agents/src/duckclaw/workers/factory.py",
    "tests/test_cancel_trade_signal_tool.py",
    "specs/features/platform/QUANT_TRADE_SIGNAL_CANCEL.md",
)


def _github_repo_root() -> Path:
    from duckclaw.forge.skills.telegram_mcp_bridge import infer_repo_root

    return infer_repo_root()


def _github_parse_pr_payload(content: str) -> list[dict[str, Any]]:
    raw = str(content or "").strip()
    if not raw or raw.startswith("failed"):
        return []
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        return [data]
    return []


def _github_pr_is_incomplete(pr: dict[str, Any]) -> bool:
    title = str(pr.get("title") or "").lower()
    body = str(pr.get("body") or "").lower()
    if "partial" in title:
        return True
    if "follow-up commits should add" in body:
        return True
    if "only `" in body and "was pushed" in body:
        return True
    return False


def _github_select_incomplete_feature_pr(prs: list[dict[str, Any]]) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for pr in prs:
        if str(pr.get("state") or "open").lower() not in ("open", ""):
            continue
        if not _github_pr_is_incomplete(pr):
            continue
        candidates.append(pr)
    if not candidates:
        return None
    for pr in candidates:
        head = str((pr.get("head") or {}).get("ref") or "")
        if "cancel" in head.lower():
            return pr
    return candidates[0]


def _github_incomplete_pr_in_recent_tools(
    messages: list[Any],
    from_idx: int,
) -> dict[str, Any] | None:
    for msg in reversed(messages[max(0, from_idx + 1) :]):
        fields = _github_tool_message_fields(msg)
        if not fields:
            continue
        tname, tcontent = fields
        if tname not in ("list_pull_requests", "pull_request_read"):
            continue
        pr = _github_select_incomplete_feature_pr(_github_parse_pr_payload(tcontent))
        if pr:
            return pr
    return None


def _github_collect_local_push_files(
    rel_paths: tuple[str, ...] | None = None,
) -> tuple[list[dict[str, str]], list[str]]:
    root = _github_repo_root()
    paths = rel_paths or _GITHUB_CANCEL_TRADE_SIGNAL_MANIFEST
    files: list[dict[str, str]] = []
    missing: list[str] = []
    for rel in paths:
        p = root / rel
        if p.is_file():
            try:
                files.append({"path": rel, "content": p.read_text(encoding="utf-8")})
            except OSError:
                missing.append(rel)
        else:
            missing.append(rel)
    return files, missing


def _github_build_forced_push_files_tool_call(
    owner: str,
    repo: str,
    branch: str,
    files: list[dict[str, str]],
    message: str,
) -> tuple[Any, list[dict[str, Any]]]:
    from langchain_core.messages import AIMessage

    forced_tid = f"call_github_push_files_{int(time.time() * 1000)}"
    forced_tc = [
        {
            "name": "push_files",
            "args": {
                "owner": owner,
                "repo": repo,
                "branch": branch,
                "files": files,
                "message": message,
            },
            "id": forced_tid,
            "type": "tool_call",
        }
    ]
    return AIMessage(content="", tool_calls=forced_tc), forced_tc


def _github_resolve_feature_branch(messages: list[Any]) -> str | None:
    """Rama del feature en curso (list_branches / PR head / default cancel)."""
    incomplete = _github_incomplete_pr_in_recent_tools(messages, -1)
    if incomplete:
        head = str((incomplete.get("head") or {}).get("ref") or "").strip()
        if head:
            return head
    inferred = _github_infer_feature_branch(messages)
    if inferred:
        return inferred
    files, _ = _github_collect_local_push_files()
    if files:
        return "feat/cancel-trade-signal-tool"
    return None


def _github_build_pr_completion_response(
    pr_url: str,
    *,
    head: str,
    missing_local: list[str] | None = None,
    files_pushed: list[str] | None = None,
) -> str:
    gaps = ""
    if missing_local:
        gaps = f"\nArchivos no encontrados en workspace: {', '.join(missing_local[:8])}"
    pushed = ""
    if files_pushed:
        pushed = "\nArchivos pusheados:\n" + "\n".join(f"- `{p}`" for p in files_pushed[:12])
    return (
        f"PR actualizado: {pr_url}\n"
        f"Rama `{head}` — manifest cancel_trade_signal aplicado.{pushed}\n"
        f"Revisa el diff en GitHub y aprueba cuando esté listo.{gaps}"
    )


def _github_try_deterministic_pr_workflow(
    *,
    state: dict,
    incoming: str,
    tools_by_name: dict[str, Any],
    last_msg: Any,
    already_has_tool_result: bool,
    worker_label: str,
    identity_fields: Callable[[dict], dict] | None = None,
    is_cancel_signal_request: Callable[[str], bool] | None = None,
) -> dict | None:
    identity_fields = identity_fields or _default_identity_fields
    is_cancel_signal_request = is_cancel_signal_request or (lambda _text: False)
    """Pipeline PR determinista: list → completar parcial | URL | create_pull_request."""
    from langchain_core.messages import AIMessage, ToolMessage

    if "create_pull_request" not in tools_by_name and "push_files" not in tools_by_name:
        return None
    if is_cancel_signal_request(incoming):
        return None
    msgs = state.get("messages") or []
    if not _github_pr_workflow_resolved_intent(msgs, incoming):
        return None
    lh = _quant_last_human_index(msgs)

    if already_has_tool_result and last_msg is not None:
        fields = _github_tool_message_fields(last_msg)
        if fields:
            tname, tcontent = fields
            if tname in ("list_pull_requests", "pull_request_read"):
                incomplete_pr = _github_select_incomplete_feature_pr(
                    _github_parse_pr_payload(tcontent)
                )
                if incomplete_pr:
                    pr_url = str(incomplete_pr.get("html_url") or "")
                    head = str((incomplete_pr.get("head") or {}).get("ref") or "")
                    owner, repo = _GITHUB_DEFAULT_OWNER, _GITHUB_DEFAULT_REPO
                    if (
                        head
                        and "push_files" in tools_by_name
                        and not _github_tool_called_since(msgs, lh, "push_files")
                    ):
                        files_payload, missing = _github_collect_local_push_files()
                        if files_payload:
                            _log.info(
                                "[%s] github deterministic stage=push_files_complete_partial_pr "
                                "head=%s files=%d missing=%d",
                                worker_label,
                                head,
                                len(files_payload),
                                len(missing),
                            )
                            # region agent log
                            # endregion
                            forced_resp, _ = _github_build_forced_push_files_tool_call(
                                owner,
                                repo,
                                head,
                                files_payload,
                                (
                                    "feat(quant): complete cancel_trade_signal — "
                                    "skill module, bridge, factory, spec, tests"
                                ),
                            )
                            out = {**state, "messages": msgs + [forced_resp]}
                            out.update(identity_fields(state))
                            return out
                    if pr_url and _github_tool_called_since(msgs, lh, "push_files"):
                        files_payload, missing = _github_collect_local_push_files()
                        resp = AIMessage(
                            content=_github_build_pr_completion_response(
                                pr_url,
                                head=head or "?",
                                missing_local=missing,
                                files_pushed=[f["path"] for f in files_payload],
                            )
                        )
                        out = {**state, "messages": msgs + [resp]}
                        out.update(identity_fields(state))
                        return out
                    if pr_url:
                        _, missing = _github_collect_local_push_files()
                        resp = AIMessage(
                            content=(
                                f"PR incompleto detectado: {pr_url}\n"
                                f"Faltaba completar el manifest local "
                                f"({'push_files no registrada' if 'push_files' not in tools_by_name else 'sin archivos en workspace'})."
                                f"{(' Missing: ' + ', '.join(missing[:6])) if missing else ''}"
                            )
                        )
                        out = {**state, "messages": msgs + [resp]}
                        out.update(identity_fields(state))
                        return out
                pr_url = _github_extract_open_pr_url(tcontent)
                if pr_url and not _github_select_incomplete_feature_pr(
                    _github_parse_pr_payload(tcontent)
                ):
                    # region agent log
                    # endregion
                    resp = AIMessage(content=f"PR abierto: {pr_url}")
                    out = {**state, "messages": msgs + [resp]}
                    out.update(identity_fields(state))
                    return out
                if (
                    tname == "list_pull_requests"
                    and not _github_tool_called_since(msgs, lh, "create_pull_request")
                ):
                    head = _github_infer_feature_branch(msgs)
                    if head:
                        owner, repo = _GITHUB_DEFAULT_OWNER, _GITHUB_DEFAULT_REPO
                        _log.info(
                            "[%s] github deterministic stage=create_pull_request_from_list "
                            "owner=%s repo=%s head=%s",
                            worker_label,
                            owner,
                            repo,
                            head,
                        )
                        forced_resp, _ = _github_build_forced_create_pull_request_tool_call(
                            owner, repo, head
                        )
                        out = {**state, "messages": msgs + [forced_resp]}
                        out.update(identity_fields(state))
                        return out
            if tname == "push_files":
                ctx = _github_parse_push_files_success(tcontent)
                if ctx:
                    owner, repo, head = ctx
                    incomplete_pr = _github_incomplete_pr_in_recent_tools(msgs, lh)
                    files_payload, missing = _github_collect_local_push_files()
                    if incomplete_pr:
                        pr_url = str(incomplete_pr.get("html_url") or "")
                        resp = AIMessage(
                            content=_github_build_pr_completion_response(
                                pr_url,
                                head=head,
                                missing_local=missing,
                                files_pushed=[f["path"] for f in files_payload],
                            )
                        )
                        out = {**state, "messages": msgs + [resp]}
                        out.update(identity_fields(state))
                        return out
                    if "list_pull_requests" in tools_by_name and not _github_tool_called_since(
                        msgs, lh, "list_pull_requests"
                    ):
                        # region agent log
                        # endregion
                        tid = f"call_github_list_prs_{int(time.time() * 1000)}"
                        forced = AIMessage(
                            content="",
                            tool_calls=[
                                {
                                    "name": "list_pull_requests",
                                    "args": {
                                        "owner": _GITHUB_DEFAULT_OWNER,
                                        "repo": _GITHUB_DEFAULT_REPO,
                                        "state": "open",
                                    },
                                    "id": tid,
                                    "type": "tool_call",
                                }
                            ],
                        )
                        out = {**state, "messages": msgs + [forced]}
                        out.update(identity_fields(state))
                        return out
                    if not _github_tool_called_since(msgs, lh, "create_pull_request"):
                        forced_resp, _ = _github_build_forced_create_pull_request_tool_call(
                            owner, repo, head
                        )
                        out = {**state, "messages": msgs + [forced_resp]}
                        out.update(identity_fields(state))
                        return out

    if not already_has_tool_result:
        branch = _github_resolve_feature_branch(msgs)
        files_payload, missing = _github_collect_local_push_files()
        if (
            branch
            and files_payload
            and "push_files" in tools_by_name
            and not _github_tool_called_since(msgs, lh, "push_files")
        ):
            # region agent log
            # endregion
            _log.info(
                "[%s] github deterministic stage=push_files_proactive head=%s files=%d",
                worker_label,
                branch,
                len(files_payload),
            )
            forced_resp, _ = _github_build_forced_push_files_tool_call(
                _GITHUB_DEFAULT_OWNER,
                _GITHUB_DEFAULT_REPO,
                branch,
                files_payload,
                (
                    "feat(quant): complete cancel_trade_signal — "
                    "skill module, bridge, factory, spec, tests"
                ),
            )
            out = {**state, "messages": msgs + [forced_resp]}
            out.update(identity_fields(state))
            return out
        pending = _github_needs_create_pr_after_push(msgs)
        if pending:
            owner, repo, head = pending
            _log.info(
                "[%s] github deterministic stage=create_pull_request_retry owner=%s repo=%s head=%s",
                worker_label,
                owner,
                repo,
                head,
            )
            forced_resp, _ = _github_build_forced_create_pull_request_tool_call(owner, repo, head)
            out = {**state, "messages": msgs + [forced_resp]}
            out.update(identity_fields(state))
            return out
        if "list_pull_requests" in tools_by_name and not _github_tool_called_since(
            msgs, lh, "list_pull_requests"
        ):
            # region agent log
            # endregion
            tid = f"call_github_list_prs_{int(time.time() * 1000)}"
            forced = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "list_pull_requests",
                        "args": {
                            "owner": _GITHUB_DEFAULT_OWNER,
                            "repo": _GITHUB_DEFAULT_REPO,
                            "state": "open",
                        },
                        "id": tid,
                        "type": "tool_call",
                    }
                ],
            )
            out = {**state, "messages": msgs + [forced]}
            out.update(identity_fields(state))
            return out
    return None


def _user_requests_github_pr_retry(text: str) -> bool:
    """Usuario pide reintentar tras fallo parcial (p. ej. «Vuelve a intentar»)."""
    if not text or not str(text).strip():
        return False
    low = text.strip().lower()
    if "[system_directive:" in low or "[system_event:" in low:
        return False
    return bool(
        re.search(r"\bvuelve?\s+a\s+intentar\b", low)
        or re.search(r"\bintenta(r|)\s+(de\s+)?nuevo\b", low)
        or re.search(r"\botra\s+vez\b", low)
        or re.search(r"\btry\s+again\b", low)
        or re.search(r"\bretry\b", low)
    )


def _github_pr_intent_in_recent_human_messages(
    messages: list[Any],
    *,
    max_lookback: int = 8,
) -> bool:
    from langchain_core.messages import HumanMessage

    seen = 0
    for msg in reversed(messages or []):
        if not isinstance(msg, HumanMessage):
            continue
        seen += 1
        if _user_requests_github_pr(str(getattr(msg, "content", "") or "")):
            return True
        if seen >= max(1, max_lookback):
            break
    return False


def _github_latest_push_files_ctx(messages: list[Any]) -> tuple[str, str, str] | None:
    for msg in reversed(messages or []):
        fields = _github_tool_message_fields(msg)
        if not fields or fields[0] != "push_files":
            continue
        ctx = _github_parse_push_files_success(fields[1])
        if ctx:
            return ctx
    return None


def _github_needs_create_pr_after_push(messages: list[Any]) -> tuple[str, str, str] | None:
    """Último push_files OK sin create_pull_request posterior en el hilo."""
    push_idx = -1
    push_ctx: tuple[str, str, str] | None = None
    for i, msg in enumerate(messages or []):
        fields = _github_tool_message_fields(msg)
        if not fields or fields[0] != "push_files":
            continue
        ctx = _github_parse_push_files_success(fields[1])
        if ctx:
            push_idx = i
            push_ctx = ctx
    if push_ctx is None or push_idx < 0:
        return None
    if _github_tool_called_since(messages, push_idx, "create_pull_request"):
        return None
    return push_ctx


def _github_pr_workflow_resolved_intent(messages: list[Any], incoming: str) -> bool:
    """PR directo o reintento con contexto previo de montar PR / push sin PR."""
    if _user_requests_github_pr(incoming):
        return True
    low = str(incoming or "").strip().lower()
    if re.search(r"\bpr\b", low) and _github_needs_create_pr_after_push(messages):
        return True
    if re.search(r"\bpr\b", low) and _github_pr_intent_in_recent_human_messages(messages):
        return True
    if not _user_requests_github_pr_retry(incoming):
        return False
    if _github_pr_intent_in_recent_human_messages(messages):
        return True
    return _github_latest_push_files_ctx(messages) is not None


def _github_build_forced_create_pull_request_tool_call(
    owner: str,
    repo: str,
    head: str,
) -> tuple[Any, list[dict[str, Any]]]:
    from langchain_core.messages import AIMessage

    title = _github_pr_title_from_branch(head)
    forced_tid = f"call_github_create_pr_{int(time.time() * 1000)}"
    forced_tc = [
        {
            "name": "create_pull_request",
            "args": {
                "owner": owner,
                "repo": repo,
                "title": title,
                "head": head,
                "base": "main",
                "body": (
                    f"PR abierto por DuckClaw agent desde rama `{head}`.\n\n"
                    "Revisar diff en GitHub antes de merge."
                ),
            },
            "id": forced_tid,
            "type": "tool_call",
        }
    ]
    return AIMessage(content="", tool_calls=forced_tc), forced_tc



github_pr_workflow_resolved_intent = _github_pr_workflow_resolved_intent
try_deterministic_pr_workflow = _github_try_deterministic_pr_workflow
