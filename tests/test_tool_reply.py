"""Tests for duckclaw.utils.format_tool_reply."""

import json

from duckclaw.utils import format_tool_reply
from duckclaw.utils.tool_reply import looks_like_finanz_local_cuentas_json


def test_format_tool_reply_json_pretty() -> None:
    out = format_tool_reply('{"a": 1}')
    assert '"a"' in out
    assert "1" in out
    assert "\n" in out


def test_format_tool_reply_plain_and_empty() -> None:
    assert format_tool_reply("hola") == "hola"
    assert format_tool_reply("") == "Listo."
    assert format_tool_reply(None) == "Listo."


def test_looks_like_finanz_local_cuentas_json() -> None:
    rows = [
        {
            "id": "1",
            "name": "Bancolombia",
            "balance": "100",
            "currency": "COP",
            "updated_at": "2026-01-01",
        }
    ]
    assert looks_like_finanz_local_cuentas_json(json.dumps(rows))
    assert not looks_like_finanz_local_cuentas_json('{"a": 1}')


