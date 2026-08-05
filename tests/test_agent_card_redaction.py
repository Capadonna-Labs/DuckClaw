"""Agent card must not leak prompts or secrets."""

from __future__ import annotations

import json

from duckclaw.agent_card_builder import build_a2a_agent_card


def test_agent_card_description_from_soul_not_system_prompt() -> None:
    manifest = {"id": "w", "skills": []}
    files = {
        "soul.md": "Public soul excerpt only.",
        "system_prompt.md": "SECRET: execute_broker_signals_batch admin_sql",
    }
    card = build_a2a_agent_card("w", manifest=manifest, files=files)
    blob = json.dumps(card).lower()
    assert "execute_broker" not in blob
    assert "admin_sql" not in blob
    assert "Public soul" in card["description"]
