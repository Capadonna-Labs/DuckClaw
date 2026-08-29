"""Playground zero-trust: default scaffold no bypasses catalog or sensitive packs."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from duckclaw.workers.tool_pack_policy import (
    apply_runtime_tool_packs,
    is_pack_restricted_for_worker,
)


def _default_spec() -> SimpleNamespace:
    return SimpleNamespace(worker_id="default", logical_worker_id="default_agent")


def test_default_worker_cannot_unlock_docs_output_pack() -> None:
    from duckclaw.forge.skills.tool_pack_bridge import register_tool_pack_meta_tools

    tools: list = []
    register_tool_pack_meta_tools(tools, spec=_default_spec())
    unlock = next(t for t in tools if getattr(t, "name", "") == "unlock_tool_pack")
    out = json.loads(unlock.invoke({"pack_id": "docs_output"}))
    assert out.get("ok") is False
    assert "docs_output" in str(out.get("error") or "")


def test_default_worker_filters_docs_output_tools_from_runtime_packs() -> None:
    from langchain_core.tools import StructuredTool

    def _write_output_document(**_: object) -> str:
        return "nope"

    tools = [
        StructuredTool.from_function(
            _write_output_document,
            name="write_output_document",
            description="write",
        ),
        StructuredTool.from_function(lambda: "ok", name="read_sql", description="read"),
    ]
    result = apply_runtime_tool_packs(
        tools,
        spec=_default_spec(),
        intent_text="publicar custom_report en output",
        messages=[],
    )
    names = {getattr(t, "name", "") for t in result.tools}
    assert "write_output_document" not in names
    assert "read_sql" in names


def test_is_pack_restricted_only_for_default_worker() -> None:
    assert is_pack_restricted_for_worker("docs_output", "default") is True
    assert is_pack_restricted_for_worker("docs_output", "quant-trader") is False
    assert is_pack_restricted_for_worker("core", "default") is False


def test_playground_chat_rejects_default_without_catalog(
    gateway_admin_client: TestClient,
) -> None:
    r = gateway_admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={
            "X-Admin-Key": "test-admin-key",
            "X-Duckclaw-Actor": "admin@test.local",
        },
        json={"worker_id": "default", "message": "ping"},
    )
    assert r.status_code == 403


def test_playground_chat_allows_catalog_worker(
    gateway_admin_client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from duckclaw import DuckClaw
    from duckclaw.admin_worker_catalog import create_worker
    from duckclaw.gateway_db import get_gateway_db_path

    db = DuckClaw(get_gateway_db_path(), read_only=False, engine="python")
    try:
        create_worker(
            db,
            owner_email="admin@test.local",
            worker_id="dev-coder",
            display_name="Dev Coder",
        )
    finally:
        db.close()

    gw_dir = Path(__file__).resolve().parent.parent / "services" / "api-gateway"
    import sys

    if str(gw_dir) not in sys.path:
        sys.path.insert(0, str(gw_dir))
    import routers.admin_domains.playground.chat_turn as playground_chat_turn

    async def _fake_invoke(*_args, **_kwargs):
        return {"response": "ok", "usage_tokens": {"total": 1}}

    monkeypatch.setattr(playground_chat_turn, "invoke_chat", _fake_invoke)

    r = gateway_admin_client.post(
        "/api/v1/admin/playground/chat",
        headers={
            "X-Admin-Key": "test-admin-key",
            "X-Duckclaw-Actor": "admin@test.local",
        },
        json={"worker_id": "dev-coder", "message": "ping"},
    )
    assert r.status_code == 200
    assert r.json().get("worker_id") == "dev-coder"
