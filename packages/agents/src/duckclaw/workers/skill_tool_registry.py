"""Generic worker skill-to-tool registration.

The worker factory should not know individual integration config fields. This
module owns the mapping from configured skill names to their lazy registrars.
"""

from __future__ import annotations

import logging
from typing import Any

from duckclaw.workers.manifest import WorkerSpec

_log = logging.getLogger(__name__)


def worker_skill_config(spec: WorkerSpec, skill_name: str) -> dict[str, Any] | None:
    configs = getattr(spec, "skill_configs", None) or {}
    if not isinstance(configs, dict):
        return None
    key = str(skill_name or "").strip().lower().replace("-", "_")
    cfg = configs.get(key)
    return cfg if isinstance(cfg, dict) else None


def register_pre_llm_skill_tools(
    tools: list[Any],
    spec: WorkerSpec,
    *,
    tool_surface: str,
    incoming_hint: str,
) -> None:
    """Register configured skill tools that do not need the built LLM."""
    _register_google_trends(tools, spec, tool_surface=tool_surface)
    _register_reddit(tools, spec, tool_surface=tool_surface, incoming_hint=incoming_hint)


def register_post_llm_skill_tools(
    tools: list[Any],
    spec: WorkerSpec,
    *,
    db: Any,
    llm: Any,
) -> None:
    """Register configured skill tools that may depend on db or llm handles."""
    research_config = worker_skill_config(spec, "research")
    _register_research(tools, research_config, llm=llm)
    _register_openweather(tools, spec, research_config=research_config)
    _register_tailscale(tools, spec)
    _register_comfyui(tools, spec, db=db)


def read_visual_artifact_image_as_b64(artifact_path: str, tenant_id: str) -> str:
    """Read a generated visual artifact without coupling factory to a bridge module."""
    try:
        from duckclaw.forge.skills.comfyui_bridge import read_artifact_image_as_b64

        return str(read_artifact_image_as_b64(artifact_path, tenant_id) or "")
    except Exception:
        _log.debug("visual artifact read skipped", exc_info=True)
        return ""


def _register_google_trends(tools: list[Any], spec: WorkerSpec, *, tool_surface: str) -> None:
    config = worker_skill_config(spec, "google_trends")
    if tool_surface != "full" or config is None:
        return
    try:
        from duckclaw.forge.skills.google_trends_bridge import register_google_trends_skill

        register_google_trends_skill(tools, config)
    except Exception:
        _log.debug("google_trends skill registration skipped", exc_info=True)


def _register_reddit(
    tools: list[Any],
    spec: WorkerSpec,
    *,
    tool_surface: str,
    incoming_hint: str,
) -> None:
    config = worker_skill_config(spec, "reddit")
    hint = str(incoming_hint or "").strip().lower()
    should_register = bool(config) and (
        tool_surface == "context_synthesis"
        or (tool_surface == "url_research" and "reddit.com" in hint)
        or (tool_surface == "full" and "reddit.com" in hint)
    )
    if not should_register:
        return
    try:
        from duckclaw.forge.skills.reddit_bridge import register_reddit_skill

        register_reddit_skill(tools, config)
    except Exception:
        _log.debug("reddit skill registration skipped", exc_info=True)


def _register_research(tools: list[Any], config: dict[str, Any] | None, *, llm: Any) -> None:
    if not config:
        return
    try:
        from duckclaw.forge.skills.research_bridge import register_research_skill

        register_research_skill(tools, config, llm=llm)
    except Exception:
        _log.debug("research skill registration skipped", exc_info=True)


def _register_openweather(
    tools: list[Any],
    spec: WorkerSpec,
    *,
    research_config: dict[str, Any] | None,
) -> None:
    config = worker_skill_config(spec, "openweather")
    if config is None:
        return
    try:
        from duckclaw.forge.skills.openweather_bridge import register_openweather_skill

        register_openweather_skill(tools, config, research_config)
    except Exception:
        _log.debug("openweather skill registration skipped", exc_info=True)


def _register_tailscale(tools: list[Any], spec: WorkerSpec) -> None:
    config = worker_skill_config(spec, "tailscale")
    if not config:
        return
    try:
        from duckclaw.forge.skills.tailscale_bridge import register_tailscale_skill

        register_tailscale_skill(tools, config)
    except Exception:
        _log.debug("tailscale skill registration skipped", exc_info=True)


def _register_comfyui(tools: list[Any], spec: WorkerSpec, *, db: Any) -> None:
    config = worker_skill_config(spec, "comfyui")
    if config is None:
        return
    try:
        from duckclaw.forge.skills.comfyui_bridge import register_comfyui_skill

        register_comfyui_skill(tools, config, duckclaw_db=db)
    except Exception:
        _log.debug("comfyui skill registration skipped", exc_info=True)
