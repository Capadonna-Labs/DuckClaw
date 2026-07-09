"""db-writer meditate state delta handler."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import duckdb

_REPO = Path(__file__).resolve().parent.parent
_WRITER = _REPO / "services" / "db-writer"
if str(_WRITER) not in sys.path:
    sys.path.append(str(_WRITER))

from loop_state_delta_handler import _sync_handle_loop_state_delta  # noqa: E402
from models.loop_state_delta import MeditateStateDelta  # noqa: E402


def test_loop_state_delta_roundtrip() -> None:
    delta = MeditateStateDelta(
        delta_type="UPSERT_MEDITATE_AUDIT",
        tenant_id="default",
        user_id="default",
        target_db_path="/tmp/x.duckdb",
        mutation={
            "run_id": "run-1",
            "distance_vector": {"error_rate_pct": 1.0},
            "actions_json": [{"action_type": "noop"}],
            "status": "completed",
        },
    )
    raw = delta.model_dump_json()
    back = MeditateStateDelta.model_validate(json.loads(raw))
    assert back.delta_type == "UPSERT_MEDITATE_AUDIT"
    assert back.audit_mutation().run_id == "run-1"


def test_apply_quarantine_memory(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "vault.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS main")
    con.execute(
        """
        CREATE TABLE main.semantic_memory (
            id VARCHAR PRIMARY KEY,
            embedding_status VARCHAR DEFAULT 'PENDING',
            updated_at TIMESTAMP
        )
        """
    )
    con.execute("INSERT INTO main.semantic_memory VALUES ('mem-1', 'PENDING', now())")
    con.close()

    monkeypatch.setattr(
        "loop_state_delta_handler.validate_user_db_path",
        lambda *_a, **_k: True,
    )
    payload = {
        "delta_type": "QUARANTINE_MEMORY",
        "tenant_id": "default",
        "user_id": "default",
        "target_db_path": str(db_path),
        "mutation": {"memory_ids": ["mem-1"]},
    }
    _sync_handle_loop_state_delta(json.dumps(payload))
    con2 = duckdb.connect(str(db_path))
    row = con2.execute(
        "SELECT embedding_status FROM main.semantic_memory WHERE id = 'mem-1'"
    ).fetchone()
    con2.close()
    assert row is not None
    assert row[0] == "QUARANTINE"


def test_upsert_homeostasis_manifest(tmp_path: Path, monkeypatch) -> None:
    db_path = tmp_path / "manifest.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute("CREATE SCHEMA IF NOT EXISTS harness_core")
    con.execute(
        """
        CREATE TABLE harness_core.homeostasis_targets (
            tenant_id VARCHAR PRIMARY KEY,
            targets_json JSON,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    con.close()

    monkeypatch.setattr(
        "loop_state_delta_handler.validate_user_db_path",
        lambda *_a, **_k: True,
    )
    manifest = {
        "infra": {"error_rate_pct": 2.0},
        "goals": [
            {
                "belief_key": "completion_rate_pct",
                "target_value": 95.0,
                "threshold": 2.0,
                "title": "Completion rate",
            }
        ],
    }
    payload = {
        "delta_type": "UPSERT_HOMEOSTASIS_MANIFEST",
        "tenant_id": "analytics",
        "user_id": "default",
        "target_db_path": str(db_path),
        "mutation": {"manifest": manifest},
    }
    _sync_handle_loop_state_delta(json.dumps(payload))
    con2 = duckdb.connect(str(db_path))
    row = con2.execute(
        "SELECT targets_json FROM harness_core.homeostasis_targets WHERE tenant_id = 'analytics'"
    ).fetchone()
    con2.close()
    assert row is not None
    stored = json.loads(row[0]) if isinstance(row[0], str) else row[0]
    assert stored["infra"]["error_rate_pct"] == 2.0
    assert stored["goals"][0]["belief_key"] == "completion_rate_pct"
