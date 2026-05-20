"""Regresión: db-writer en sys.path no debe romper import de app del Gateway."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parent.parent


def _load_visual_state_delta_test_module() -> None:
    path = _REPO / "tests" / "test_visual_state_delta.py"
    spec = importlib.util.spec_from_file_location("test_visual_state_delta", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)


def test_gateway_app_import_after_db_writer_path_pollution() -> None:
    _load_visual_state_delta_test_module()
    writer = str(_REPO / "services" / "db-writer")
    assert writer in sys.path
    assert sys.path[0] != writer or str(_REPO / "services" / "api-gateway") in sys.path[:2]

    from gateway_import import load_gateway_app

    app = load_gateway_app()
    assert app is not None
    assert "FastAPI" in type(app).__name__
