from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from duckclaw.forge.skills.openweather_bridge import register_openweather_skill


def test_openweather_tool_returns_config_error_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENWEATHER_API_KEY", raising=False)
    tools: list = []
    register_openweather_skill(
        tools,
        {"enabled": True, "default_units": "metric", "default_lang": "es"},
        {"tavily_enabled": False},
    )
    assert len(tools) == 1
    out = tools[0].invoke({"city": "Medellin"})
    payload = json.loads(out)
    assert payload["ok"] is False
    assert "missing_api_key" in str(payload.get("error") or "")


@patch("urllib.request.urlopen")
def test_openweather_tool_parses_current_weather(mock_urlopen: MagicMock, monkeypatch) -> None:
    monkeypatch.setenv("OPENWEATHER_API_KEY", "test-key")
    fake_resp = MagicMock()
    fake_resp.read.return_value = json.dumps(
        {
            "name": "Medellin",
            "sys": {"country": "CO"},
            "dt": 1712500000,
            "weather": [{"main": "Clouds", "description": "nubes", "icon": "03d"}],
            "main": {"temp": 18.05, "feels_like": 18.34, "humidity": 93, "pressure": 1012},
            "wind": {"speed": 1.14, "deg": 120},
            "rain": {"1h": 0.2},
        }
    ).encode("utf-8")
    mock_urlopen.return_value.__enter__.return_value = fake_resp

    tools: list = []
    register_openweather_skill(
        tools,
        {
            "enabled": True,
            "default_units": "metric",
            "default_lang": "es",
            "include_tavily_context": False,
        },
        {"tavily_enabled": False},
    )
    assert len(tools) == 1
    out = tools[0].invoke({"city": "Medellin", "country": "CO"})
    payload = json.loads(out)
    assert payload["ok"] is True
    data = payload["data"]
    assert data["location"]["city"] == "Medellin"
    assert data["location"]["country"] == "CO"
    assert data["metrics"]["temp"] == 18.05
    assert data["weather"]["description"] == "nubes"
