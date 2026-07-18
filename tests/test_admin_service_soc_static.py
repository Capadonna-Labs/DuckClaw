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
