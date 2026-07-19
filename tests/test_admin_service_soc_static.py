"""Contrato estático: facade delgado + módulos de dominio en services/admin."""

from __future__ import annotations

from pathlib import Path

from admin_service_corpus import admin_service_corpus

_SERVICES = Path("apps/duckclaw-admin/src/services")
_ADMIN = _SERVICES / "admin"


def test_admin_service_facade_is_thin_spread_of_domain_modules() -> None:
    facade = (_SERVICES / "adminService.ts").read_text(encoding="utf-8")
    modules = sorted(p.name for p in _ADMIN.glob("*Api.ts"))

    assert len(facade.splitlines()) < 200
    assert "adminFetch<" not in facade
    for name in modules:
        export = name.replace(".ts", "")
        assert f"...{export}" in facade, f"missing spread {export}"
        assert f"from './admin/{export}'" in facade or f'from "./admin/{export}"' in facade


def test_admin_service_corpus_exposes_hot_path_methods() -> None:
    corpus = admin_service_corpus()
    for needle in (
        "playgroundChatStream:",
        "getTrainStatus:",
        "getSandboxChatPolicy:",
        "listKnowledgeSources:",
        "listProductivityArtifacts:",
        "listTemplates:",
        "listMcpConnectors:",
        "getDuckdbTables:",
        "listPromptPolicies:",
        "listWorkspaceProjectsPage,",
    ):
        assert needle in corpus, needle


def test_admin_chat_pure_helpers_live_outside_hook() -> None:
    pure = Path("apps/duckclaw-admin/src/components/chat/adminChatPure.ts").read_text(encoding="utf-8")
    hook = Path("apps/duckclaw-admin/src/components/chat/useAdminChat.ts").read_text(encoding="utf-8")
    assert "export function hasToolHeartbeatInCurrentTurn" in pure
    assert "export function conversationIndicatesLoopScheduling" in pure
    assert "from './adminChatPure'" in hook
    assert "export function hasToolHeartbeatInCurrentTurn" not in hook


def test_admin_chat_turn_lives_outside_hook() -> None:
    turn = Path("apps/duckclaw-admin/src/components/chat/runAdminChatTurn.ts").read_text(encoding="utf-8")
    hook = Path("apps/duckclaw-admin/src/components/chat/useAdminChat.ts").read_text(encoding="utf-8")
    assert "export async function runAdminChatTurn" in turn
    assert "playgroundChatStream" in turn
    assert "from './runAdminChatTurn'" in hook
    assert "playgroundChatStream" not in hook
    assert len(hook.splitlines()) < 800


def test_admin_chat_history_lives_outside_hook() -> None:
    history = Path("apps/duckclaw-admin/src/components/chat/useAdminChatHistory.ts").read_text(
        encoding="utf-8"
    )
    hook = Path("apps/duckclaw-admin/src/components/chat/useAdminChat.ts").read_text(encoding="utf-8")
    assert "export function useAdminChatHistory" in history
    assert "reloadHistory" in history
    assert "scheduleLoopHistoryReload" in history
    assert "from './useAdminChatHistory'" in hook
    assert "writeEphemeralHeartbeats" not in hook
    assert "setWorkerId: (next) => setWorkerId(next)" not in hook
    assert "configRef.current" in history
    assert "setWorkerIdRef.current" in history
    assert "loadedKeyRef" in history
    assert len(hook.splitlines()) < 600


def test_admin_chat_panel_delegates_list_and_compose() -> None:
    panel = Path("apps/duckclaw-admin/src/components/chat/AdminChatPanel.tsx").read_text(
        encoding="utf-8"
    )
    assert "AdminChatMessageList" in panel
    assert "AdminChatComposeFooter" in panel
    assert "function AdminChatMessageList" not in panel
    assert "function AdminChatComposeFooter" not in panel
    assert "<ChatBubble" not in panel
    assert "<MediaAttachMenu" not in panel
    assert len(panel.splitlines()) < 600


def test_playground_page_delegates_history_and_settings() -> None:
    page = Path("apps/duckclaw-admin/src/app/(admin)/playground/page.tsx").read_text(encoding="utf-8")
    assert "PlaygroundHistoryView" in page
    assert "from '@/components/playground/PlaygroundHistoryView'" in page
    assert "from '@/components/playground/PlaygroundSettingsParts'" in page
    assert "function PlaygroundHistoryView" not in page
    assert "function SettingsModal" not in page
    assert len(page.splitlines()) < 900
