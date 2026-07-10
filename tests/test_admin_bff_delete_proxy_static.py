"""BFF admin proxy must not re-read an empty DELETE body (Next.js Request stream)."""

from __future__ import annotations

from pathlib import Path


def test_admin_bff_proxy_reads_body_once_and_omits_empty_delete_body() -> None:
    route = (
        Path(__file__).resolve().parents[1]
        / "apps/duckclaw-admin/src/app/api/admin/[...path]/route.ts"
    )
    text = route.read_text(encoding="utf-8")
    assert "bodyRead" in text
    assert "await req.text()" in text
    assert text.count("await req.text()") == 1, "proxy must read req.text() at most once"
    assert "bodyRead && bodyText.length > 0" in text
