"""Parse optional ``DUCKCLAW_FLY_MANIFEST`` YAML for extension fly commands."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass(frozen=True)
class FlyExtensionManifest:
    """Declarative fly extension config supplied by an external repo."""

    lib_path: str = "lib"
    package_name: str = ""
    fly_dispatchers: tuple[str, ...] = ()
    worker_skill_hooks: tuple[str, ...] = ()
    read_only_commands: tuple[str, ...] = ()
    help_entries: tuple[tuple[str, str], ...] = ()
    source_path: Optional[Path] = None


def _normalize_command_name(name: str) -> str:
    return (name or "").strip().lower().replace("_", "-")


def _parse_help_entries(raw: Any) -> tuple[tuple[str, str], ...]:
    if not isinstance(raw, list):
        return ()
    out: list[tuple[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        cmd = _normalize_command_name(str(item.get("name") or ""))
        desc = str(item.get("description") or "").strip()
        if cmd:
            out.append((cmd, desc))
    return tuple(out)


def _parse_hook_list(raw: Any) -> tuple[str, ...]:
    if not isinstance(raw, list):
        return ()
    out: list[str] = []
    for item in raw:
        text = str(item or "").strip()
        if text:
            out.append(text)
    return tuple(out)


def _parse_manifest_dict(data: dict[str, Any], *, source: Path | None) -> FlyExtensionManifest:
    dispatchers_raw = data.get("fly_dispatchers") or []
    hooks_raw = data.get("worker_skill_hooks") or []
    read_only_raw = data.get("read_only_commands") or []
    dispatchers: list[str] = []
    if isinstance(dispatchers_raw, list):
        for item in dispatchers_raw:
            text = str(item or "").strip()
            if text:
                dispatchers.append(text)
    read_only: list[str] = []
    if isinstance(read_only_raw, list):
        for item in read_only_raw:
            cmd = _normalize_command_name(str(item or ""))
            if cmd:
                read_only.append(cmd)
    lib_path = str(data.get("lib_path") or "lib").strip() or "lib"
    package_name = str(data.get("package_name") or "").strip()
    return FlyExtensionManifest(
        lib_path=lib_path,
        package_name=package_name,
        fly_dispatchers=tuple(dispatchers),
        worker_skill_hooks=_parse_hook_list(hooks_raw),
        read_only_commands=tuple(read_only),
        help_entries=_parse_help_entries(data.get("help_entries")),
        source_path=source,
    )


def _load_yaml_file(path: Path) -> dict[str, Any]:
    try:
        import yaml  # type: ignore[import-untyped]
    except ImportError as exc:
        raise RuntimeError(
            "PyYAML is required to load DUCKCLAW_FLY_MANIFEST; install PyYAML or use env-only config"
        ) from exc
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return {}
    return raw


def resolve_manifest_path() -> Optional[Path]:
    """Resolve manifest file from ``DUCKCLAW_FLY_MANIFEST`` (absolute or relative to extension root)."""
    raw = (os.environ.get("DUCKCLAW_FLY_MANIFEST") or "").strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if candidate.is_file():
        return candidate.resolve()
    for root in _extension_roots_for_manifest():
        under_root = (root / raw).resolve()
        if under_root.is_file():
            return under_root
    return None


def _extension_roots_for_manifest() -> list[Path]:
    from duckclaw.extensions.loader import extension_roots

    return extension_roots()


def load_fly_extension_manifest() -> Optional[FlyExtensionManifest]:
    """Load manifest if configured; returns None when unset or missing."""
    path = resolve_manifest_path()
    if path is None:
        return None
    try:
        data = _load_yaml_file(path)
    except Exception:
        return None
    return _parse_manifest_dict(data, source=path)
