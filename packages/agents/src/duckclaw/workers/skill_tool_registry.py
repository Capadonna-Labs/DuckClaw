"""Generic worker skill-to-tool registration.

The worker factory should not know individual integration config fields. This
module owns the mapping from configured skill names to their lazy registrars.
"""

from __future__ import annotations

import importlib
import logging
from dataclasses import dataclass, field
from typing import Any, Literal

from duckclaw.workers.manifest import WorkerSpec

_log = logging.getLogger(__name__)

SkillToolPhase = Literal["pre_llm", "post_llm"]


@dataclass(frozen=True)
class SkillToolRegistrar:
    """Declarative binding from a configured skill to a lazy tool registrar."""

    skill_name: str
    phase: SkillToolPhase
    registrar_path: str
    surfaces: tuple[str, ...] = ()
    hint_surfaces: tuple[str, ...] = ()
    hint_contains: tuple[str, ...] = ()
    empty_config_registers: bool = True
    positional_context: tuple[str, ...] = ()
    keyword_context: dict[str, str] = field(default_factory=dict)


DEFAULT_SKILL_TOOL_REGISTRY: tuple[SkillToolRegistrar, ...] = (
    SkillToolRegistrar(
        skill_name="google_trends",
        phase="pre_llm",
        registrar_path="duckclaw.forge.skills.google_trends_bridge:register_google_trends_skill",
        surfaces=("full",),
    ),
    SkillToolRegistrar(
        skill_name="reddit",
        phase="pre_llm",
        registrar_path="duckclaw.forge.skills.reddit_bridge:register_reddit_skill",
        surfaces=("context_synthesis",),
        hint_surfaces=("url_research", "full"),
        hint_contains=("reddit.com",),
        empty_config_registers=False,
    ),
    SkillToolRegistrar(
        skill_name="research",
        phase="post_llm",
        registrar_path="duckclaw.forge.skills.research_bridge:register_research_skill",
        empty_config_registers=False,
        keyword_context={"llm": "llm"},
    ),
    SkillToolRegistrar(
        skill_name="openweather",
        phase="post_llm",
        registrar_path="duckclaw.forge.skills.openweather_bridge:register_openweather_skill",
        positional_context=("research_config",),
    ),
    SkillToolRegistrar(
        skill_name="tailscale",
        phase="post_llm",
        registrar_path="duckclaw.forge.skills.tailscale_bridge:register_tailscale_skill",
        empty_config_registers=False,
    ),
    SkillToolRegistrar(
        skill_name="comfyui",
        phase="post_llm",
        registrar_path="duckclaw.forge.skills.comfyui_bridge:register_comfyui_skill",
        keyword_context={"duckclaw_db": "db"},
    ),
    SkillToolRegistrar(
        skill_name="higgsfield",
        phase="post_llm",
        registrar_path="duckclaw.forge.skills.higgsfield_bridge:register_higgsfield_skill",
        keyword_context={
            "duckclaw_db": "db",
            "worker_id": "worker_id",
            "tenant_id": "tenant_id",
        },
    ),
    SkillToolRegistrar(
        skill_name="slm_eval",
        phase="post_llm",
        registrar_path="duckclaw.forge.skills.slm_eval_bridge:register_slm_eval_skill",
        empty_config_registers=True,
        keyword_context={"db": "db"},
    ),
)

VISUAL_ARTIFACT_READER_PATH = "duckclaw.forge.skills.comfyui_bridge:read_artifact_image_as_b64"


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
    _register_configured_skill_tools(
        tools,
        spec,
        phase="pre_llm",
        tool_surface=tool_surface,
        incoming_hint=incoming_hint,
        context={},
    )


def register_post_llm_skill_tools(
    tools: list[Any],
    spec: WorkerSpec,
    *,
    db: Any,
    llm: Any,
    tenant_id: str = "default",
) -> None:
    """Register configured skill tools that may depend on db or llm handles."""
    _register_configured_skill_tools(
        tools,
        spec,
        phase="post_llm",
        tool_surface="",
        incoming_hint="",
        context={
            "db": db,
            "llm": llm,
            "research_config": worker_skill_config(spec, "research"),
            "worker_id": str(getattr(spec, "worker_id", None) or ""),
            "tenant_id": str(tenant_id or "default"),
        },
    )


def read_visual_artifact_image_as_b64(artifact_path: str, tenant_id: str) -> str:
    """Read a generated visual artifact without coupling factory to a bridge module."""
    try:
        reader = _load_callable(VISUAL_ARTIFACT_READER_PATH)
        return str(reader(artifact_path, tenant_id) or "")
    except Exception:
        _log.debug("visual artifact read skipped", exc_info=True)
        return ""


def _register_configured_skill_tools(
    tools: list[Any],
    spec: WorkerSpec,
    *,
    phase: SkillToolPhase,
    tool_surface: str,
    incoming_hint: str,
    context: dict[str, Any],
) -> None:
    for descriptor in DEFAULT_SKILL_TOOL_REGISTRY:
        if descriptor.phase != phase:
            continue
        if not _descriptor_is_active(descriptor, tool_surface=tool_surface, incoming_hint=incoming_hint):
            continue
        config = worker_skill_config(spec, descriptor.skill_name)
        if config is None:
            continue
        if not config and not descriptor.empty_config_registers:
            continue
        _invoke_registrar(tools, descriptor, config, context)


def _descriptor_is_active(
    descriptor: SkillToolRegistrar,
    *,
    tool_surface: str,
    incoming_hint: str,
) -> bool:
    surface = str(tool_surface or "").strip()
    if surface and surface in descriptor.surfaces:
        return True
    hint = str(incoming_hint or "").strip().lower()
    if surface in descriptor.hint_surfaces and any(item.lower() in hint for item in descriptor.hint_contains):
        return True
    return not descriptor.surfaces and not descriptor.hint_surfaces


def _invoke_registrar(
    tools: list[Any],
    descriptor: SkillToolRegistrar,
    config: dict[str, Any],
    context: dict[str, Any],
) -> None:
    try:
        registrar = _load_callable(descriptor.registrar_path)
        positional_args = [context.get(name) for name in descriptor.positional_context]
        keyword_args = {
            kwarg_name: context.get(context_name)
            for kwarg_name, context_name in descriptor.keyword_context.items()
        }
        registrar(tools, config, *positional_args, **keyword_args)
    except Exception:
        _log.debug("%s skill registration skipped", descriptor.skill_name, exc_info=True)


def _load_callable(path: str) -> Any:
    module_name, _, attr_name = str(path or "").partition(":")
    if not module_name or not attr_name:
        raise ValueError(f"Invalid callable path: {path!r}")
    module = importlib.import_module(module_name)
    target = getattr(module, attr_name)
    if not callable(target):
        raise TypeError(f"Configured registrar is not callable: {path!r}")
    return target
