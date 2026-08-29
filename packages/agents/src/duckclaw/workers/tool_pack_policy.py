"""Policy pura: packs activos por turno + filtro de tools (sin I/O)."""

from __future__ import annotations

import json
import logging
import re
from typing import Any, Iterable

from duckclaw.workers.tool_pack_catalog import resolve_runtime_packs_config
from duckclaw.workers.tool_pack_models import (
    PackFilterResult,
    RuntimePacksConfig,
    RuntimeToolPackCatalog,
    ToolPackMembers,
    ToolPackSpec,
)

_log = logging.getLogger(__name__)

UNLOCK_TOOL_NAME = "unlock_tool_pack"
LIST_PACKS_TOOL_NAME = "list_tool_packs"
MCP_UMBRELLA_PACK_ID = "mcp"
_MCP_CONNECTOR_PACK_PREFIX = "mcp_"
_DEFAULT_WORKER_ID = "default"
# Internal scaffold worker: no on-demand packs that write, execute, or reach external systems.
_DEFAULT_WORKER_RESTRICTED_PACK_IDS = frozenset(
    {
        "docs_output",
        "sandbox",
        "reports",
        "mcp",
        "visual",
        "integrations",
        "research",
        "knowledge",
    }
)
# ADB helpers live outside mcp__* namespace but belong to Android MCP pack.
_ANDROID_ADB_HELPER_TOOLS = frozenset(
    {
        "android_expand_notifications",
        "android_collapse_notifications",
    }
)


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
    tool_names = tuple(_tool_name(t) for t in tool_list if _tool_name(t))
    connector_ids = mcp_connector_ids_from_tool_names(tool_names)
    if not cfg.enabled:
        return PackFilterResult(
            tools=tool_list,
            active_packs=frozenset(),
            bound_names=tool_names,
            managed_hidden=0,
            applied=False,
            truncated=False,
            connector_ids=connector_ids,
        )

    cfg = with_mcp_connector_packs(cfg, tool_names)
    msgs = messages or ()
    active = resolve_active_pack_ids(
        cfg,
        intent_text=intent_text,
        messages=msgs,
        available_tool_names=tool_names,
    )
    active = filter_active_packs_for_worker(
        active,
        worker_id=runtime_worker_id_from_spec(spec),
    )
    unlock_priority = tuple(unlocked_packs_from_messages(msgs))
    return filter_tools_by_packs(
        tool_list,
        cfg=cfg,
        active_packs=active,
        connector_ids=connector_ids,
        unlock_priority=unlock_priority,
    )


def with_mcp_connector_packs(
    cfg: RuntimePacksConfig,
    tool_names: Iterable[str],
) -> RuntimePacksConfig:
    """Devuelve cfg con packs dinámicos ``mcp_{connector}`` fusionados al catálogo."""
    catalog = enrich_catalog_with_mcp_connectors(cfg.catalog, tool_names)
    if catalog is cfg.catalog:
        return cfg
    return RuntimePacksConfig(
        enabled=cfg.enabled,
        catalog=catalog,
        disabled_packs=cfg.disabled_packs,
        extra_always=cfg.extra_always,
        raw=cfg.raw,
    )


def enrich_catalog_with_mcp_connectors(
    catalog: RuntimeToolPackCatalog,
    tool_names: Iterable[str],
) -> RuntimeToolPackCatalog:
    """Añade un pack por conector MCP presente en ``tool_names`` (idempotente)."""
    existing = {p.pack_id for p in catalog.packs}
    extra: list[ToolPackSpec] = []
    # Helpers may appear without mcp__android__* yet; still seed android pack.
    connector_ids = set(mcp_connector_ids_from_tool_names(tool_names))
    if _ANDROID_ADB_HELPER_TOOLS.intersection(str(n or "") for n in tool_names):
        connector_ids.add("android")
    for connector_id in sorted(connector_ids):
        pack_id = mcp_pack_id_for_connector(connector_id)
        if pack_id in existing:
            continue
        exact = (
            _ANDROID_ADB_HELPER_TOOLS if connector_id == "android" else frozenset()
        )
        extra.append(
            ToolPackSpec(
                pack_id=pack_id,
                description=f"Tools MCP del conector «{connector_id}».",
                always=False,
                members=ToolPackMembers(
                    exact=exact,
                    prefixes=(f"mcp__{connector_id}__",),
                ),
                activation_signals=(connector_id,),
            )
        )
        existing.add(pack_id)
    if not extra:
        return catalog
    return RuntimeToolPackCatalog(
        version=catalog.version,
        orphan_policy=catalog.orphan_policy,
        max_bound_tools=catalog.max_bound_tools,
        packs=tuple(catalog.packs) + tuple(extra),
    )


def mcp_pack_id_for_connector(connector_id: str) -> str:
    cleaned = str(connector_id or "").strip().lower()
    return f"{_MCP_CONNECTOR_PACK_PREFIX}{cleaned}"


def resolve_active_pack_ids(
    cfg: RuntimePacksConfig,
    *,
    intent_text: str | None,
    messages: Iterable[Any] = (),
    available_tool_names: Iterable[str] = (),
) -> frozenset[str]:
    catalog = cfg.catalog
    disabled = set(cfg.disabled_packs)
    active: set[str] = set()
    connector_ids = mcp_connector_ids_from_tool_names(available_tool_names)
    connector_pack_ids = {
        mcp_pack_id_for_connector(cid) for cid in connector_ids
    } - disabled

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
        # N agentes / N MCP: id del conector como token (no substring de mcp_github).
        for connector_id in connector_ids:
            pack_id = mcp_pack_id_for_connector(connector_id)
            if pack_id in disabled:
                continue
            if intent_mentions_token(intent, connector_id):
                active.add(pack_id)

    active |= sticky_packs_from_messages(messages, catalog) - disabled
    active |= unlocked_packs_from_messages(messages) - disabled

    # Umbrella mcp (unlock / extra_always) → todos los conectores del worker.
    if MCP_UMBRELLA_PACK_ID in active and MCP_UMBRELLA_PACK_ID not in disabled:
        active |= connector_pack_ids
    return frozenset(active)


def runtime_worker_id_from_spec(spec: Any | None) -> str:
    if spec is None:
        return ""
    for attr in ("worker_id", "logical_worker_id"):
        raw = str(getattr(spec, attr, "") or "").strip()
        if raw:
            return raw
    return ""


def is_default_runtime_worker(worker_id: str | None) -> bool:
    return (worker_id or "").strip().lower().replace("_", "-") == _DEFAULT_WORKER_ID


def is_pack_restricted_for_worker(pack_id: str, worker_id: str | None) -> bool:
    if not is_default_runtime_worker(worker_id):
        return False
    pid = (pack_id or "").strip().lower()
    if not pid:
        return False
    if pid in _DEFAULT_WORKER_RESTRICTED_PACK_IDS:
        return True
    return pid.startswith(_MCP_CONNECTOR_PACK_PREFIX)


def filter_active_packs_for_worker(
    active: Iterable[str],
    *,
    worker_id: str | None,
) -> frozenset[str]:
    return frozenset(
        pid for pid in active if not is_pack_restricted_for_worker(pid, worker_id)
    )


def mcp_connector_ids_from_tool_names(tool_names: Iterable[str]) -> frozenset[str]:
    """Extrae ids de conector desde nombres canónicos ``mcp__{connector}__{tool}``."""
    found: set[str] = set()
    for raw in tool_names:
        name = str(raw or "").strip()
        if not name.startswith("mcp__"):
            continue
        rest = name[5:]
        connector, sep, _tool = rest.partition("__")
        if sep and connector.strip():
            found.add(connector.strip().lower())
    return frozenset(found)


def filter_tools_by_packs(
    tools: Iterable[Any],
    *,
    cfg: RuntimePacksConfig,
    active_packs: frozenset[str],
    connector_ids: frozenset[str] | None = None,
    unlock_priority: Iterable[str] = (),
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
        kept = _truncate_preferring_always(
            kept,
            catalog,
            active_packs,
            max_bound,
            unlock_priority=tuple(unlock_priority),
        )
        truncated = True

    names = tuple(_tool_name(t) for t in kept if _tool_name(t))
    ids = connector_ids if connector_ids is not None else mcp_connector_ids_from_tool_names(
        _tool_name(t) for t in tools
    )
    return PackFilterResult(
        tools=kept,
        active_packs=frozenset(active_packs),
        bound_names=names,
        managed_hidden=hidden,
        applied=True,
        truncated=truncated,
        connector_ids=frozenset(ids),
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


def catalog_public_summary(
    cfg: RuntimePacksConfig,
    *,
    tool_names: Iterable[str] = (),
    worker_id: str | None = None,
) -> list[dict[str, Any]]:
    enriched = with_mcp_connector_packs(cfg, tool_names)
    rows: list[dict[str, Any]] = []
    for pack in enriched.catalog.packs:
        if pack.pack_id in enriched.disabled_packs:
            continue
        if is_pack_restricted_for_worker(pack.pack_id, worker_id):
            continue
        member_count = (
            len(pack.members.exact)
            + len(pack.members.prefixes)
            + len(pack.members.name_regexes)
        )
        rows.append(
            {
                "pack_id": pack.pack_id,
                "description": pack.description,
                "always": pack.always or pack.pack_id in enriched.extra_always,
                "activation_signals": list(pack.activation_signals),
                "member_hints": {
                    "exact_count": len(pack.members.exact),
                    "prefix_count": len(pack.members.prefixes),
                    "member_hint_count": member_count,
                },
            }
        )
    return rows


def expand_unlock_pack_ids(
    pack_id: str,
    cfg: RuntimePacksConfig,
    *,
    tool_names: Iterable[str] = (),
    worker_id: str | None = None,
) -> list[str]:
    """Si unlock es umbrella ``mcp``, expande a packs por conector presentes."""
    cleaned = (pack_id or "").strip()
    if not cleaned:
        return []
    if is_pack_restricted_for_worker(cleaned, worker_id):
        return []
    enriched = with_mcp_connector_packs(cfg, tool_names)
    known = {p.pack_id for p in enriched.catalog.packs} - set(enriched.disabled_packs)
    if cleaned not in known:
        return []
    if cleaned != MCP_UMBRELLA_PACK_ID:
        return [cleaned]
    connector_packs = sorted(
        p.pack_id
        for p in enriched.catalog.packs
        if p.pack_id.startswith(_MCP_CONNECTOR_PACK_PREFIX)
        and p.pack_id != MCP_UMBRELLA_PACK_ID
        and p.pack_id not in enriched.disabled_packs
    )
    return [MCP_UMBRELLA_PACK_ID, *connector_packs]


def log_pack_filter_result(worker_label: str, result: PackFilterResult) -> None:
    if not result.applied:
        return
    metrics = result.metrics
    _log.info(
        "[%s] runtime_tool_packs_metric %s names=%s",
        worker_label,
        metrics,
        list(result.bound_names)[:40],
    )


def intent_mentions_token(intent_lower: str, token: str) -> bool:
    """True si ``token`` aparece como palabra/token, no como substring de otro id.

    Evita que citar ``mcp_github`` active el conector ``github``.
    """
    cleaned = (token or "").strip().lower()
    if not cleaned or not intent_lower:
        return False
    # Límite: no letra/dígito/_ a ambos lados (pack ids usan _).
    pattern = rf"(?<![a-z0-9_]){re.escape(cleaned)}(?![a-z0-9_])"
    return re.search(pattern, intent_lower) is not None


def _intent_matches_pack(intent_lower: str, pack: ToolPackSpec) -> bool:
    for signal in pack.activation_signals:
        if intent_mentions_token(intent_lower, signal):
            return True
    return False


def _truncate_preferring_always(
    tools: list[Any],
    catalog: RuntimeToolPackCatalog,
    active_packs: frozenset[str],
    max_bound: int,
    *,
    unlock_priority: tuple[str, ...] = (),
) -> list[Any]:
    """Preferir always-on, luego packs recién unlock, luego resto; huérfanos al final."""
    always_ids = {p.pack_id for p in catalog.packs if p.always and p.pack_id in active_packs}
    # Último unlock gana (agent pidió ese pack → no truncar a favor de otro MCP).
    unlock_rank = {
        pid: idx for idx, pid in enumerate(reversed(tuple(unlock_priority)))
    }
    primary: list[Any] = []
    unlocked_secondary: list[tuple[int, Any]] = []
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
            continue
        if packs & active_packs:
            hit = packs & unlock_rank.keys()
            if hit:
                # Mejor (más reciente) rank entre packs de la tool.
                rank = max(unlock_rank[p] for p in hit)
                unlocked_secondary.append((rank, tool))
            else:
                secondary.append(tool)
            continue
        orphans.append(tool)
    unlocked_secondary.sort(key=lambda item: (-item[0],))
    ordered = (
        primary
        + [t for _, t in unlocked_secondary]
        + secondary
        + orphans
    )
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
