"""One-shot generator: meditate.py -> loop.py (run once, then delete)."""
from __future__ import annotations

import re
from pathlib import Path

SRC = Path(__file__).resolve().parents[4] / "packages/agents/src/duckclaw/commands/meditate.py"
DST = Path(__file__).resolve().parents[4] / "packages/agents/src/duckclaw/commands/loop.py"

text = SRC.read_text(encoding="utf-8")
text = text.replace(
    '"""Cognitive /meditate scheduling: auto-mejora LLM vs manifiesto /goals."""',
    '"""Cognitive /loop scheduling: auto-mejora LLM vs manifiesto /goals (formerly /meditate)."""',
    1,
)
insert = """
from duckclaw.commands.loop_state_keys import (
    LOOP_ACTIVE_KEY,
    LOOP_AWAITING_USER_KEY,
    LOOP_DELTA_SECONDS_KEY,
    LOOP_LAST_FIRE_KEY,
    LOOP_TENANT_KEY,
    LOOP_WORKER_KEY,
    get_loop_chat_state,
    migrate_loop_chat_state_keys,
    persist_loop_chat_state,
)
"""
text = text.replace(
    "from duckclaw.commands.history import _infer_user_id_for_audit_queue",
    insert + "from duckclaw.commands.history import _infer_user_id_for_audit_queue",
    1,
)
for line in [
    '_MEDITATE_DELTA_SECONDS_KEY = "meditate_delta_seconds"\n',
    '_MEDITATE_LAST_FIRE_KEY = "meditate_last_fire_epoch"\n',
    '_MEDITATE_TENANT_KEY = "meditate_tenant_id"\n',
    '_MEDITATE_WORKER_KEY = "meditate_worker_id"\n',
    '_MEDITATE_ACTIVE_KEY = "meditate_active"\n',
    '_MEDITATE_AWAITING_USER_KEY = "meditate_awaiting_user"\n',
]:
    text = text.replace(line, "")

replacements = [
    ("MEDITATE_DELTA_MIN_SECONDS", "LOOP_DELTA_MIN_SECONDS"),
    ("MEDITATE_DELTA_MAX_SECONDS", "LOOP_DELTA_MAX_SECONDS"),
    ("MEDITATE_SELF_HTTP_TIMEOUT", "LOOP_SELF_HTTP_TIMEOUT"),
    ("MEDITATE_DEFAULT_INTERVAL_SECONDS", "LOOP_DEFAULT_INTERVAL_SECONDS"),
    ("MEDITATE_SYSTEM_USER_LABEL", 'LOOP_SYSTEM_USER_LABEL = "[Ciclo loop]"'),
    ("MEDITATE_SYSTEM_USER_LABEL = \"[Ciclo loop]\"", "LOOP_SYSTEM_USER_LABEL = \"[Ciclo loop]\""),
    ("MeditateTickHeartbeatPublisher", "LoopTickHeartbeatPublisher"),
    ("_meditate_tick_heartbeat_publisher", "_loop_tick_heartbeat_publisher"),
    ("configure_meditate_tick_heartbeat_publisher", "configure_loop_tick_heartbeat_publisher"),
    ("publish_meditate_tick", "publish_loop_tick"),
    ("parse_meditate_delta_arg", "parse_loop_delta_arg"),
    ("chat_id_from_meditate_delta_config_key", "chat_id_from_loop_delta_config_key"),
    ("_resolve_meditate_worker_id", "_resolve_loop_worker_id"),
    ("is_meditate_active_mode", "is_loop_active_mode"),
    ("is_meditate_awaiting_user", "is_loop_awaiting_user"),
    ("set_meditate_awaiting_user", "set_loop_awaiting_user"),
    ("enable_meditate_active_mode", "enable_loop_active_mode"),
    ("build_meditate_active_user_continuation", "build_loop_active_user_continuation"),
    ("build_meditate_self_system_event_message", "build_loop_self_system_event_message"),
    ("meditate_repetition_interval_human", "loop_repetition_interval_human"),
    ("_build_meditate_tick_payload", "_build_loop_tick_payload"),
    ("post_meditate_self_tick_sync", "post_loop_self_tick_sync"),
    ("dispatch_meditate_self_tick", "dispatch_loop_self_tick"),
    ("post_meditate_self_tick_async", "post_loop_self_tick_async"),
    ("_persist_meditate_chat_state", "_persist_loop_chat_state"),
    ("clear_meditate_schedule", "clear_loop_schedule"),
    ("get_meditate_schedule_status", "get_loop_schedule_status"),
    ("format_meditate_next_tick_footer", "format_loop_next_tick_footer"),
    ("apply_meditate_schedule", "apply_loop_schedule"),
    ("_format_meditate_cycle_summary", "_format_loop_cycle_summary"),
    ("_publish_meditate_tick_heartbeat", "_publish_loop_tick_heartbeat"),
    ("_resolve_meditate_vault_user_id", "_resolve_loop_vault_user_id"),
    ("invoke_meditate_cycle_for_chat", "invoke_loop_cycle_for_chat"),
    ("_format_meditate_usage", "_format_loop_usage"),
    ("execute_meditate_immediate", "execute_loop_immediate"),
    ("_execute_meditate_enable", "_execute_loop_enable"),
    ("_execute_meditate_active_on", "_execute_loop_active_on"),
    ("execute_meditate", "execute_loop"),
    ("_MEDITATE_DELTA_SECONDS_KEY", "LOOP_DELTA_SECONDS_KEY"),
    ("_MEDITATE_LAST_FIRE_KEY", "LOOP_LAST_FIRE_KEY"),
    ("_MEDITATE_TENANT_KEY", "LOOP_TENANT_KEY"),
    ("_MEDITATE_WORKER_KEY", "LOOP_WORKER_KEY"),
    ("_MEDITATE_ACTIVE_KEY", "LOOP_ACTIVE_KEY"),
    ("_MEDITATE_AWAITING_USER_KEY", "LOOP_AWAITING_USER_KEY"),
    ("meditate_validation_service", "loop_validation_service"),
    ("_meditate_delta_seconds", "_loop_delta_seconds"),
    ("meditate self tick", "loop self tick"),
    ('name=f"meditate-tick', 'name=f"loop-tick'),
]
for a, b in replacements:
    text = text.replace(a, b)

# Fix duplicate LOOP_SYSTEM_USER_LABEL if any
text = re.sub(
    r'LOOP_SYSTEM_USER_LABEL = "\[Ciclo loop\]" = "\[Ciclo loop\]"',
    'LOOP_SYSTEM_USER_LABEL = "[Ciclo loop]"',
    text,
)
if 'LOOP_SYSTEM_USER_LABEL = "[Ciclo loop]"' not in text:
    text = text.replace(
        'LOOP_DEFAULT_INTERVAL_SECONDS = 15 * 60\n',
        'LOOP_DEFAULT_INTERVAL_SECONDS = 15 * 60\nLOOP_SYSTEM_USER_LABEL = "[Ciclo loop]"\n',
        1,
    )

for pat, rep in [
    (r"/meditate-approve", "/loop-approve"),
    (r"/meditate-reject", "/loop-reject"),
    (r"/meditate_approve", "/loop_approve"),
    (r"/meditate_reject", "/loop_reject"),
    (r"`/meditate", "`/loop"),
    (r'"/meditate', '"/loop'),
    (r"/meditate", "/loop"),
]:
    text = re.sub(pat, rep, text)

# get_chat_state -> get_loop_chat_state for loop keys
for fn in [
    "is_loop_active_mode",
    "is_loop_awaiting_user",
    "get_loop_schedule_status",
    "loop_repetition_interval_human",
]:
    pass

text = text.replace(
    "return (get_chat_state(db, chat_id, LOOP_ACTIVE_KEY) or \"\").strip() == \"1\"",
    'migrate_loop_chat_state_keys(db, chat_id)\n    return (get_loop_chat_state(db, chat_id, LOOP_ACTIVE_KEY) or "").strip() == "1"',
    1,
)
text = text.replace(
    "return (get_chat_state(db, chat_id, LOOP_AWAITING_USER_KEY) or \"\").strip() == \"1\"",
    'return (get_loop_chat_state(db, chat_id, LOOP_AWAITING_USER_KEY) or "").strip() == "1"',
    1,
)

def patch_get_state(block_key: str) -> None:
    global text
    text = text.replace(
        f"get_chat_state(db, chat_id, {block_key})",
        f"get_loop_chat_state(db, chat_id, {block_key})",
    )

for k in [
    "LOOP_DELTA_SECONDS_KEY",
    "LOOP_LAST_FIRE_KEY",
    "LOOP_TENANT_KEY",
    "LOOP_WORKER_KEY",
    "LOOP_AWAITING_USER_KEY",
]:
    patch_get_state(k)

# _persist_loop_chat_state should delegate to persist_loop_chat_state
old_persist = '''def _persist_loop_chat_state(
    db: Any,
    chat_id: Any,
    key_suffix: str,
    value: str,
    *,
    tenant_id: str = "default",
) -> tuple[bool, str]:
    tid = str(tenant_id or "default").strip() or "default"
    if _skip_runtime_ddl(db):
        return set_chat_state_via_typed_command(
            db,
            chat_id,
            key_suffix,
            value,
            tenant_id=tid,
        )
    set_chat_state(db, chat_id, key_suffix, value)
    return True, ""'''

new_persist = '''def _persist_loop_chat_state(
    db: Any,
    chat_id: Any,
    key_suffix: str,
    value: str,
    *,
    tenant_id: str = "default",
) -> tuple[bool, str]:
    tid = str(tenant_id or "default").strip() or "default"
    return persist_loop_chat_state(db, chat_id, key_suffix, value, tenant_id=tid)'''

text = text.replace(old_persist, new_persist)

DST.write_text(text, encoding="utf-8")
print("wrote", DST)
