"""Tests for TypeSafe Jev Decisions tool (jev_decide)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock

import pytest

from duckclaw.forge.skills.jev_decide_bridge import (
    DEFAULT_JEV_MODEL,
    jev_decide_impl,
    parse_and_validate_questions,
    register_jev_decide_skill,
)


_VALID_QUESTIONS = {
    "is_bug": {
        "type": "noul",
        "instructions": "Is this a software defect?",
        "criteria": {
            "true": "Broken or unexpected behavior",
            "false": "Question or feature request",
        },
    }
}


def test_parse_and_validate_questions_ok() -> None:
    qs, err = parse_and_validate_questions(json.dumps(_VALID_QUESTIONS))
    assert err is None
    assert qs == _VALID_QUESTIONS


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("", "questions_required"),
        ("{", "questions_json_invalid"),
        ("[]", "questions_must_be_nonempty_object"),
        ("{}", "questions_must_be_nonempty_object"),
        (
            json.dumps({"x": {"type": "maybe", "instructions": "y", "criteria": {}}}),
            "question_type_invalid:x",
        ),
        (
            json.dumps({"x": {"type": "noul", "instructions": "", "criteria": {}}}),
            "question_instructions_required:x",
        ),
        (
            json.dumps({"x": {"type": "noul", "instructions": "ok"}}),
            "question_criteria_required:x",
        ),
    ],
)
def test_parse_and_validate_questions_errors(raw: str, expected: str) -> None:
    qs, err = parse_and_validate_questions(raw)
    assert qs is None
    assert err == expected


def test_jev_decide_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    out = json.loads(
        jev_decide_impl(
            "Checkout blank",
            json.dumps(_VALID_QUESTIONS),
        )
    )
    assert out["ok"] is False
    assert "missing_api_key" in str(out.get("error") or "")


def test_jev_decide_state_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
    out = json.loads(jev_decide_impl("  ", json.dumps(_VALID_QUESTIONS)))
    assert out["ok"] is False
    assert out["error"] == "state_required"


def test_jev_decide_http_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    class _Resp:
        status = 200

        def read(self) -> bytes:
            return json.dumps(
                {
                    "id": "gen-1",
                    "model": DEFAULT_JEV_MODEL,
                    "provider": "TypeSafe",
                    "answers": {
                        "is_bug": {"noul": 0.91, "confidence": 0.9},
                    },
                    "usage": {"prompt_tokens": 12, "completion_tokens": 0},
                }
            ).encode("utf-8")

        def getcode(self) -> int:
            return 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    captured: dict = {}

    def _urlopen(req, timeout=60):  # noqa: ARG001
        captured["url"] = req.full_url
        captured["method"] = req.get_method()
        captured["headers"] = dict(req.header_items())
        body = json.loads(req.data.decode("utf-8"))
        captured["body"] = body
        return _Resp()

    out = json.loads(
        jev_decide_impl(
            "Checkout blank after Pay",
            json.dumps(_VALID_QUESTIONS),
            model="jev",
            session_id="sess-1",
            urlopen=_urlopen,
        )
    )
    assert out["ok"] is True
    assert out["model"] == DEFAULT_JEV_MODEL
    assert out["answers"]["is_bug"]["noul"] == 0.91
    assert captured["url"] == "https://openrouter.ai/api/alpha/decisions"
    assert captured["method"] == "POST"
    assert captured["body"]["model"] == DEFAULT_JEV_MODEL
    assert captured["body"]["session_id"] == "sess-1"
    assert "Authorization" in {k.title() if False else k for k in captured["headers"]} or any(
        "authorization" in k.lower() for k in captured["headers"]
    )


def test_jev_decide_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    import urllib.error

    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")

    def _urlopen(req, timeout=60):  # noqa: ARG001
        raise urllib.error.HTTPError(
            req.full_url, 400, "Bad Request", hdrs=None, fp=MagicMock(read=lambda: b'{"error":"bad"}')
        )

    out = json.loads(
        jev_decide_impl(
            "hi",
            json.dumps(_VALID_QUESTIONS),
            urlopen=_urlopen,
        )
    )
    assert out["ok"] is False
    assert out["error"] == "http_400"


def test_register_jev_decide_skill_appends_tool() -> None:
    tools: list = []
    register_jev_decide_skill(tools, {})
    assert len(tools) == 1
    assert tools[0].name == "jev_decide"


def test_register_jev_decide_skill_none_config_skips() -> None:
    tools: list = []
    register_jev_decide_skill(tools, None)
    assert tools == []


def test_register_jev_decide_skill_disabled() -> None:
    tools: list = []
    register_jev_decide_skill(tools, {"enabled": False})
    assert tools == []


def test_jev_decide_in_skill_tool_registry() -> None:
    from duckclaw.workers.skill_tool_registry import DEFAULT_SKILL_TOOL_REGISTRY

    item = next(i for i in DEFAULT_SKILL_TOOL_REGISTRY if i.skill_name == "jev_decide")
    assert item.phase == "post_llm"
    assert item.empty_config_registers is True
    assert item.registrar_path.endswith("jev_decide_bridge:register_jev_decide_skill")
