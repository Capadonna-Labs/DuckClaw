"""Back-to-back protective orders: the TP/SL read waits out DB-Writer's lock.

Trailing 4 tickers in one turn failed from the 2nd order on: DB-Writer was still
saving the previous order's rows and a single read-only connect gave up at once.
"""

from __future__ import annotations

import duckdb


def test_tp_sl_read_retries_while_vault_is_locked(tmp_path, monkeypatch) -> None:
    import duckclaw.db_bridge as bridge
    from duckclaw.signal_execution_bridge import _read_active_tp_sl

    vault = str(tmp_path / "vault.duckdb")
    con = duckdb.connect(vault)
    con.execute("CREATE SCHEMA quant_core")
    con.execute(
        "CREATE TABLE quant_core.tp_sl_levels (ticker TEXT, take_profit DOUBLE, stop_loss DOUBLE, "
        "status TEXT, created_at TIMESTAMP DEFAULT now())"
    )
    con.execute("INSERT INTO quant_core.tp_sl_levels (ticker, take_profit, stop_loss, status) VALUES ('MU', 1200, 989.71, 'ACTIVE')")
    con.close()

    real_connect = duckdb.connect
    calls = {"n": 0}

    def flaky_connect(path, *a, **k):
        calls["n"] += 1
        if calls["n"] <= 2:  # DB-Writer still holds the file for the previous order
            raise duckdb.IOException('Could not set lock on file "vault.duckdb": Conflicting lock is held')
        return real_connect(path, *a, **k)

    monkeypatch.setattr(bridge._duckdb, "connect", flaky_connect)
    monkeypatch.setenv("DUCKCLAW_GATEWAY_RO_LOCK_BASE_SLEEP_S", "0.05")

    tp, sl, err = _read_active_tp_sl(vault, "MU")
    assert err is None and (tp, sl) == (1200.0, 989.71)
    assert calls["n"] == 3
