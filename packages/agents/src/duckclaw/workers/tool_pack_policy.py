"""Policy pura: packs activos por turno + filtro de tools (sin I/O)."""

from __future__ import annotations

import json
import logging
from typing import Any, Iterable

from duckclaw.workers.tool_pack_catalog import resolve_runtime_packs_config
from duckclaw.workers.tool_pack_models import (
    PackFilterResult,
    RuntimePacksConfig,
    RuntimeToolPackCatalog,
    ToolPackSpec,
)

_log = logging.getLogger(__name__)

UNLOCK_TOOL_NAME = "unlock_tool_pack"
LIST_PACKS_TOOL_NAME = "list_tool_packs"


def apply_runtime_tool_packs(
    tools: Iterable[Any],
    *,
    spec: Any | None,
    intent_text: str | None,
    messages: Iterable[Any] | None = None,
) -> PackFilterResult:
    """Filtra tools según packs activos. No-op si ``runtime_packs.enabled`` es false."""
    cfg = resolve_runtime_packs_config(spec)
    tool_list = list(tools)
    if not cfg.enabled:
        names = tuple(_tool_name(t) for t in tool_list if _tool_name(t))
        return PackFilterResult(
            tools=tool_list,
            active_packs=frozenset(),
            bound_names=names,
            managed_hidden=0,
            applied=False,
            truncated=False,
        )

    active = resolve_active_pack_ids(
        cfg,
        intent_text=intent_text,
        messages=messages or (),
    )
    return filter_tools_by_packs(tool_list, cfg=cfg, active_packs=active)


def resolve_active_pack_ids(
    cfg: RuntimePacksConfig,
    *,
    intent_text: str | None,
    messages: Iterable[Any] = (),
) -> frozenset[str]:
    catalog = cfg.catalog
    disabled = set(cfg.disabled_packs)
    active: set[str] = set()

    for pack in catalog.packs:
        if pack.pack_id in disabled:
            continue
        if pack.always or pack.pack_id in cfg.extra_always:
            active.add(pack.pack_id)

    intent = (intent_text or "").strip().lower()
    if intent:
        for pack in catalog.packs:
            if pack.pack_id in disabled:
                continue
            if _intent_matches_pack(intent, pack):
                active.add(pack.pack_id)

    active |= sticky_packs_from_messages(messages, catalog) - disabled
    active |= unlocked_packs_from_messages(messages) - disabled
    return frozenset(active)


def filter_tools_by_packs(
    tools: Iterable[Any],
    *,
    cfg: RuntimePacksConfig,
    active_packs: frozenset[str],
) -> PackFilterResult:
    catalog = cfg.catalog
    kept: list[Any] = []
    hidden = 0
    for tool in tools:
        name = _tool_name(tool)
        if not name:
            kept.append(tool)
            continue
        packs = catalog.packs_for_tool(name)
        if not packs:
            if catalog.orphan_policy == "include":
                kept.append(tool)
            else:
                hidden += 1
            continue
        # Packs deshabilitados no cuentan como cobertura: tool se trata como huérfana.
        live_packs = packs - cfg.disabled_packs
        if not live_packs:
            if catalog.orphan_policy == "include":
                kept.append(tool)
            else:
                hidden += 1
            continue
        if live_packs & active_packs:
            kept.append(tool)
        else:
            hidden += 1

    truncated = False
    max_bound = catalog.max_bound_tools
    if len(kept) > max_bound:
        kept = _truncate_preferring_always(kept, catalog, active_packs, max_bound)
        truncated = True

    names = tuple(_tool_name(t) for t in kept if _tool_name(t))
    return PackFilterResult(
        tools=kept,
        active_packs=frozenset(active_packs),
        bound_names=names,
        managed_hidden=hidden,
        applied=True,
        truncated=truncated,
    )


def sticky_packs_from_messages(
    messages: Iterable[Any],
    catalog: RuntimeToolPackCatalog,
) -> frozenset[str]:
    """Packs de tools ya usadas tras el último mensaje humano."""
    tool_names = tool_names_after_last_human(messages)
    active: set[str] = set()
    for name in tool_names:
        active |= set(catalog.packs_for_tool(name))
    return frozenset(active)


def unlocked_packs_from_messages(messages: Iterable[Any]) -> frozenset[str]:
    """Packs desbloqueados vía ``unlock_tool_pack`` en el turno actual."""
    unlocked: set[str] = set()
    for msg in _messages_after_last_human(messages):
        if _message_tool_name(msg) != UNLOCK_TOOL_NAME:
            continue
        content = getattr(msg, "content", None)
        if not isinstance(content, str) or not content.strip():
            continue
        try:
            payload = json.loads(content)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        if payload.get("ok") is False:
            continue
        pack_id = str(payload.get("pack_id") or payload.get("unlocked") or "").strip()
        if pack_id:
            unlocked.add(pack_id)
        for item in payload.get("unlocked_packs") or []:
            pid = str(item).strip()
            if pid:
                unlocked.add(pid)
    return frozenset(unlocked)


def tool_names_after_last_human(messages: Iterable[Any]) -> frozenset[str]:
    names: set[str] = set()
    for msg in _messages_after_last_human(messages):
        name = _message_tool_name(msg)
        if name:
            names.add(name)
    return frozenset(names)


def catalog_public_summary(cfg: RuntimePacksConfig) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for pack in cfg.catalog.packs:
        if pack.pack_id in cfg.disabled_packs:
            continue
        member_count = len(pack.members.exact) + len(pack.members.prefixes)
        rows.append(
            {
                "pack_id": pack.pack_id,
                "description": pack.description,
                "always": pack.always or pack.pack_id in cfg.extra_always,
                "activation_signals": list(pack.activation_signals),
                "member_hints": {
                    "exact_count": len(pack.members.exact),
                    "prefix_count": len(pack.members.prefixes),
                    "member_hint_count": member_count,
                },
            }
        )
    return rows


def log_pack_filter_result(worker_label: str, result: PackFilterResult) -> None:
    if not result.applied:
        return
    _log.info(
        "[%s] runtime_tool_packs active=%s bound=%s hidden=%s truncated=%s names=%s",
        worker_label,
        sorted(result.active_packs),
        len(result.bound_names),
        result.managed_hidden,
        result.truncated,
        list(result.bound_names)[:40],
    )


def _intent_matches_pack(intent_lower: str, pack: ToolPackSpec) -> bool:
    for signal in pack.activation_signals:
        if signal and signal in intent_lower:
            return True
    return False


def _truncate_preferring_always(
    tools: list[Any],
    catalog: RuntimeToolPackCatalog,
    active_packs: frozenset[str],
    max_bound: int,
) -> list[Any]:
    """Preferir tools de packs activos; los huérfanos van al final (no comen cupo)."""
    always_ids = {p.pack_id for p in catalog.packs if p.always and p.pack_id in active_packs}
    primary: list[Any] = []
    secondary: list[Any] = []
    orphans: list[Any] = []
    for tool in tools:
        name = _tool_name(tool)
        packs = catalog.packs_for_tool(name)
        if not packs:
            orphans.append(tool)
            continue
        if packs & always_ids:
            primary.append(tool)
        elif packs & active_packs:
            secondary.append(tool)
        else:
            # No debería llegar aquí (ya filtrado), pero no inventar prioridad.
            orphans.append(tool)
    ordered = primary + secondary + orphans
    return ordered[:max_bound]


def _messages_after_last_human(messages: Iterable[Any]) -> list[Any]:
    msgs = list(messages or [])
    last_human = -1
    for idx, msg in enumerate(msgs):
        cls = type(msg).__name__
        role = str(getattr(msg, "type", "") or getattr(msg, "role", "") or "").lower()
        if cls == "HumanMessage" or role in {"human", "user"}:
            last_human = idx
    if last_human < 0:
        return msgs
    return msgs[last_human + 1 :]


def _message_tool_name(msg: Any) -> str:
    cls = type(msg).__name__
    role = str(getattr(msg, "type", "") or "").lower()
    if cls != "ToolMessage" and role != "tool":
        return ""
    return str(getattr(msg, "name", "") or "").strip()


def _tool_name(tool: Any) -> str:
    return str(getattr(tool, "name", "") or "").strip()
