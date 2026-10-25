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


def test_embedded_chat_keeps_a_compact_header_with_a_close_button() -> None:
    page = _read("app", "(admin)", "playground", "page.tsx")
    assert "const embedded = useEmbedded();" in page
    assert "denseCompose={embedded}" in page                                  # shorter composer in the narrow framed chat
    assert "embedded ? undefined : (" in page                                 # no "back to history" button when framed
    assert "requestEmbedChatClose()" in page and 'aria-label="Cerrar chat"' in page   # the header's x asks the framing page to hide the chat
    assert "if (embedded) setPanelOpen(false);" in page                       # starts on the conversation, settings closed
    helper = _read("lib", "embedChat.ts")
    assert "export function requestEmbedChatClose" in helper and "export function shouldEscCloseEmbedChat" in helper
