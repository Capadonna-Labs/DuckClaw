"""Modelos inmutables para runtime tool packs."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

OrphanPolicy = Literal["include", "exclude"]


@dataclass(frozen=True)
class ToolPackMembers:
    exact: frozenset[str] = field(default_factory=frozenset)
    prefixes: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolPackSpec:
    pack_id: str
    description: str
    always: bool
    members: ToolPackMembers
    activation_signals: tuple[str, ...] = ()

    def matches_tool(self, tool_name: str) -> bool:
        name = (tool_name or "").strip()
        if not name:
            return False
        if name in self.members.exact:
            return True
        return any(name.startswith(prefix) for prefix in self.members.prefixes if prefix)


@dataclass(frozen=True)
class RuntimeToolPackCatalog:
    version: int
    orphan_policy: OrphanPolicy
    max_bound_tools: int
    packs: tuple[ToolPackSpec, ...]

    def pack_by_id(self) -> dict[str, ToolPackSpec]:
        return {p.pack_id: p for p in self.packs}

    def packs_for_tool(self, tool_name: str) -> frozenset[str]:
        return frozenset(p.pack_id for p in self.packs if p.matches_tool(tool_name))

    def is_managed(self, tool_name: str) -> bool:
        return bool(self.packs_for_tool(tool_name))


@dataclass(frozen=True)
class RuntimePacksConfig:
    """Config efectiva (catálogo default ∪ overrides del manifest)."""

    enabled: bool
    catalog: RuntimeToolPackCatalog
    disabled_packs: frozenset[str] = field(default_factory=frozenset)
    extra_always: frozenset[str] = field(default_factory=frozenset)
    raw: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class PackFilterResult:
    tools: list[Any]
    active_packs: frozenset[str]
    bound_names: tuple[str, ...]
    managed_hidden: int
    applied: bool
    truncated: bool
