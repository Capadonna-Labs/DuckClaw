"""Tests for update_system_prompt tool bridge."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from duckclaw.forge.skills.update_worker_system_prompt_bridge import (
    _update_system_prompt_impl,
    register_update_system_prompt_tools,
    update_system_prompt,
)

_WORKER_ID = "research-analyst"
_VAULT_PATH = "/tmp/research_vault.duckdb"


def test_update_system_prompt_reuses_bound_worker_db_on_same_vault_path() -> None:
    mock_bound = MagicMock()
    mock_bound._path = _VAULT_PATH
    mock_bound._read_only = False

    with patch(
        "duckclaw.forge.skills.goals_tool_context.get_goals_tool_worker_id",
        return_value=_WORKER_ID,
    ):
        with patch(
            "duckclaw.forge.skills.goals_tool_context.get_goals_tool_db_path",
            return_value=_VAULT_PATH,
        ):
            with patch(
                "duckclaw.forge.skills.knowledge_tool_context.get_session_actor_email",
                return_value="admin@test",
            ):
                with patch("duckclaw.DuckClaw") as duck_ctor:
                    with patch(
                        "duckclaw.commands.model_setup.get_effective_system_prompt",
                        return_value="base prompt",
                    ):
                        with patch(
                            "duckclaw.commands.model_setup._set_system_prompt_policy",
                            return_value=(True, ""),
                        ) as set_policy:
                            with patch(
                                "duckclaw.forge.skills.update_worker_system_prompt_bridge._maybe_sync_catalog_file",
                            ):
                                raw = _update_system_prompt_impl(
                                    mock_bound,
                                    "Regla estructural: descartar categoría completa si falla el check #3.",
                                    mode="append",
                                )

    duck_ctor.assert_not_called()
    set_policy.assert_called_once()
    assert set_policy.call_args[0][0] is mock_bound
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert payload["worker_id"] == _WORKER_ID


def test_update_system_prompt_opens_vault_duckclaw_when_no_bound_db() -> None:
    mock_db = MagicMock()
    mock_db.close = MagicMock()

    with patch(
        "duckclaw.forge.skills.goals_tool_context.get_goals_tool_worker_id",
        return_value=_WORKER_ID,
    ):
        with patch(
            "duckclaw.forge.skills.goals_tool_context.get_goals_tool_db_path",
            return_value=_VAULT_PATH,
        ):
            with patch(
                "duckclaw.forge.skills.knowledge_tool_context.get_session_actor_email",
                return_value="admin@test",
            ):
                with patch("duckclaw.DuckClaw", return_value=mock_db) as duck_ctor:
                    with patch(
                        "duckclaw.commands.model_setup.get_effective_system_prompt",
                        return_value="base prompt",
                    ):
                        with patch(
                            "duckclaw.commands.model_setup._set_system_prompt_policy",
                            return_value=(True, ""),
                        ):
                            with patch(
                                "duckclaw.forge.skills.update_worker_system_prompt_bridge._maybe_sync_catalog_file",
                            ):
                                raw = update_system_prompt(
                                    "Regla estructural: descartar categoría completa si falla el check #3.",
                                    mode="append",
                                )

    duck_ctor.assert_called_once_with(_VAULT_PATH, read_only=False, engine="python")
    mock_db.close.assert_called_once()
    payload = json.loads(raw)
    assert payload["ok"] is True


def test_update_system_prompt_uses_gateway_get_db_without_vault_path() -> None:
    mock_db = MagicMock()

    with patch(
        "duckclaw.forge.skills.goals_tool_context.get_goals_tool_worker_id",
        return_value=_WORKER_ID,
    ):
        with patch(
            "duckclaw.forge.skills.goals_tool_context.get_goals_tool_db_path",
            return_value="",
        ):
            with patch(
                "duckclaw.forge.skills.knowledge_tool_context.get_session_actor_email",
                return_value="admin@test",
            ):
                with patch("duckclaw.graphs.graph_server.get_db", return_value=mock_db) as get_db:
                    with patch(
                        "duckclaw.commands.model_setup.get_effective_system_prompt",
                        return_value="",
                    ):
                        with patch(
                            "duckclaw.commands.model_setup._set_system_prompt_policy",
                            return_value=(True, ""),
                        ):
                            with patch(
                                "duckclaw.forge.skills.update_worker_system_prompt_bridge._maybe_sync_catalog_file",
                            ):
                                raw = update_system_prompt(
                                    "Nueva regla operativa para evaluación de tareas pendientes.",
                                    mode="replace",
                                )

    get_db.assert_called_once_with()
    payload = json.loads(raw)
    assert payload["ok"] is True
    assert payload["mode"] == "replace"


def test_register_update_system_prompt_tools_exposes_canonical_and_alias() -> None:
    tools: list = []
    register_update_system_prompt_tools(tools, MagicMock())
    names = {getattr(t, "name", "") for t in tools}
    assert "update_system_prompt" in names
    assert "update_my_system_prompt" in names
    assert len(tools) == 2


def test_update_system_prompt_requires_worker_id() -> None:
    with patch(
        "duckclaw.forge.skills.goals_tool_context.get_goals_tool_worker_id",
        return_value="",
    ):
        raw = update_system_prompt("Instrucciones válidas con longitud suficiente.", mode="append")
    payload = json.loads(raw)
    assert payload["ok"] is False


def test_update_system_prompt_requires_min_length() -> None:
    with patch(
        "duckclaw.forge.skills.goals_tool_context.get_goals_tool_worker_id",
        return_value=_WORKER_ID,
    ):
        raw = update_system_prompt("corto", mode="append")
    payload = json.loads(raw)
    assert payload["ok"] is False
