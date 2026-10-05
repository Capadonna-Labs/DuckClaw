"""Estado del Mac para el correo de Resend. No envía nada."""

from __future__ import annotations

from duckops.host_status_mail import HostSample, parse_memory_pressure, render_mail

_PRESSURE = (
    "The system has 17179869184 (1048576 pages with a page size of 16384).\n"
    "System-wide memory free percentage: 81%\n"
)


def _sample(**overrides: object) -> HostSample:
    base = dict(
        memory_free_pct=81,
        memory_total_gb=16.0,
        disk_used_pct=40,
        processes=(
            ("DuckClaw-Gateway", "online"),
            ("DuckClaw-DB-Writer", "online"),
            ("DuckClaw-Knowledge-Indexer", "online"),
            ("DuckClaw-Heartbeat", "online"),
            ("duckclaw-admin-ui", "online"),
        ),
        redis_open=True,
        tailscale="Running",
        gateway_health=True,
        admin_up=True,
    )
    base.update(overrides)
    return HostSample(**base)  # type: ignore[arg-type]


def test_parse_memory_pressure_reads_free_percent_and_total() -> None:
    free_pct, total_gb = parse_memory_pressure(_PRESSURE)
    assert free_pct == 81
    assert total_gb == 16.0


def test_healthy_sample_is_not_scarce() -> None:
    subject, body = render_mail(_sample())
    assert subject == "DuckClaw Mac mini ok"
    assert "Memoria libre: 81% de 16.0 GB" in body
    assert "DuckClaw-Gateway: online" in body
    assert "re_" not in body


def test_low_memory_or_dead_process_is_scarce() -> None:
    assert _sample(memory_free_pct=10).scarce
    assert _sample(disk_used_pct=90).scarce
    processes = (
        ("DuckClaw-Gateway", "missing"),
        ("DuckClaw-DB-Writer", "online"),
        ("DuckClaw-Knowledge-Indexer", "online"),
        ("DuckClaw-Heartbeat", "online"),
        ("duckclaw-admin-ui", "online"),
    )
    assert _sample(processes=processes).scarce
    assert not _sample().scarce
