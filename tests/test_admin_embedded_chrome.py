"""The console shows only the chat when it runs inside an iframe (the dashboard's narrow chat panel)."""

from __future__ import annotations

from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "apps" / "duckclaw-admin" / "src"


def _read(*parts: str) -> str:
    return _SRC.joinpath(*parts).read_text(encoding="utf-8").replace("\r\n", "\n")


def test_embedded_console_has_no_side_menu_topbar_or_padding() -> None:
    hook = _read("lib", "useEmbedded.ts")
    assert "window.self !== window.top" in hook and "catch" in hook          # a cross-origin parent counts as embedded
    layout = _read("app", "(admin)", "layout.tsx")
    assert "const embedded = useEmbedded();" in layout
    assert "{!embedded && (" in layout and layout.index("{!embedded && (") < layout.index("<Sidebar />")   # desktop sidebar inside the guard
    assert "{!embedded && isSidebarOpen && (" in layout                       # mobile overlay (the one that showed in the chat panel)
    assert "{!embedded && <Topbar" in layout                                  # status, refresh, theme and avatar are not needed in a chat panel
    assert "embedded\n              ? 'overflow-hidden overscroll-none p-0'" in layout   # no outer padding: every pixel goes to the chat
    top = _read("components", "layout", "Topbar.tsx")
    assert "hideMenu" not in top                                              # the topbar is simply not rendered when embedded


def test_embedded_chat_drops_the_studio_header_and_the_suggestions_strip() -> None:
    page = _read("app", "(admin)", "playground", "page.tsx")
    assert "const embedded = useEmbedded();" in page and "showStudioHeader={!embedded}" in page    # title, tokens and the back/folder/terminal/settings buttons
    panel = _read("components", "chat", "AdminChatPanel.tsx")
    assert "const showSuggestions = !embedded && shouldShowSuggestionChips(" in panel
    assert "suggestions={embedded ? [] : suggestions}" in panel               # no "Sugerencias" bar above the composer
