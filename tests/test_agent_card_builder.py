"""Tests for A2A agent card builder."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from duckclaw.agent_card_builder import build_a2a_agent_card

_SCHEMA_PATH = Path(__file__).resolve().parent / "fixtures" / "a2a_agent_card_schema.json"


@pytest.fixture
def agent_card_schema() -> dict:
    return json.loads(_SCHEMA_PATH.read_text(encoding="utf-8"))


def test_build_a2a_agent_card_required_fields() -> None:
    manifest = {
        "id": "demo-worker",
        "display_name": "Demo Worker",
        "description": "Example worker",
        "version": "2.1.0",
        "skills": ["research"],
        "topology": "general",
    }
    files = {"soul.md": "Demo agent for documentation.\n\nMore detail hidden."}
    card = build_a2a_agent_card(
        "demo-worker",
        manifest=manifest,
        files=files,
        public_base_url="https://example.test",
        gateway_a2a_url="https://example.test/api/v1/agent/chat",
    )
    assert card["name"] == "demo-worker"
    assert card["version"] == "2.1.0"
    assert card["supportedInterfaces"][0]["protocolVersion"] == "1.0"
    assert card["skills"][0]["tags"]
    assert "system_prompt.md" not in str(card.get("description") or "").lower()


def test_build_a2a_agent_card_allows_update_system_prompt_skill() -> None:
    """Regression: skill id ``update_system_prompt`` must not trip prompt-leak scan."""
    manifest = {
        "id": "finanz-1",
        "skills": ["research", "admin_sql", "update_system_prompt"],
    }
    files = {"soul.md": "Assistant for personal finance."}
    card = build_a2a_agent_card("finanz-1", manifest=manifest, files=files)
    skill_ids = {s["id"] for s in card["skills"]}
    assert "update_system_prompt" in skill_ids


def test_agent_card_rejects_prompt_markers_in_description() -> None:
    manifest = {"id": "w", "skills": [], "description": "See system_prompt.md for rules"}
    files = {"soul.md": ""}
    with pytest.raises(ValueError, match="prompt file"):
        build_a2a_agent_card("w", manifest=manifest, files=files)


def test_agent_card_validates_against_schema(agent_card_schema: dict) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    manifest = {"id": "demo", "skills": [], "tool_profile": "general"}
    files = {"soul.md": "Demo worker soul."}
    card = build_a2a_agent_card("demo", manifest=manifest, files=files)
    jsonschema.validate(instance=card, schema=agent_card_schema)
