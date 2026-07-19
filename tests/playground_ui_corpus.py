"""Corpus UI playground + helpers puros del chat admin."""

from __future__ import annotations

from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_ADMIN = _ROOT / "apps/duckclaw-admin/src"


def playground_ui_corpus() -> str:
    paths = [
        _ADMIN / "app/(admin)/playground/page.tsx",
        _ADMIN / "components/playground/PlaygroundHistoryView.tsx",
        _ADMIN / "components/playground/PlaygroundSettingsParts.tsx",
        _ADMIN / "components/playground/playgroundHistoryHelpers.ts",
        _ADMIN / "components/playground/playgroundTypes.ts",
        _ADMIN / "components/playground/PlaygroundRunSettingsPanel.tsx",
        _ADMIN / "components/playground/SessionDatabaseChip.tsx",
        _ADMIN / "components/playground/PlaygroundRagProjectWarning.tsx",
    ]
    return "\n".join(p.read_text(encoding="utf-8") for p in paths if p.exists())


def admin_chat_corpus() -> str:
    paths = [
        _ADMIN / "components/chat/useAdminChat.ts",
        _ADMIN / "components/chat/adminChatPure.ts",
        _ADMIN / "components/chat/runAdminChatTurn.ts",
        _ADMIN / "components/chat/useAdminChatHistory.ts",
        _ADMIN / "components/chat/AdminChatPanel.tsx",
        _ADMIN / "components/chat/AdminChatMessageList.tsx",
        _ADMIN / "components/chat/AdminChatComposeFooter.tsx",
    ]
    return "\n".join(p.read_text(encoding="utf-8") for p in paths if p.exists())
