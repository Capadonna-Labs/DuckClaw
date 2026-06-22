"""Load optional extension StateDelta queue handlers (domain-agnostic)."""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from duckclaw.extensions.loader import (
    default_extension_lib_subpath,
    extension_roots,
    resolve_callable_entrypoint,
)
from duckclaw.extensions.manifest import (
    StateDeltaHandlerEntry,
    load_fly_extension_manifest,
)

_log = logging.getLogger(__name__)

_AsyncHandler = Callable[[Any, str], Awaitable[None]]


@dataclass(frozen=True)
class StateDeltaHandlerBinding:
    """Resolved Redis queue + async handler callable from an extension."""

    queue_name: str
    handler: _AsyncHandler
    label: str


def _resolve_queue_name(entry: StateDeltaHandlerEntry) -> str:
    if entry.queue_env:
        from_env = (os.environ.get(entry.queue_env) or "").strip()
        if from_env:
            return from_env
    if entry.queue:
        return entry.queue
    if entry.default_queue:
        return entry.default_queue
    return ""


def _entries_from_manifest() -> list[StateDeltaHandlerEntry]:
    manifest = load_fly_extension_manifest()
    if manifest is None:
        return []
    return list(manifest.state_delta_handlers)


def _entries_from_env() -> list[StateDeltaHandlerEntry]:
    raw = (os.environ.get("DUCKCLAW_EXTRA_STATE_DELTA_HANDLERS") or "").strip()
    if not raw:
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        _log.warning("DUCKCLAW_EXTRA_STATE_DELTA_HANDLERS is not valid JSON")
        return []
    if not isinstance(parsed, list):
        _log.warning("DUCKCLAW_EXTRA_STATE_DELTA_HANDLERS must be a JSON array")
        return []
    out: list[StateDeltaHandlerEntry] = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        entrypoint = str(item.get("entrypoint") or "").strip()
        if not entrypoint:
            continue
        out.append(
            StateDeltaHandlerEntry(
                queue=str(item.get("queue") or "").strip(),
                queue_env=str(item.get("queue_env") or "").strip(),
                default_queue=str(item.get("default_queue") or "").strip(),
                entrypoint=entrypoint,
                lib_path=str(item.get("lib_path") or "").strip(),
            )
        )
    return out


def _collect_handler_entries() -> list[StateDeltaHandlerEntry]:
    """Manifest entries first, then env augmentations."""
    seen: set[tuple[str, str]] = set()
    merged: list[StateDeltaHandlerEntry] = []
    for entry in _entries_from_manifest() + _entries_from_env():
        key = (entry.entrypoint, entry.lib_path or "")
        if key in seen:
            continue
        seen.add(key)
        merged.append(entry)
    return merged


def load_state_delta_handler_bindings() -> list[StateDeltaHandlerBinding]:
    """
    Resolve extension StateDelta handlers from manifest and/or env.

    Each entry must declare ``entrypoint`` (``module:callable``) and a queue via
    ``queue``, ``queue_env`` (+ optional ``default_queue``), relative to
    ``DUCKCLAW_EXTENSION_ROOT``.
    """
    roots = extension_roots()
    if not roots:
        return []

    manifest = load_fly_extension_manifest()
    default_lib = (manifest.lib_path if manifest else "") or default_extension_lib_subpath()

    bindings: list[StateDeltaHandlerBinding] = []
    for entry in _collect_handler_entries():
        queue_name = _resolve_queue_name(entry)
        if not queue_name:
            _log.warning(
                "state_delta handler skipped (no queue): entrypoint=%s",
                entry.entrypoint,
            )
            continue
        lib_path = (entry.lib_path or default_lib).strip() or default_lib
        handler_fn: _AsyncHandler | None = None
        label = entry.entrypoint
        for root in roots:
            # Do not reuse manifest.package_name: fly lib and db_writer handlers
            # often live under different lib_path subtrees.
            fn = resolve_callable_entrypoint(
                entry.entrypoint,
                root=root,
                package_name=None,
                lib_path=lib_path,
            )
            if fn is not None:
                handler_fn = fn  # type: ignore[assignment]
                label = f"{root.name}:{entry.entrypoint}"
                break
        if handler_fn is None:
            _log.warning(
                "state_delta handler not resolved: entrypoint=%s lib_path=%s",
                entry.entrypoint,
                lib_path,
            )
            continue
        bindings.append(
            StateDeltaHandlerBinding(
                queue_name=queue_name,
                handler=handler_fn,
                label=label,
            )
        )
    if bindings:
        _log.info(
            "extension state_delta handlers loaded: %s",
            ", ".join(f"{b.label}@{b.queue_name}" for b in bindings),
        )
    return bindings
