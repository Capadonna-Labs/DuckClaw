from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from langchain_core.messages import ToolMessage

REPO_ROOT = Path(__file__).resolve().parents[1]
API_GATEWAY_DIR = REPO_ROOT / "services" / "api-gateway"
if str(API_GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(API_GATEWAY_DIR))

from core import vlm_ingest as vlm_mod
from routers import telegram_inbound_webhook as _tg_wh
from routers.telegram_inbound_webhook import (
    _extract_visual_payload,
    _extract_visual_payload_with_reply,
    _wr_vlm_collect_album_items,
)
from duckclaw.forge.atoms.quant_price_validator import enforce_visual_evidence_rule


class _FakeRedisLists:
    """Mínimo async para album coordination + lpush state delta."""

    def __init__(self) -> None:
        self.lists: dict[str, list[str]] = {}
        self._kv: dict[str, str] = {}
        self._expiry: dict[str, float] = {}
        self.lpush_calls: list[tuple[str, str]] = []

    def _purge(self, key: str) -> None:
        exp = self._expiry.get(key)
        if exp is not None and exp <= time.monotonic():
            self._kv.pop(key, None)
            self._expiry.pop(key, None)

    async def rpush(self, key: str, value: str) -> int:
        self.lists.setdefault(key, []).append(value)
        return len(self.lists[key])

    async def llen(self, key: str) -> int:
        return len(self.lists.get(key, []))

    async def lrange(self, key: str, start: int, end: int) -> list[str]:
        items = self.lists.get(key, [])
        if end == -1:
            return items[start:]
        return items[start : end + 1]

    async def delete(self, key: str) -> int:
        n = 0
        if key in self.lists:
            del self.lists[key]
            n += 1
        if key in self._kv:
            del self._kv[key]
            self._expiry.pop(key, None)
            n += 1
        return n

    async def expire(self, key: str, seconds: int) -> bool:
        return True

    async def set(self, key: str, value: str, ex: int | None = None, nx: bool = False) -> bool:
        self._purge(key)
        if nx and key in self._kv:
            return False
        self._kv[key] = value
        if ex is not None:
            self._expiry[key] = time.monotonic() + int(ex)
        return True

    async def lpush(self, key: str, value: str) -> int:
        self.lpush_calls.append((key, value))
        return 1


def test_extract_visual_payload_photo_prefers_largest() -> None:
    msg = {
        "photo": [
            {"file_id": "small"},
            {"file_id": "large"},
        ],
        "media_group_id": "grp-1",
    }
    duo, from_reply = _extract_visual_payload_with_reply(msg)
    assert from_reply is False
    out = _extract_visual_payload(msg)
    assert duo["file_id"] == out["file_id"]
    assert out["file_id"] == "large"
    assert out["mime_type"] == "image/jpeg"
    assert out["media_group_id"] == "grp-1"


def test_extract_visual_payload_inherits_photo_from_reply_to_message() -> None:
    msg = {
        "text": "@finanz01_bot analiza",
        "reply_to_message": {
            "message_id": 99,
            "photo": [{"file_id": "s"}, {"file_id": "hq"}],
            "media_group_id": "mg-1",
        },
    }
    out, from_reply = _extract_visual_payload_with_reply(msg)
    assert from_reply is True
    assert out["file_id"] == "hq"
    assert out["mime_type"] == "image/jpeg"
    assert out["media_group_id"] == "mg-1"


def test_extract_visual_payload_document_uses_mime() -> None:
    msg = {"document": {"file_id": "doc-file", "mime_type": "image/png"}}
    out = _extract_visual_payload(msg)
    assert out["file_id"] == "doc-file"
    assert out["mime_type"] == "image/png"


def test_visual_evidence_rule_blocks_prices_without_tool_evidence() -> None:
    reply, reason = enforce_visual_evidence_rule(
        incoming="Usuario dice: x\n[VLM_CONTEXT image_hash=abc confidence=0.8]",
        messages=[],
        reply="VIX está en 24.55 y bajando",
    )
    assert "Regla de Evidencia Única" in reply
    assert reason == "missing_tool_evidence_for_vlm_claim"


def test_visual_evidence_rule_allows_when_tool_evidence_exists() -> None:
    tool_msg = ToolMessage(content='{"status":"ok"}', tool_call_id="1", name="fetch_market_data")
    reply, reason = enforce_visual_evidence_rule(
        incoming="Usuario dice: x\n[VLM_CONTEXT image_hash=abc confidence=0.8]",
        messages=[tool_msg],
        reply="VIX está en 24.55 y bajando",
    )
    assert reply == "VIX está en 24.55 y bajando"
    assert reason is None


def test_visual_evidence_rule_relaxed_when_no_tracked_ticker_in_reply() -> None:
    class _FakeDB:
        def query(self, _q: str) -> str:
            return '[{"t": "AAPL"}]'

    class _FakeSpec:
        worker_id = "finanz"
        logical_worker_id = "finanz"
        quant_config = {"enabled": True}

    reply, reason = enforce_visual_evidence_rule(
        incoming="Usuario dice: x\n[VLM_CONTEXT image_hash=abc confidence=0.8]",
        messages=[],
        reply="SpaceX podría recaudar 75.00 billones; valoración 1.75 billones (noticia).",
        db=_FakeDB(),
        spec=_FakeSpec(),
    )
    assert reason is None
    assert "SpaceX" in reply


def test_visual_evidence_rule_blocks_known_ticker_price_without_tools() -> None:
    class _FakeDB:
        def query(self, _q: str) -> str:
            return '[{"t": "AAPL"}]'

    class _FakeSpec:
        worker_id = "finanz"
        logical_worker_id = "finanz"
        quant_config = {"enabled": True}

    reply, reason = enforce_visual_evidence_rule(
        incoming="Usuario dice: x\n[VLM_CONTEXT image_hash=abc confidence=0.8]",
        messages=[],
        reply="En la imagen AAPL cotiza 150.2500 respecto al cierre (ejemplo).",
        db=_FakeDB(),
        spec=_FakeSpec(),
    )
    assert reason == "missing_tool_evidence_for_vlm_claim"
    assert "Regla de Evidencia" in reply


def test_visual_evidence_rule_accepts_verify_visual_claim_numeric() -> None:
    tool_msg = ToolMessage(
        content='{"status":"verified","symbol":"AAPL","claimed_value":150.25,"actual_value":150.20}',
        tool_call_id="1",
        name="verify_visual_claim",
    )
    class _FakeDB:
        def query(self, _q: str) -> str:
            return '[{"t": "AAPL"}]'

    class _FakeSpec:
        worker_id = "finanz"
        logical_worker_id = "finanz"
        quant_config = {"enabled": True}

    reply, reason = enforce_visual_evidence_rule(
        incoming="Usuario dice: x\n[VLM_CONTEXT image_hash=abc confidence=0.8]",
        messages=[tool_msg],
        reply="En la imagen AAPL cotiza 150.2500.",
        db=_FakeDB(),
        spec=_FakeSpec(),
    )
    assert reason is None
    assert "150.2500" in reply


def test_vlm_backend_order_mlx_only_without_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DUCKCLAW_VLM_PRIMARY", raising=False)
    monkeypatch.delenv("DUCKCLAW_VLM_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert vlm_mod._vlm_backend_order() == ["mlx"]


def test_vlm_backend_order_mlx_then_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DUCKCLAW_VLM_ALLOW_OPENAI_VISION", "1")
    monkeypatch.delenv("DUCKCLAW_VLM_PRIMARY", raising=False)
    monkeypatch.delenv("DUCKCLAW_VLM_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert vlm_mod._vlm_backend_order() == ["mlx", "openai"]


def test_vlm_backend_order_openai_key_ignored_without_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    """Sin opt-in explícito, OPENAI_API_KEY no entra en la cadena VLM (Gemma/mlx_vlm → Gemini)."""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("DUCKCLAW_VLM_ALLOW_OPENAI_VISION", raising=False)
    monkeypatch.delenv("DUCKCLAW_VLM_PRIMARY", raising=False)
    monkeypatch.delenv("DUCKCLAW_VLM_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert vlm_mod._vlm_backend_order() == ["mlx"]


def test_vlm_backend_order_openai_first_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DUCKCLAW_VLM_ALLOW_OPENAI_VISION", "1")
    monkeypatch.setenv("DUCKCLAW_VLM_PRIMARY", "openai")
    monkeypatch.delenv("DUCKCLAW_VLM_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert vlm_mod._vlm_backend_order() == ["openai", "mlx"]


def test_vlm_backend_order_mlx_gemini_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DUCKCLAW_VLM_ALLOW_OPENAI_VISION", "1")
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.delenv("DUCKCLAW_VLM_PRIMARY", raising=False)
    assert vlm_mod._vlm_backend_order() == ["mlx", "gemini", "openai"]


def test_vlm_backend_order_openai_first_with_gemini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("DUCKCLAW_VLM_ALLOW_OPENAI_VISION", "1")
    monkeypatch.setenv("DUCKCLAW_VLM_GEMINI_API_KEY", "g-dedicated")
    monkeypatch.setenv("DUCKCLAW_VLM_PRIMARY", "openai")
    assert vlm_mod._vlm_backend_order() == ["openai", "mlx", "gemini"]


def test_vlm_backend_order_mlx_gemini_when_openai_key_but_no_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.delenv("DUCKCLAW_VLM_ALLOW_OPENAI_VISION", raising=False)
    monkeypatch.setenv("GEMINI_API_KEY", "g-test")
    monkeypatch.delenv("DUCKCLAW_VLM_PRIMARY", raising=False)
    assert vlm_mod._vlm_backend_order() == ["mlx", "gemini"]


def test_vlm_gemini_api_key_prefers_dedicated_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_VLM_GEMINI_API_KEY", "dedicated")
    monkeypatch.setenv("GEMINI_API_KEY", "other")
    assert vlm_mod._vlm_gemini_api_key() == "dedicated"


def test_vlm_backend_order_mlx_gemini_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("GOOGLE_API_KEY", "g")
    monkeypatch.delenv("DUCKCLAW_VLM_PRIMARY", raising=False)
    assert vlm_mod._vlm_backend_order() == ["mlx", "gemini"]


def test_gemini_text_from_response_ok() -> None:
    data = {"candidates": [{"content": {"parts": [{"text": "Parte A"}, {"text": " B"}]}}]}
    assert vlm_mod._gemini_text_from_response(data) == "Parte A B"


def test_gemini_text_from_response_raises_on_empty() -> None:
    with pytest.raises(RuntimeError, match="sin candidates"):
        vlm_mod._gemini_text_from_response({})


def test_call_gemini_vision_parses_httpx_response() -> None:
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(
        return_value={"candidates": [{"content": {"parts": [{"text": "resumen visión"}]}}]}
    )
    mock_post = AsyncMock(return_value=mock_resp)

    class FakeClient:
        def __init__(self, *a: object, **k: object) -> None:
            pass

        async def __aenter__(self) -> FakeClient:
            return self

        async def __aexit__(self, *a: object) -> None:
            return None

        post = mock_post

    async def _run() -> str:
        with patch.object(vlm_mod.httpx, "AsyncClient", return_value=FakeClient()):
            return await vlm_mod._call_gemini_vision(
                api_key="fake",
                model="gemini-2.5-flash",
                mime_type="image/png",
                image_bytes=b"\x89PNG\r\n\x1a\n",
                user_caption="mira",
                http_timeout_s=30.0,
            )

    assert asyncio.run(_run()) == "resumen visión"
    mock_post.assert_called_once()
    call_kw = mock_post.call_args
    assert call_kw is not None
    assert "generateContent" in str(call_kw[0][0])
    assert call_kw[1].get("params", {}).get("key") == "fake"


def test_mlx_vlm_local_disabled_by_vlm_mlx_disable_local_alias(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_VLM_DISABLE_LOCAL_MLX_VLM", raising=False)
    monkeypatch.delenv("DUCKCLAW_VLM_MLX_DISABLE_LOCAL", raising=False)
    monkeypatch.setenv("VLM_MLX_DISABLE_LOCAL", "1")
    assert vlm_mod._mlx_vlm_local_enabled() is False
    assert vlm_mod._try_mlx_vlm_local_before_http() is False


def test_mlx_http_base_url_prefers_vlm_mlx_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_VLM_MLX_BASE_URL", raising=False)
    monkeypatch.setenv("VLM_MLX_BASE_URL", "http://127.0.0.1:8080/v1")
    assert vlm_mod._mlx_http_base_url() == "http://127.0.0.1:8080/v1"


def test_mlx_http_base_url_duckclaw_wins_over_vlm_mlx(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_VLM_MLX_BASE_URL", "http://10.0.0.1:9000/v1")
    monkeypatch.setenv("VLM_MLX_BASE_URL", "http://127.0.0.1:8080/v1")
    assert vlm_mod._mlx_http_base_url() == "http://10.0.0.1:9000/v1"


def test_httpx_trust_env_false_for_loopback_openai_base() -> None:
    assert vlm_mod._httpx_trust_env_for_openai_base("http://127.0.0.1:8080/v1") is False
    assert vlm_mod._httpx_trust_env_for_openai_base("http://localhost:9000/v1") is False
    assert vlm_mod._httpx_trust_env_for_openai_base("https://api.openai.com/v1") is True


def test_mlx_http_base_url_uses_mlx_port_when_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_VLM_MLX_BASE_URL", raising=False)
    monkeypatch.delenv("VLM_MLX_BASE_URL", raising=False)
    monkeypatch.setenv("MLX_PORT", "8080")
    assert vlm_mod._mlx_http_base_url() == "http://127.0.0.1:8080/v1"


def test_skip_mlx_openai_vision_when_loopback_same_port_as_mlx_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Copiar .env con VLM_MLX_BASE_URL=8080 y MLX_PORT=8080 no debe forzar HTTP visión (404)."""
    monkeypatch.delenv("DUCKCLAW_VLM_MLX_HTTP_ALLOW_DEFAULT_LOOPBACK", raising=False)
    monkeypatch.setenv("MLX_PORT", "8080")
    monkeypatch.setenv("VLM_MLX_BASE_URL", "http://127.0.0.1:8080/v1")
    base = vlm_mod._mlx_http_base_url()
    assert vlm_mod._skip_mlx_openai_vision_same_port_as_text_mlx(base) is True


def test_skip_mlx_openai_vision_false_when_vlm_on_other_loopback_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DUCKCLAW_VLM_MLX_HTTP_ALLOW_DEFAULT_LOOPBACK", raising=False)
    monkeypatch.setenv("MLX_PORT", "8080")
    assert vlm_mod._skip_mlx_openai_vision_same_port_as_text_mlx("http://127.0.0.1:9090/v1") is False


def test_skip_mlx_openai_vision_false_non_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLX_PORT", "8080")
    assert (
        vlm_mod._skip_mlx_openai_vision_same_port_as_text_mlx("https://api.openai.com/v1")
        is False
    )


def test_skip_mlx_openai_vision_false_when_allow_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MLX_PORT", "8080")
    monkeypatch.setenv("DUCKCLAW_VLM_MLX_HTTP_ALLOW_DEFAULT_LOOPBACK", "1")
    assert (
        vlm_mod._skip_mlx_openai_vision_same_port_as_text_mlx("http://127.0.0.1:8080/v1")
        is False
    )


def test_vlm_backend_order_openai_primary_without_key_falls_back_mlx_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("DUCKCLAW_VLM_PRIMARY", "openai")
    monkeypatch.delenv("DUCKCLAW_VLM_GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    assert vlm_mod._vlm_backend_order() == ["mlx"]


def test_suffix_for_mime() -> None:
    assert vlm_mod._suffix_for_mime("image/jpeg") == ".jpg"
    assert vlm_mod._suffix_for_mime("image/png") == ".png"
    assert vlm_mod._suffix_for_mime("image/webp") == ".webp"


def test_mlx_vlm_model_id_explicit_overrides_gemma_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_VLM_MLX_VLM_MODEL", raising=False)
    monkeypatch.delenv("MLX_VLM_MODEL", raising=False)
    monkeypatch.delenv("MLX_GEMMA4_MODEL_PATH", raising=False)
    monkeypatch.delenv("MLX_MODEL_ID", raising=False)
    monkeypatch.delenv("MLX_MODEL_PATH", raising=False)
    assert vlm_mod._mlx_vlm_model_id() == "mlx-community/gemma-4-e4b-it-4bit"


def test_mlx_vlm_model_id_respects_mlx_gemma4_path(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_VLM_MLX_VLM_MODEL", raising=False)
    monkeypatch.delenv("MLX_VLM_MODEL", raising=False)
    monkeypatch.setenv("MLX_GEMMA4_MODEL_PATH", "/opt/models/gemma4-e4b")
    assert vlm_mod._mlx_vlm_model_id() == "/opt/models/gemma4-e4b"


def test_mlx_vlm_model_id_respects_explicit_vlm_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_VLM_MLX_VLM_MODEL", "mlx-community/llava-v1.6-mistral-7b-4bit")
    assert vlm_mod._mlx_vlm_model_id() == "mlx-community/llava-v1.6-mistral-7b-4bit"


def test_vlm_exception_for_log_never_empty_on_blank_message() -> None:
    assert "Exception" in vlm_mod.vlm_exception_for_log(Exception(""))
    assert "sin mensaje" in vlm_mod.vlm_exception_for_log(Exception(""))


def test_mlx_http_vision_model_ignores_text_only_mlx_model_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PM2 suele fijar MLX_MODEL_ID al LLM de texto (Slayer); VLM HTTP debe usar Gemma por defecto."""
    monkeypatch.delenv("DUCKCLAW_VLM_MLX_MODEL", raising=False)
    monkeypatch.delenv("MLX_VISION_MODEL", raising=False)
    monkeypatch.delenv("DUCKCLAW_VLM_MLX_VLM_MODEL", raising=False)
    monkeypatch.delenv("MLX_VLM_MODEL", raising=False)
    monkeypatch.delenv("MLX_GEMMA4_MODEL_PATH", raising=False)
    monkeypatch.setenv("MLX_MODEL_ID", "/models/Slayer-8B-V1.1")
    assert vlm_mod._mlx_http_vision_model() == "mlx-community/gemma-4-e4b-it-4bit"


def test_mlx_vlm_processor_repo_maps_llava_mlx_to_hf(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DUCKCLAW_VLM_MLX_VLM_PROCESSOR_REPO", raising=False)
    assert (
        vlm_mod._mlx_vlm_processor_repo("mlx-community/llava-v1.6-mistral-7b-4bit")
        == "llava-hf/llava-v1.6-mistral-7b-hf"
    )


def test_mlx_vlm_processor_repo_explicit_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DUCKCLAW_VLM_MLX_VLM_PROCESSOR_REPO", "custom/repo")
    assert vlm_mod._mlx_vlm_processor_repo("mlx-community/foo") == "custom/repo"


def test_push_vlm_state_delta_redis_payload_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = _FakeRedisLists()
    monkeypatch.setenv("DUCKCLAW_VLM_STATE_DELTA_QUEUE", "q:test:vlm")

    async def _run() -> None:
        await vlm_mod.push_vlm_state_delta_redis(
            fake,
            tenant_id="wr_-1001",
            image_hash="abc",
            vlm_summary="VIX 24",
            confidence_score=0.91,
        )

    asyncio.run(_run())
    assert len(fake.lpush_calls) == 1
    qkey, raw = fake.lpush_calls[0]
    assert qkey == "q:test:vlm"
    body = json.loads(raw)
    assert body["delta_type"] == "VLM_CONTEXT_EXTRACTED"
    assert body["tenant_id"] == "wr_-1001"
    assert body["mutation"]["image_hash"] == "abc"
    assert body["mutation"]["confidence_score"] == 0.91


def test_wr_vlm_collect_album_single_message() -> None:
    r = _FakeRedisLists()

    async def _run() -> None:
        x = await _wr_vlm_collect_album_items(
            r,
            tenant_id="wr_-9",
            media_group_id="album-1",
            file_id="f1",
            mime_type="image/png",
            caption="hi",
        )
        assert x == [{"file_id": "f1", "mime": "image/png", "cap": "hi"}]

    asyncio.run(_run())


def test_wr_vlm_collect_album_parallel_one_leader_merges(monkeypatch: pytest.MonkeyPatch) -> None:
    _real_asyncio_sleep = asyncio.sleep

    async def _yield_sleep(_t: float = 0.0) -> None:
        await _real_asyncio_sleep(0)

    monkeypatch.setattr(_tg_wh.asyncio, "sleep", _yield_sleep)
    r = _FakeRedisLists()
    tenant = "wr_z"
    mg = "g1"

    async def _one(fid: str, cap: str) -> list[dict[str, str]] | None:
        return await _wr_vlm_collect_album_items(
            r,
            tenant_id=tenant,
            media_group_id=mg,
            file_id=fid,
            mime_type="image/jpeg",
            caption=cap,
        )

    async def _run() -> None:
        a, b = await asyncio.gather(_one("fa", ""), _one("fb", "@bot"))
        assert (a is None) ^ (b is None)
        merged = a if a is not None else b
        assert merged is not None
        ids = {x["file_id"] for x in merged}
        assert ids == {"fa", "fb"}

    asyncio.run(_run())


def test_wr_vlm_collect_album_caps_at_three_unique(monkeypatch: pytest.MonkeyPatch) -> None:
    _real_asyncio_sleep = asyncio.sleep

    async def _yield_sleep(_t: float = 0.0) -> None:
        await _real_asyncio_sleep(0)

    monkeypatch.setattr(_tg_wh.asyncio, "sleep", _yield_sleep)
    r = _FakeRedisLists()
    tenant = "wr_cap"
    mg = "g2"

    async def _one(fid: str) -> list[dict[str, str]] | None:
        return await _wr_vlm_collect_album_items(
            r,
            tenant_id=tenant,
            media_group_id=mg,
            file_id=fid,
            mime_type="image/jpeg",
            caption="",
        )

    async def _run() -> None:
        outs = await asyncio.gather(_one("a"), _one("b"), _one("a"), _one("c"), _one("d"))
        leader = [o for o in outs if o is not None]
        assert len(leader) == 1
        assert len(leader[0]) == 3
        assert {x["file_id"] for x in leader[0]} <= {"a", "b", "c", "d"}
        assert len({x["file_id"] for x in leader[0]}) == 3

    asyncio.run(_run())
