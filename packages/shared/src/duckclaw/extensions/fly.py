"""External fly-command dispatch configured via environment variables."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable, Optional

from duckclaw.extensions.loader import (
    extension_roots,
    invalidate_extension_loader_cache,
    resolve_callable_entrypoint,
)
from duckclaw.extensions.manifest import FlyExtensionManifest, load_fly_extension_manifest

_log = logging.getLogger(__name__)

_DISPATCHER_CACHE: list[Callable[..., Any]] | None = None
_READ_ONLY_CACHE: frozenset[str] | None = None


def _split_list_env(name: str) -> list[str]:
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return []
    parts: list[str] = []
    for chunk in raw.replace(";", ",").split(","):
        text = chunk.strip()
        if text:
            parts.append(text)
    return parts


def _normalize_command_name(name: str) -> str:
    return (name or "").strip().lower().replace("_", "-")


def _manifest_for_roots() -> Optional[FlyExtensionManifest]:
    try:
        return load_fly_extension_manifest()
    except Exception:
        _log.debug("fly extension manifest load failed", exc_info=True)
        return None


def _dispatcher_specs() -> list[tuple[str, str | None, str | None]]:
    """
    Return (entrypoint, package_name, lib_path) tuples.

    Manifest dispatchers take precedence; ``DUCKCLAW_FLY_DISPATCHERS`` augments when manifest is absent
    or adds extras when manifest exists but has no dispatchers.
    """
    manifest = _manifest_for_roots()
    specs: list[str] = []
    pkg: str | None = None
    lib_path: str | None = None
    if manifest is not None:
        pkg = manifest.package_name or None
        lib_path = manifest.lib_path or None
        specs.extend(list(manifest.fly_dispatchers))
    env_specs = _split_list_env("DUCKCLAW_FLY_DISPATCHERS")
    if env_specs:
        if not specs:
            specs = env_specs
        else:
            seen = set(specs)
            for item in env_specs:
                if item not in seen:
                    specs.append(item)
                    seen.add(item)
    return [(s, pkg, lib_path) for s in specs]


def _build_dispatchers() -> list[Callable[..., Any]]:
    roots = extension_roots()
    if not roots:
        return []
    dispatchers: list[Callable[..., Any]] = []
    for entrypoint, package_name, lib_path in _dispatcher_specs():
        bound: Callable[..., Any] | None = None
        for root in roots:
            fn = resolve_callable_entrypoint(
                entrypoint,
                root=root,
                package_name=package_name,
                lib_path=lib_path,
            )
            if fn is not None:
                bound = fn
                break
        if bound is not None:
            dispatchers.append(bound)
        else:
            _log.warning("fly extension dispatcher not found: %s", entrypoint)
    return dispatchers


def get_fly_dispatchers() -> list[Callable[..., Any]]:
    """Cached list of external fly dispatch callables."""
    global _DISPATCHER_CACHE
    if _DISPATCHER_CACHE is None:
        _DISPATCHER_CACHE = _build_dispatchers()
    return _DISPATCHER_CACHE


def extension_fly_read_only_command_names() -> frozenset[str]:
    """
    Extra slash commands safe for read-only vault opens.

    Sources: manifest ``read_only_commands``, then ``DUCKCLAW_FLY_READ_ONLY_EXTRA``.
    """
    global _READ_ONLY_CACHE
    if _READ_ONLY_CACHE is not None:
        return _READ_ONLY_CACHE
    names: set[str] = set()
    manifest = _manifest_for_roots()
    if manifest is not None:
        for cmd in manifest.read_only_commands:
            norm = _normalize_command_name(cmd)
            if norm:
                names.add(norm)
                if "-" in norm:
                    names.add(norm.replace("-", "_"))
    for raw in _split_list_env("DUCKCLAW_FLY_READ_ONLY_EXTRA"):
        norm = _normalize_command_name(raw)
        if norm:
            names.add(norm)
            if "-" in norm:
                names.add(norm.replace("-", "_"))
    _READ_ONLY_CACHE = frozenset(names)
    return _READ_ONLY_CACHE


def invalidate_extension_fly_cache() -> None:
    """Reset cached dispatchers/read-only sets (tests)."""
    global _DISPATCHER_CACHE, _READ_ONLY_CACHE
    _DISPATCHER_CACHE = None
    _READ_ONLY_CACHE = None
    invalidate_extension_loader_cache()


def dispatch_extension_fly_command(
    name: str,
    db: Any,
    chat_id: Any,
    args: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
    vault_user_id: Any = None,
    username: str = "",
    entry_worker_id: str | None = None,
) -> Optional[str]:
    """
    Invoke registered external fly dispatchers until one returns a non-None str.

    ``None`` from a dispatcher means "not handled"; exceptions are logged and skipped.
    """
    if not get_fly_dispatchers():
        return None
    kwargs = {
        "requester_id": requester_id,
        "tenant_id": tenant_id,
        "vault_user_id": vault_user_id,
        "username": username,
        "entry_worker_id": entry_worker_id,
    }
    for dispatcher in get_fly_dispatchers():
        try:
            out = dispatcher(name, db, chat_id, args, **kwargs)
        except Exception:
            _log.debug("extension fly dispatcher failed for /%s", name, exc_info=True)
            continue
        if out is not None:
            return str(out)
    return None
