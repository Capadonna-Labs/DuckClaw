"""open_gateway_db respects spawn inline (no RO hub connections)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

_REPO = Path(__file__).resolve().parents[1]
_GATEWAY = _REPO / "services" / "api-gateway"
if str(_GATEWAY) not in sys.path:
    sys.path.insert(0, str(_GATEWAY))


def test_open_gateway_db_uses_rw_when_spawn_inline(tmp_path, monkeypatch) -> None:
    db_path = tmp_path / "hub.duckdb"
    db_path.write_bytes(b"")

    monkeypatch.setenv("DUCKCLAW_GATEWAY_DB_PATH", str(db_path))
    monkeypatch.setenv("DUCKCLAW_SPAWN_PROFILE", "1")

    from core.admin_identity import open_gateway_db

    seen: list[bool] = []

    class FakeDuckClaw:
        def __init__(self, path: str, *, read_only: bool, engine: str) -> None:
            seen.append(read_only)

        def close(self) -> None:
            pass

    with patch("core.admin_identity.DuckClaw", FakeDuckClaw):
        with patch("core.admin_identity.get_gateway_db_path", return_value=str(db_path)):
            with open_gateway_db(read_only=True) as _db:
                pass

    assert seen == [False]
