"""Legacy slash/fly command invocation for chat entrypoints."""

from __future__ import annotations

import asyncio
import logging
import os
import time
from pathlib import Path
from typing import Any, Callable

from core.sandbox_figure_b64 import decode_sandbox_figure_base64, decode_valid_sandbox_image_bytes
from core.telegram_media_upload import send_sandbox_chart_to_telegram_sync
from duckclaw import DuckClaw
from duckclaw.channels import GatewayDeliveryContext
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.extensions.fly import extension_fly_read_only_command_names
from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session
from duckclaw.graphs.on_the_fly_commands import handle_command, parse_command, pop_all_fly_outbound_charts
from duckclaw.manager.graph import worker_graph_cache_entry_count
from duckclaw.ops.gateway_resource_release import release_worker_graph_cache
from duckclaw.utils.logger import format_chat_id_for_terminal

ResolveTelegramBotToken = Callable[[], str]
PersistAdminFlyCharts = Callable[[str, list[str]], list[str]]

_log = logging.getLogger("duckclaw.gateway")

_CORE_READ_ONLY_SAFE_FLY_COMMANDS = frozenset(
    (
        "approve-code",
        "approve_code",
        "audit",
        "comfyui",
        "context",
        "crons",
        "forget",
        "goals",
        "heartbeat",
        "health",
        "history",
        "internet",
        "llm",
        "model",
        "models",
        "network",
        "prompt",
        "loop",
        "loop-approve",
        "loop_approve",
        "loop-reject",
        "loop_reject",
        "meditate",
        "meditate-approve",
        "meditate_approve",
        "meditate-reject",
        "meditate_reject",
        "provider",
        "red",
        "reject-code",
        "reject_code",
        "resolve-uncertainty",
        "resolve_uncertainty",
        "sandbox",
        "sandox",
        "setup",
        "summarize",
        "system",
        "system_prompt",
        "team",
        "vault",
        "workers",
    )
)
READ_ONLY_SAFE_FLY_COMMANDS = _CORE_READ_ONLY_SAFE_FLY_COMMANDS | extension_fly_read_only_command_names()
LEGACY_RW_FLY_COMMANDS = frozenset(())


def _truncate_fly_log(text: str, max_len: int = 200) -> str:
    value = (text or "").strip()
    return value if len(value) <= max_len else value[:max_len] + "..."


def _fly_command_requires_write_access(message: str) -> bool:
    """Subcomandos fly que mutan vault/chat state necesitan DuckClaw read_only=False."""
    name, args = parse_command(message)
    if not name:
        return False
    cmd = name.replace("_", "-")
    if cmd in LEGACY_RW_FLY_COMMANDS:
        return True
    args_norm = (args or "").strip().lower()
    if cmd in ("loop", "meditate"):
        if not args_norm:
            return False
        first = args_norm.split()[0]
        if first in ("--status", "status"):
            return False
        if first in ("on", "off", "--delta", "--self", "--now"):
            return True
        return False
    return False


def _open_fly_duckclaw(vault_db_path: str, message: str) -> DuckClaw:
    _name, _args = parse_command(message)
    read_only = not _fly_command_requires_write_access(message)
    return DuckClaw(vault_db_path, read_only=read_only, engine="python")


def _audit_fly_vault_resolution(vault_db_path: str, fly_engine: str) -> None:
    if (os.environ.get("DUCKCLAW_TEAM_WHITELIST_DEBUG") or "").strip().lower() not in (
        "1",
        "true",
        "yes",
        "on",
    ):
        return
    try:
        gateway_path = str(Path(get_gateway_db_path()).resolve())
        vault_path = (
            str(Path(vault_db_path).resolve())
            if vault_db_path and vault_db_path != ":memory:"
            else (vault_db_path or "")
        )
        same_file = bool(
            vault_path
            and gateway_path
            and Path(vault_path).resolve() == Path(gateway_path).resolve()
        )
        _log.info(
            "fly_team_audit vault_resolved=%r gateway_resolved=%r same_file=%s fly_engine=%s",
            vault_path[-96:] if len(vault_path) > 96 else vault_path,
            gateway_path[-96:] if len(gateway_path) > 96 else gateway_path,
            same_file,
            fly_engine,
        )
    except OSError as exc:
        _log.info("fly_team_audit path_compare_error=%s", exc)


def _clear_cached_worker_handles_for_fly() -> None:
    try:
        cache_entries = worker_graph_cache_entry_count()
        release_worker_graph_cache(force=True)
        if _log.isEnabledFor(logging.DEBUG):
            _log.debug("fly cleared worker graph cache entries=%s", cache_entries)
    except Exception:
        if _log.isEnabledFor(logging.DEBUG):
            _log.debug("fly worker graph cache clear skipped", exc_info=True)


async def _attach_fly_charts(
    fly_response: dict[str, Any],
    *,
    session_id: str,
    tenant_id: str,
    delivery_context: GatewayDeliveryContext,
    resolve_telegram_bot_token: ResolveTelegramBotToken,
    persist_admin_fly_charts: PersistAdminFlyCharts,
) -> None:
    loop = asyncio.get_running_loop()
    token = (
        ((delivery_context.outbound_bot_token or "").strip() or resolve_telegram_bot_token()).strip()
        if (delivery_context.channel or "telegram").strip().lower() == "telegram"
        else ""
    )
    admin_ui = is_admin_ui_chat_session(session_id)
    fly_charts, fly_chart_names = pop_all_fly_outbound_charts(session_id)
    if token:
        chart_sent = False
        for photo_b64 in fly_charts:
            png_bytes = decode_valid_sandbox_image_bytes(photo_b64)
            if not png_bytes:
                png_bytes = decode_sandbox_figure_base64(photo_b64)
            if not png_bytes:
                continue
            ok = await loop.run_in_executor(
                None,
                lambda b=png_bytes: send_sandbox_chart_to_telegram_sync(
                    bot_token=token,
                    chat_id=str(session_id),
                    image_bytes=b,
                ),
            )
            chart_sent = chart_sent or bool(ok)
        fly_response["chart_sent"] = chart_sent
    if admin_ui and fly_charts:
        fly_response["fly_charts_b64"] = fly_charts
        if fly_chart_names:
            fly_response["fly_chart_names"] = fly_chart_names[: len(fly_charts)]
        artifact_ids = persist_admin_fly_charts(tenant_id, fly_charts)
        if artifact_ids:
            fly_response["fly_chart_artifact_ids"] = artifact_ids
            fly_response["artifact_tenant_id"] = tenant_id
        if not artifact_ids:
            fly_response["figure_base64"] = fly_charts[0]


async def invoke_legacy_fly_command(
    *,
    message: str,
    session_id: str,
    worker_id: str,
    tenant_id: str,
    vault_db_path: str,
    vault_user_id: str,
    requester_id: str,
    username: str,
    delivery_context: GatewayDeliveryContext,
    resolve_telegram_bot_token: ResolveTelegramBotToken,
    persist_admin_fly_charts: PersistAdminFlyCharts,
) -> dict[str, Any] | None:
    """Invoke legacy slash/fly commands and return a chat response if handled."""
    if not (message or "").strip().startswith("/"):
        return None

    fly_db = None
    cmd_reply: str | None = None
    elapsed_ms = 0
    try:
        vpath = (vault_db_path or "").strip()
        Path(vpath).parent.mkdir(parents=True, exist_ok=True)
        fly_engine = "python"
        _audit_fly_vault_resolution(vpath, fly_engine)
        _clear_cached_worker_handles_for_fly()
        fly_db = _open_fly_duckclaw(vpath, message)
        started_at = time.monotonic()
        cmd_reply = handle_command(
            fly_db,
            session_id,
            message,
            requester_id=requester_id,
            tenant_id=tenant_id,
            vault_user_id=vault_user_id,
            username=username,
            entry_worker_id=worker_id,
        )
        elapsed_ms = int((time.monotonic() - started_at) * 1000)
    except Exception as exc:
        _log.error("fly command failed chat=%s: %s", format_chat_id_for_terminal(session_id), exc)
    finally:
        if fly_db is not None:
            try:
                fly_db.close()
            except Exception:
                pass

    if cmd_reply is None:
        _log.warning(
            "fly command unhandled (graph fallback): chat=%s head=%s",
            format_chat_id_for_terminal(session_id),
            (message or "").split()[0] if (message or "").strip() else "?",
        )
        return None

    fly_response: dict[str, Any] = {
        "response": cmd_reply,
        "session_id": session_id,
        "worker_id": worker_id,
        "elapsed_ms": elapsed_ms,
    }
    try:
        await _attach_fly_charts(
            fly_response,
            session_id=session_id,
            tenant_id=tenant_id,
            delivery_context=delivery_context,
            resolve_telegram_bot_token=resolve_telegram_bot_token,
            persist_admin_fly_charts=persist_admin_fly_charts,
        )
    except Exception as exc:
        if _log.isEnabledFor(logging.DEBUG):
            _log.debug("fly chart attach failed: %s", exc)
    if _log.isEnabledFor(logging.DEBUG):
        _log.debug(
            "fly (backup) chat=%s: %s",
            format_chat_id_for_terminal(session_id),
            _truncate_fly_log(cmd_reply),
        )
    return fly_response
