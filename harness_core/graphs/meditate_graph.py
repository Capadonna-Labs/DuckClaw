"""Deprecated shim — prefer ``harness_core.graphs.loop_graph``."""
from harness_core.graphs.loop_graph import *  # noqa: F403
from harness_core.graphs.loop_graph import _plan_rules as _plan_rules

__all__ = ["_plan_rules"]
