from pathlib import Path


def test_session_db_path_helpers_exist() -> None:
    lib = Path("apps/duckclaw-admin/src/lib/sessionDbPath.ts").read_text(encoding="utf-8")
    assert "shortenSessionDbPath" in lib
    assert "sessionDbScopeLabel" in lib


def test_playground_shows_session_database_chip() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/playground/page.tsx").read_text(encoding="utf-8")
    chip = Path("apps/duckclaw-admin/src/components/playground/SessionDatabaseChip.tsx").read_text(
        encoding="utf-8"
    )
    assert "SessionDatabaseChip" in page
    assert 'title="Base de datos de esta sesión"' in page
    assert "sessionDbScopeLabel" in chip
    assert "BD sin resolver" in chip


def test_knowledge_page_status_badges_and_scope_layout() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/knowledge/page.tsx").read_text(encoding="utf-8")
    assert "KnowledgeSourcesGrid" in page
    assert "KnowledgeControlPanel" in page
    assert "KnowledgeScopeStatus" in page
    assert "KnowledgePlaygroundBanner" not in page
    assert "lg:grid-cols-12" in page
    card = Path("apps/duckclaw-admin/src/components/knowledge/KnowledgeSourceCard.tsx").read_text(
        encoding="utf-8"
    )
    assert "KnowledgeStatusBadge" in card
    assert "md:flex-row" not in card
    assert "Ver archivos" not in card
    status = Path("apps/duckclaw-admin/src/components/knowledge/KnowledgeScopeStatus.tsx").read_text(
        encoding="utf-8"
    )
    assert "return null" in status
    assert "auto-fill" in Path(
        "apps/duckclaw-admin/src/components/knowledge/KnowledgeSourcesGrid.tsx"
    ).read_text(encoding="utf-8")
    grid = Path("apps/duckclaw-admin/src/components/knowledge/KnowledgeSourcesGrid.tsx").read_text(
        encoding="utf-8"
    )
    assert "sourcesSummaryLabel" in grid
