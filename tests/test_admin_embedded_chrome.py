"""The console hides its side menu when it runs inside an iframe (the dashboard's chat panel)."""

from __future__ import annotations

from pathlib import Path

_SRC = Path(__file__).resolve().parent.parent / "apps" / "duckclaw-admin" / "src"


def test_embedded_console_has_no_side_menu_or_menu_button() -> None:
    hook = (_SRC / "lib" / "useEmbedded.ts").read_text(encoding="utf-8")
    assert "window.self !== window.top" in hook and "catch" in hook          # a cross-origin parent counts as embedded
    layout = (_SRC / "app" / "(admin)" / "layout.tsx").read_text(encoding="utf-8")
    assert "const embedded = useEmbedded();" in layout
    assert "{!embedded && (" in layout                                        # desktop sidebar
    assert "{!embedded && isSidebarOpen && (" in layout                       # mobile overlay (the one that showed in the chat panel)
    assert "hideMenu={embedded}" in layout
    assert layout.index("{!embedded && (") < layout.index("<Sidebar />")      # the sidebar sits inside the guard
    top = (_SRC / "components" / "layout" / "Topbar.tsx").read_text(encoding="utf-8")
    assert "hideMenu = false" in top and "{!hideMenu && (" in top             # no hamburger to reopen it
    assert "hideMenu ? 'justify-end' : 'justify-between'" in top              # the right-hand controls stay on the right
