"""Unit tests for duckclaw.slm HTTP client (mock MLX-Inference)."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from duckclaw.slm import ExecuteSLMRequest, execute_slm_http, validate_slm_xml_output


def test_validate_slm_xml_output_ok() -> None:
    text = "<thought>plan</thought><tool_call>use_bucket</tool_call>"
    result = validate_slm_xml_output(text)
    assert result["ok"] is True
    assert result["has_thought"] is True
    assert result["has_tool_call"] is True


def test_validate_slm_xml_output_fail() -> None:
    assert validate_slm_xml_output("plain text")["ok"] is False


def test_execute_slm_http_success() -> None:
    req = ExecuteSLMRequest(prompt="test scenario", temperature=0.0, max_tokens=64)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "<thought>ok</thought>"}}],
    }
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response
    with patch("duckclaw.slm.client.httpx.Client", return_value=mock_client):
        out = execute_slm_http(req, base_url="http://127.0.0.1:8080/v1", model="gemma4")
    assert out.startswith("SLM Output:")
    assert "<thought>ok</thought>" in out


def test_execute_slm_http_reasoning_fallback() -> None:
    req = ExecuteSLMRequest(prompt="Responde OK", temperature=0.0, max_tokens=64)
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "choices": [{"message": {"content": "", "reasoning": "Thinking… OK"}}],
    }
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response
    with patch("duckclaw.slm.client.httpx.Client", return_value=mock_client):
        out = execute_slm_http(req, base_url="http://127.0.0.1:8080/v1", model="qwen35")
    assert "SLM Output:" in out
    assert "OK" in out


def test_execute_slm_http_missing_base_url() -> None:
    req = ExecuteSLMRequest(prompt="x")
    out = execute_slm_http(req, base_url="", model="gemma4")
    assert "SLM Crash" in out


def test_execute_slm_http_http_error() -> None:
    req = ExecuteSLMRequest(prompt="x")
    mock_response = MagicMock()
    mock_response.status_code = 503
    mock_response.text = "unavailable"
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_response
    with patch("duckclaw.slm.client.httpx.Client", return_value=mock_client):
        out = execute_slm_http(req, base_url="http://127.0.0.1:8080/v1", model="gemma4")
    assert "HTTP 503" in out
