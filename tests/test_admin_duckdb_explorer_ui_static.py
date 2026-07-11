from __future__ import annotations

from pathlib import Path


def test_table_explorer_exposes_pagination_and_csv() -> None:
    page = Path("apps/duckclaw-admin/src/components/duckdb/TableExplorer.tsx").read_text(encoding="utf-8")
    csv_lib = Path("apps/duckclaw-admin/src/lib/duckdbCsvExport.ts").read_text(encoding="utf-8")

    assert "downloadDuckdbCsv" in page
    assert "limit:" in page
    assert "offset:" in page
    assert "hasMore" in page
    assert "PAGE_SIZE_OPTIONS" in page
    assert "buildDuckdbCsv" in csv_lib
