"""Conexión hub activa durante delegación worker (evita RO+RW en el mismo .duckdb)."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_report_engine_hub_db: ContextVar[Any] = ContextVar("duckclaw_report_engine_hub_db", default=None)


def set_report_engine_hub_db(db: Any | None) -> None:
    _report_engine_hub_db.set(db)


def get_report_engine_hub_db() -> Any | None:
    return _report_engine_hub_db.get()


def clear_report_engine_hub_db() -> None:
    _report_engine_hub_db.set(None)
