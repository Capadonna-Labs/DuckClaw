"""Carga y merge del catálogo de runtime tool packs (YAML + manifest)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from duckclaw.workers.tool_pack_models import (
    OrphanPolicy,
    RuntimePacksConfig,
    RuntimeToolPackCatalog,
    ToolPackMembers,
    ToolPackSpec,
)

_DEFAULT_CATALOG_PATH = Path(__file__).resolve().parent / "data" / "runtime_tool_packs.yaml"


def default_runtime_tool_packs_path() -> Path:
    return _DEFAULT_CATALOG_PATH


@lru_cache(maxsize=1)
def load_default_runtime_tool_pack_catalog() -> RuntimeToolPackCatalog:
    return catalog_from_mapping(_load_yaml_mapping(_DEFAULT_CATALOG_PATH))


def clear_runtime_tool_pack_catalog_cache() -> None:
    load_default_runtime_tool_pack_catalog.cache_clear()


def catalog_from_mapping(raw: dict[str, Any]) -> RuntimeToolPackCatalog:
    orphan = str(raw.get("orphan_policy") or "exclude").strip().lower()
    if orphan not in ("include", "exclude"):
        orphan = "exclude"
    max_bound = int(raw.get("max_bound_tools") or 16)
    if max_bound < 1:
        max_bound = 16
    packs_raw = raw.get("packs") or []
    if not isinstance(packs_raw, list):
        packs_raw = []
    packs: list[ToolPackSpec] = []
    for item in packs_raw:
        if not isinstance(item, dict):
            continue
        pack = _pack_from_mapping(item)
        if pack is not None:
            packs.append(pack)
    return RuntimeToolPackCatalog(
        version=int(raw.get("version") or 1),
        orphan_policy=orphan,  # type: ignore[arg-type]
        max_bound_tools=max_bound,
        packs=tuple(packs),
    )


def resolve_runtime_packs_config(spec: Any | None) -> RuntimePacksConfig:
    """Merge default catalog with ``spec.tool_surface_config.runtime_packs``."""
    base = load_default_runtime_tool_pack_catalog()
    section = _runtime_packs_section(spec)
    enabled = True
    if "enabled" in section:
        enabled = bool(section.get("enabled"))
    disabled = _as_str_frozenset(section.get("disabled_packs"))
    extra_always = _as_str_frozenset(section.get("extra_always"))
    catalog = _apply_catalog_overrides(base, section)
    return RuntimePacksConfig(
        enabled=enabled,
        catalog=catalog,
        disabled_packs=disabled,
        extra_always=extra_always,
        raw=dict(section),
    )


def runtime_packs_enabled(spec: Any | None) -> bool:
    return resolve_runtime_packs_config(spec).enabled


def _load_yaml_mapping(path: Path) -> dict[str, Any]:
    text = path.read_text(encoding="utf-8")
    data = yaml.safe_load(text) or {}
    if not isinstance(data, dict):
        raise ValueError(f"runtime tool packs catalog must be a mapping: {path}")
    return data


def _runtime_packs_section(spec: Any | None) -> dict[str, Any]:
    if spec is None:
        return {}
    raw = getattr(spec, "tool_surface_config", None) or {}
    if not isinstance(raw, dict):
        return {}
    section = raw.get("runtime_packs")
    return dict(section) if isinstance(section, dict) else {}


def _apply_catalog_overrides(
    base: RuntimeToolPackCatalog,
    section: dict[str, Any],
) -> RuntimeToolPackCatalog:
    orphan: OrphanPolicy = base.orphan_policy
    if "orphan_policy" in section:
        candidate = str(section.get("orphan_policy") or "").strip().lower()
        if candidate in ("include", "exclude"):
            orphan = candidate  # type: ignore[assignment]
    max_bound = base.max_bound_tools
    if "max_bound_tools" in section:
        try:
            max_bound = max(1, int(section.get("max_bound_tools")))
        except (TypeError, ValueError):
            pass

    overrides = section.get("pack_overrides") or {}
    if not isinstance(overrides, dict):
        overrides = {}

    packs: list[ToolPackSpec] = []
    for pack in base.packs:
        ov = overrides.get(pack.pack_id)
        if not isinstance(ov, dict):
            packs.append(pack)
            continue
        members = pack.members
        if isinstance(ov.get("members"), dict):
            members = _members_from_mapping(ov["members"], fallback=pack.members)
        signals = pack.activation_signals
        if "activation_signals" in ov:
            signals = tuple(
                str(s).strip().lower()
                for s in (ov.get("activation_signals") or [])
                if str(s).strip()
            )
        always = pack.always
        if "always" in ov:
            always = bool(ov.get("always"))
        description = pack.description
        if "description" in ov and str(ov.get("description") or "").strip():
            description = str(ov.get("description")).strip()
        packs.append(
            ToolPackSpec(
                pack_id=pack.pack_id,
                description=description,
                always=always,
                members=members,
                activation_signals=signals,
            )
        )

    # Packs adicionales solo vía override completo en ``extra_packs``.
    extra_packs = section.get("extra_packs") or []
    if isinstance(extra_packs, list):
        existing = {p.pack_id for p in packs}
        for item in extra_packs:
            if not isinstance(item, dict):
                continue
            pack = _pack_from_mapping(item)
            if pack is None or pack.pack_id in existing:
                continue
            packs.append(pack)
            existing.add(pack.pack_id)

    return RuntimeToolPackCatalog(
        version=base.version,
        orphan_policy=orphan,
        max_bound_tools=max_bound,
        packs=tuple(packs),
    )


def _pack_from_mapping(item: dict[str, Any]) -> ToolPackSpec | None:
    pack_id = str(item.get("id") or item.get("pack_id") or "").strip()
    if not pack_id:
        return None
    members_raw = item.get("members") if isinstance(item.get("members"), dict) else {}
    members = _members_from_mapping(members_raw, fallback=ToolPackMembers())
    signals = tuple(
        str(s).strip().lower()
        for s in (item.get("activation_signals") or [])
        if str(s).strip()
    )
    return ToolPackSpec(
        pack_id=pack_id,
        description=str(item.get("description") or "").strip(),
        always=bool(item.get("always")),
        members=members,
        activation_signals=signals,
    )


def _members_from_mapping(
    raw: dict[str, Any],
    *,
    fallback: ToolPackMembers,
) -> ToolPackMembers:
    exact_src = raw.get("exact") if "exact" in raw else sorted(fallback.exact)
    prefixes_src = raw.get("prefixes") if "prefixes" in raw else list(fallback.prefixes)
    regex_src = (
        raw.get("name_regexes") if "name_regexes" in raw else list(fallback.name_regexes)
    )
    exact = frozenset(str(x).strip() for x in (exact_src or []) if str(x).strip())
    prefixes = tuple(str(x).strip() for x in (prefixes_src or []) if str(x).strip())
    name_regexes = tuple(str(x).strip() for x in (regex_src or []) if str(x).strip())
    return ToolPackMembers(exact=exact, prefixes=prefixes, name_regexes=name_regexes)


def _as_str_frozenset(value: Any) -> frozenset[str]:
    if value is None:
        return frozenset()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple, set, frozenset)):
        return frozenset()
    return frozenset(str(x).strip() for x in value if str(x).strip())
