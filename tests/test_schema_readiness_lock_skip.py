from __future__ import annotations


def test_schema_readiness_skips_writer_lock(monkeypatch) -> None:
    from duckclaw.infra import readiness

    def _boom(_path: str):
        raise OSError(
            'IO Error: Could not set lock on file "hub.duckdb": Conflicting lock is held'
        )

    monkeypatch.setattr("duckclaw.schema_migrations.verify_schema_integrity", _boom)
    ok, msg = readiness.check_schema_readiness("/tmp/hub.duckdb")
    assert ok is True
    assert "lock" in msg.lower()
