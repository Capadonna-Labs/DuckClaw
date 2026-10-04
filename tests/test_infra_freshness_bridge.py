"""infra_freshness_bridge: cron between-fires + key-filtered freshness."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone


class _FakeDb:
    def __init__(self, rows):
        self._rows = rows
        self.last_sql = ""

    def query(self, sql: str):
        self.last_sql = sql
        return self._rows


def test_assess_table_freshness_filters_keys():
    from duckclaw.forge.skills.infra_freshness_bridge import register_infra_freshness_skill

    now = datetime.now(timezone.utc)
    db = _FakeDb([{"latest": (now - timedelta(hours=10)).isoformat()}])
    tools: list = []
    register_infra_freshness_skill(tools, db)
    by_name = {t.name: t for t in tools}
    out = json.loads(
        by_name["assess_table_freshness"].invoke(
            {
                "table": "main.readings",
                "timestamp_column": "timestamp",
                "max_age_hours": 48,
                "keys": "sensor_a,SENSOR_B",
                "key_column": "sensor",
            }
        )
    )
    assert out["within_threshold"] is True
    assert out["keys_filter"] == ["SENSOR_A", "SENSOR_B"]
    assert "IN (" in db.last_sql.upper()
    assert "SENSOR_A" in db.last_sql.upper()


def test_assess_cron_marks_stopped_with_cron_as_ok(monkeypatch):
    from duckclaw.forge.skills import infra_freshness_bridge as bridge

    class Proc:
        returncode = 0
        stdout = json.dumps(
            [
                {
                    "name": "ext-weekly-job",
                    "pm2_env": {"status": "stopped", "cron_restart": "0 20 * * 5"},
                }
            ]
        )
        stderr = ""

    monkeypatch.setattr(
        "duckclaw.ops.toolchain.run_pm2",
        lambda *a, **k: Proc(),
    )
    monkeypatch.setattr(
        "subprocess.check_output",
        lambda *a, **k: (_ for _ in ()).throw(FileNotFoundError("no crontab")),
    )
    tools: list = []
    bridge.register_infra_freshness_skill(tools, _FakeDb([]))
    by_name = {t.name: t for t in tools}
    out = json.loads(by_name["assess_cron_registered"].invoke({"pm2_name": "ext-weekly-job"}))
    assert out["found"] is True
    assert out["has_cron"] is True
    assert out["between_fires_ok"] is True
    assert out.get("source") == "pm2"


def test_assess_cron_falls_back_to_crontab_when_pm2_missing(monkeypatch):
    from duckclaw.forge.skills import infra_freshness_bridge as bridge

    class Proc:
        returncode = 0
        stdout = "[]"
        stderr = ""

    monkeypatch.setattr(
        "duckclaw.ops.toolchain.run_pm2",
        lambda *a, **k: Proc(),
    )
    cron_blob = (
        "0 20 * * 5 /venv/bin/python /app/scripts/ext/weekly_job.py "
        ">> /var/log/ext-weekly-job.log 2>&1\n"
    )
    monkeypatch.setattr(
        "subprocess.check_output",
        lambda *a, **k: cron_blob,
    )
    tools: list = []
    bridge.register_infra_freshness_skill(tools, _FakeDb([]))
    by_name = {t.name: t for t in tools}
    out = json.loads(
        by_name["assess_cron_registered"].invoke(
            {"pm2_name": "ext-weekly-job", "crontab_pattern": "weekly_job"}
        )
    )
    assert out["found"] is True
    assert out["has_cron"] is True
    assert out["source"] == "crontab"
    assert out["between_fires_ok"] is True
    assert any("weekly_job" in line for line in out["crontab_lines"])


def test_assess_cron_pm2_name_matches_crontab_log_path(monkeypatch):
    """Even without crontab_pattern, pm2_name can match crontab log path tokens."""
    from duckclaw.forge.skills import infra_freshness_bridge as bridge

    class Proc:
        returncode = 0
        stdout = "[]"
        stderr = ""

    monkeypatch.setattr(
        "duckclaw.ops.toolchain.run_pm2",
        lambda *a, **k: Proc(),
    )
    monkeypatch.setattr(
        "subprocess.check_output",
        lambda *a, **k: (
            "0 20 * * 5 python weekly_job.py >> /var/log/ext-weekly-job.log\n"
        ),
    )
    tools: list = []
    bridge.register_infra_freshness_skill(tools, _FakeDb([]))
    by_name = {t.name: t for t in tools}
    out = json.loads(
        by_name["assess_cron_registered"].invoke({"pm2_name": "ext-weekly-job"})
    )
    assert out["found"] is True
    assert out["source"] == "crontab"
