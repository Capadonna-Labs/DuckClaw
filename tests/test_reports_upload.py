"""Static contract: admin HTML upload uses publish_custom_report path."""

from __future__ import annotations

from pathlib import Path


def test_upload_route_delegates_to_publish_custom_report() -> None:
    text = Path("services/api-gateway/routers/reports.py").read_text(encoding="utf-8")
    assert '"/reports/{report_id}/upload"' in text
    assert "_publish_custom_report_impl" in text
    assert "admin-ui-upload" in text


def test_placeholder_mentions_manual_upload() -> None:
    text = Path("services/api-gateway/routers/reports.py").read_text(encoding="utf-8")
    assert "PLACEHOLDER_MARKER" in text
    assert ".html" in text
