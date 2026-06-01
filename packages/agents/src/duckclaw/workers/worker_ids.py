"""
Central registry of logical worker IDs.

Gradual extraction: custom workers (finanz, quant_trader, pqrsd_assistant, etc.)
will move out of the monorepo; only the default worker stays. This module
centralizes ID literals so hot paths can switch to env/config without scattered
string comparisons.

Override any ID at runtime via ``DUCKCLAW_WORKER_{NAME}`` (e.g.
``DUCKCLAW_WORKER_FINANZ=finance_bot``).

See specs/sistema_de_plantillas_de_agentes_virtual_worker_factory.md
"""

from __future__ import annotations

import os

__all__ = [
    "WORKER_FINANZ",
    "WORKER_QUANT_TRADER",
    "WORKER_PQRSD_ASSISTANT",
    "WORKER_JOB_HUNTER",
    "WORKER_SIATA_ANALYST",
    "MARKET_WORKERS",
    "PLOT_CAPABLE_WORKERS",
    "env_worker_id",
    "normalize_worker_id",
    "is_worker",
    "is_finanz",
    "is_market_worker",
    "is_quant_trader",
    "is_pqrsd_assistant",
    "is_job_hunter",
    "is_siata_analyst",
]


def env_worker_id(name: str, default: str) -> str:
    """Return env-overridable worker ID: ``DUCKCLAW_WORKER_{NAME}``."""
    return os.environ.get(f"DUCKCLAW_WORKER_{name.upper()}", default)


WORKER_FINANZ = env_worker_id("FINANZ", "finanz")
WORKER_QUANT_TRADER = env_worker_id("QUANT_TRADER", "quant_trader")
WORKER_PQRSD_ASSISTANT = env_worker_id("PQRSD_ASSISTANT", "pqrsd_assistant")
WORKER_JOB_HUNTER = env_worker_id("JOB_HUNTER", "job_hunter")
WORKER_SIATA_ANALYST = env_worker_id("SIATA_ANALYST", "siata_analyst")

MARKET_WORKERS = frozenset({WORKER_FINANZ, WORKER_QUANT_TRADER})
PLOT_CAPABLE_WORKERS = frozenset({WORKER_SIATA_ANALYST, WORKER_FINANZ})


def normalize_worker_id(worker_id: str | None) -> str:
    return (worker_id or "").strip().lower()


def is_worker(worker_id: str | None, *expected: str) -> bool:
    lid = normalize_worker_id(worker_id)
    return lid in expected


def is_finanz(worker_id: str | None) -> bool:
    return normalize_worker_id(worker_id) == WORKER_FINANZ


def is_market_worker(worker_id: str | None) -> bool:
    return normalize_worker_id(worker_id) in MARKET_WORKERS


def is_quant_trader(worker_id: str | None) -> bool:
    return normalize_worker_id(worker_id) == WORKER_QUANT_TRADER


def is_pqrsd_assistant(worker_id: str | None) -> bool:
    return normalize_worker_id(worker_id) == WORKER_PQRSD_ASSISTANT


def is_job_hunter(worker_id: str | None) -> bool:
    return normalize_worker_id(worker_id) == WORKER_JOB_HUNTER


def is_siata_analyst(worker_id: str | None) -> bool:
    return normalize_worker_id(worker_id) == WORKER_SIATA_ANALYST
