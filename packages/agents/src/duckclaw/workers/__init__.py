"""
Virtual Worker Factory — Plug & Play agent templates.

See specs/sistema_de_plantillas_de_agentes_virtual_worker_factory.md
"""

from duckclaw.workers.discovery import list_workers
from duckclaw.workers.factory import WorkerFactory
from duckclaw.workers.manifest import load_manifest, WorkerSpec

__all__ = ["WorkerFactory", "load_manifest", "list_workers", "WorkerSpec"]
