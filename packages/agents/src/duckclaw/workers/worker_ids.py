"""
Compatibility shim for legacy logical worker IDs.

New runtime code should use ``duckclaw.workers.identity`` and DB-backed
``WorkerRuntimePolicy``. This module remains only to avoid breaking callers
that still import legacy constants/predicates during the migration.

Override any ID at runtime via ``DUCKCLAW_WORKER_{NAME}`` (e.g.
``DUCKCLAW_WORKER_FINANZ=finance_bot``).

See specs/features/platform/RAG_TRANSVERSAL_DB_FIRST.md
"""

from __future__ import annotations

import os
import warnings

from duckclaw.workers.identity import is_worker as _identity_is_worker
from duckclaw.workers.identity import normalize_worker_id as _identity_normalize_worker_id

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


def _warn_legacy_api(name: str) -> None:
    warnings.warn(
        f"duckclaw.workers.worker_ids.{name} is deprecated; use duckclaw.workers.identity",
        DeprecationWarning,
        stacklevel=2,
    )


def normalize_worker_id(worker_id: str | None) -> str:
    _warn_legacy_api("normalize_worker_id")
    return _identity_normalize_worker_id(worker_id)


def is_worker(worker_id: str | None, *expected: str) -> bool:
    _warn_legacy_api("is_worker")
    return _identity_is_worker(worker_id, *expected)


def is_finanz(worker_id: str | None) -> bool:
    _warn_legacy_api("is_finanz")
    return _identity_is_worker(worker_id, WORKER_FINANZ)


def is_market_worker(worker_id: str | None) -> bool:
    _warn_legacy_api("is_market_worker")
    return _identity_normalize_worker_id(worker_id) in MARKET_WORKERS


def is_quant_trader(worker_id: str | None) -> bool:
    _warn_legacy_api("is_quant_trader")
    return _identity_is_worker(worker_id, WORKER_QUANT_TRADER)


def is_pqrsd_assistant(worker_id: str | None) -> bool:
    _warn_legacy_api("is_pqrsd_assistant")
    return _identity_is_worker(worker_id, WORKER_PQRSD_ASSISTANT)


def is_job_hunter(worker_id: str | None) -> bool:
    _warn_legacy_api("is_job_hunter")
    return _identity_is_worker(worker_id, WORKER_JOB_HUNTER)


def is_siata_analyst(worker_id: str | None) -> bool:
    _warn_legacy_api("is_siata_analyst")
    return _identity_is_worker(worker_id, WORKER_SIATA_ANALYST)
