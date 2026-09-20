"""Regression: publish_custom_report must reject HTML truncated mid-document instead of
silently accepting it once _coerce_publishable_html tacks on a trailing </body></html>.
Real samples from two dashboards found stuck 'in progress' in production."""

from __future__ import annotations

from duckclaw.forge.skills.custom_reports_bridge import (
    _coerce_publishable_html,
    _validate_html_content,
)

TRUNCATED_MID_TEXT = '<html><body><table><tr><td><span class="tag long">LONG'
TRUNCATED_MID_TAG = '<html><body><div class="ms">11.5% del portfolio</div'
LEGIT_MISSING_TRAILING_TAGS_ONLY = "<html><body><h1>ok</h1></body>"
WELL_FORMED = "<html><body><h1>ok</h1></body></html>"


def _publish_flow(raw: str) -> str | None:
    coerced = _coerce_publishable_html(raw)
    return _validate_html_content(coerced)


def test_rejects_truncation_mid_text_content() -> None:
    assert _publish_flow(TRUNCATED_MID_TEXT) is not None


def test_rejects_truncation_mid_end_tag() -> None:
    assert _publish_flow(TRUNCATED_MID_TAG) is not None


def test_accepts_legit_missing_trailing_tags_only() -> None:
    assert _publish_flow(LEGIT_MISSING_TRAILING_TAGS_ONLY) is None


def test_accepts_well_formed_document() -> None:
    assert _publish_flow(WELL_FORMED) is None
