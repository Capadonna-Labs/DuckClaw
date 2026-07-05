"""db-writer VLM state delta handler."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import patch

import duckdb

_REPO = Path(__file__).resolve().parent.parent
_WRITER = _REPO / "services" / "db-writer"


def _import_vlm_handler():
    writer_s = str(_WRITER)
    sys.path.insert(0, writer_s)
    try:
        import vlm_state_delta_handler as mod  # noqa: WPS433

        return mod
    finally:
        if sys.path and sys.path[0] == writer_s:
            sys.path.pop(0)
        for stale in ("main", "core.config"):
            loaded = sys.modules.get(stale)
            if loaded is not None and getattr(loaded, "__file__", "") and str(_WRITER) in str(
                loaded.__file__
            ):
                sys.modules.pop(stale, None)


def test_vlm_state_delta_persists_semantic_memory(tmp_path) -> None:
    hub = tmp_path / "hub.duckdb"
    duckdb.connect(str(hub)).close()
    vlm_mod = _import_vlm_handler()

    message = json.dumps(
        {
            "tenant_id": "tenant_a",
            "delta_type": "VLM_CONTEXT_EXTRACTED",
            "mutation": {
                "image_hash": "abc123def456",
                "vlm_summary": "Gráfico con tendencia alcista",
                "confidence_score": 0.88,
            },
        }
    )

    with patch.object(vlm_mod, "get_gateway_db_path", return_value=str(hub)):
        vlm_mod._sync_handle_vlm_state_delta(message)

    con = duckdb.connect(str(hub), read_only=True)
    try:
        row = con.execute(
            "SELECT id, source FROM main.semantic_memory WHERE id LIKE 'vlm_%'"
        ).fetchone()
        assert row is not None
        assert row[1] == "vlm_tenant:tenant_a"
    finally:
        con.close()
