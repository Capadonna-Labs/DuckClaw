"""
Virtual Worker Factory — Plug & Play agent templates.

See docs/core/03_Skills_and_Tooling_Framework.md
"""

from duckclaw.workers.discovery import list_workers
from duckclaw.workers.factory import WorkerFactory
from duckclaw.workers.manifest import load_manifest, WorkerSpec

__all__ = ["WorkerFactory", "load_manifest", "list_workers", "WorkerSpec"]
