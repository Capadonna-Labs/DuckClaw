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
    assert "Base de datos de esta sesión" in chip


def test_knowledge_page_status_badges_and_playground_banner() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/knowledge/page.tsx").read_text(encoding="utf-8")
    assert "KnowledgeStatusBadge" in page
    assert "KnowledgePlaygroundBanner" in page
    banner = Path(
        "apps/duckclaw-admin/src/components/knowledge/KnowledgePlaygroundBanner.tsx"
    ).read_text(encoding="utf-8")
    assert "Listo para el chat" in banner
    assert "Playground" in banner
