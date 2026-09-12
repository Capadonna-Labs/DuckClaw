"""Deprecated shim — prefer ``duckclaw.forge.skills.loop_bridge``."""
from duckclaw.forge.skills.loop_bridge import *  # noqa: F403
from duckclaw.forge.skills.loop_bridge import register_loop_skill as register_meditate_skill

__all__ = ["register_meditate_skill", "register_loop_skill"]
