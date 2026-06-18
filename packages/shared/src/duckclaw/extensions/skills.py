"""External worker skill registration hooks configured via environment variables."""

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

_HOOKS_CACHE: list[Callable[..., Any]] | None = None


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


def _manifest_for_roots() -> Optional[FlyExtensionManifest]:
    try:
        return load_fly_extension_manifest()
    except Exception:
        _log.debug("worker skill extension manifest load failed", exc_info=True)
        return None


def _hook_specs() -> list[tuple[str, str | None, str | None]]:
    """Return (entrypoint, package_name, lib_path) tuples from manifest + env."""
    manifest = _manifest_for_roots()
    specs: list[str] = []
    pkg: str | None = None
    lib_path: str | None = None
    if manifest is not None:
        pkg = manifest.package_name or None
        lib_path = manifest.lib_path or None
        specs.extend(list(manifest.worker_skill_hooks))
    env_specs = _split_list_env("DUCKCLAW_WORKER_SKILL_HOOKS")
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


def _build_hooks() -> list[Callable[..., Any]]:
    roots = extension_roots()
    if not roots:
        return []
    hooks: list[Callable[..., Any]] = []
    for entrypoint, package_name, lib_path in _hook_specs():
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
            hooks.append(bound)
        else:
            _log.warning("worker skill extension hook not found: %s", entrypoint)
    return hooks


def get_worker_skill_hooks() -> list[Callable[..., Any]]:
    """Cached list of external worker skill registration callables."""
    global _HOOKS_CACHE
    if _HOOKS_CACHE is None:
        _HOOKS_CACHE = _build_hooks()
    return _HOOKS_CACHE


def invalidate_extension_skills_cache() -> None:
    """Reset cached skill hooks (tests / hot reload)."""
    global _HOOKS_CACHE
    _HOOKS_CACHE = None
    invalidate_extension_loader_cache()


def invoke_extension_worker_skill_hooks(
    *,
    tools: list[Any],
    spec: Any,
    db: Any,
    llm: Any,
    logical_worker_id: str,
    worker_path: str,
) -> None:
    """
    Invoke registered external worker skill hooks.

    Passes only generic worker context; domain-specific role detection belongs in the external hook.

    Exceptions are logged and skipped so one broken extension does not break graph build.
    """
    hooks = get_worker_skill_hooks()
    if not hooks:
        return
    kwargs = {
        "tools": tools,
        "spec": spec,
        "db": db,
        "llm": llm,
        "logical_worker_id": logical_worker_id,
        "worker_path": worker_path,
    }
    for hook in hooks:
        try:
            hook(**kwargs)
        except Exception:
            _log.debug(
                "extension worker skill hook failed for %s",
                logical_worker_id,
                exc_info=True,
            )
