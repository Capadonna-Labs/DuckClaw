"""
duckclaw.forge — único punto de instanciación de agentes LangGraph.

Agents are loaded from the DB catalog at runtime. Router YAMLs
live in forge/ directly.
"""
from __future__ import annotations

from pathlib import Path

from .assembler import AgentAssembler

FORGE_DIR = Path(__file__).resolve().parent
ENTRY_ROUTER_YAML = FORGE_DIR / "entry_router.yaml"
MANAGER_ROUTER_YAML = FORGE_DIR / "manager_router.yaml"
WORKERS_TEMPLATES_DIR = FORGE_DIR / "seed"  # fallback bootstrap path (only "default")
PROJECTS_DIR = FORGE_DIR / "projects"
WORKFLOWS_DIR = FORGE_DIR / "workflows"

__all__ = [
    "AgentAssembler",
    "ENTRY_ROUTER_YAML",
    "MANAGER_ROUTER_YAML",
    "WORKERS_TEMPLATES_DIR",
    "PROJECTS_DIR",
    "WORKFLOWS_DIR",
]
