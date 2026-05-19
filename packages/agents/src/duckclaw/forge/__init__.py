"""
duckclaw.forge — único punto de instanciación de agentes LangGraph.

Toda la configuración de agentes se declara en YAML dentro de forge/templates/.
AgentAssembler lee el YAML y devuelve un LangGraph compilado listo para usar.

Spec: Agent Forge Refactor
"""

from pathlib import Path

from .assembler import AgentAssembler

# Rutas a templates built-in
FORGE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = FORGE_DIR / "templates"
ENTRY_ROUTER_YAML = TEMPLATES_DIR / "entry_router.yaml"
MANAGER_ROUTER_YAML = TEMPLATES_DIR / "manager_router.yaml"
# Ruta a plantillas de workers: forge/templates/ (cada subdir con manifest.yaml es un worker)
# finanz, personalizable, powerseal, research_worker, support, etc.
WORKERS_TEMPLATES_DIR = TEMPLATES_DIR
INDUSTRIES_TEMPLATES_DIR = TEMPLATES_DIR / "industries"
PROJECTS_DIR = FORGE_DIR / "projects"

__all__ = [
    "AgentAssembler",
    "ENTRY_ROUTER_YAML",
    "MANAGER_ROUTER_YAML",
    "WORKERS_TEMPLATES_DIR",
    "INDUSTRIES_TEMPLATES_DIR",
    "PROJECTS_DIR",
    "TEMPLATES_DIR",
]
