"""Helpers de Reddit / Groq en factory (URLs, intención follow-up, bind sin reddit_*)."""

import json
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage

from duckclaw.workers.factory import (
    _extract_first_reddit_url,
    _fetch_reddit_post_via_public_json,
    _finanz_followup_reddit_read_intent,
    _quant_trader_vlm_incoming_suggests_market_figure,
    _groq_tools_without_reddit_for_bind,
    _most_recent_reddit_url_in_human_messages,
    _patch_reddit_get_post_args_from_canonical_url,
    _quant_trader_reddit_history_anchor_intent,
    _resolve_reddit_share_url_to_comments_url,
    _subreddit_and_post_id_from_reddit_comments_url,
    incoming_is_schema_query_heuristic,
    quant_trader_lone_reddit_url_message,
    reddit_share_search_query_for_attempt,
    reddit_share_shortlink_fallback_query,
)


def test_extract_first_reddit_url_share_and_classic() -> None:
    u = "https://www.reddit.com/r/worldnews/s/OsmqJ6G0jS"
    assert _extract_first_reddit_url(f"prefix {u} suffix") == u
    classic = "https://www.reddit.com/r/foo/comments/abc123/title/"
    assert _extract_first_reddit_url(classic) == classic


def test_followup_reddit_read_intent() -> None:
    assert _finanz_followup_reddit_read_intent("Puedes leer el post de reddit?")
    assert not _finanz_followup_reddit_read_intent("Dame mis saldos")
    assert not _finanz_followup_reddit_read_intent("reddit es genial")


def test_most_recent_reddit_url_from_humans() -> None:
    older = HumanMessage(content="https://www.reddit.com/r/a/comments/old123/x")
    newer = HumanMessage(content="Ver https://www.reddit.com/r/b/s/ShareSlug1")
    assert _most_recent_reddit_url_in_human_messages([older, newer]) == "https://www.reddit.com/r/b/s/ShareSlug1"


def test_quant_trader_reddit_history_anchor_retry_without_url() -> None:
    share = "https://www.reddit.com/r/wallstreetbets/s/wAmLggXf0Y"
    msgs = [
        HumanMessage(content=f"Mira {share}"),
        HumanMessage(content="vuelve a intentar, ya cambié la variable de entorno"),
    ]
    assert _quant_trader_reddit_history_anchor_intent(
        "vuelve a intentar, ya cambié la variable de entorno", msgs
    )


def test_quant_trader_reddit_history_anchor_false_when_url_in_turn() -> None:
    share = "https://www.reddit.com/r/x/s/AbCdEfGhIj"
    msgs = [HumanMessage(content="algo"), HumanMessage(content=f"retry {share}")]
    assert not _quant_trader_reddit_history_anchor_intent(f"lee {share}", msgs)


def test_quant_trader_reddit_history_anchor_requires_share_link() -> None:
    classic = "https://www.reddit.com/r/foo/comments/abc123/title"
    msgs = [HumanMessage(content=classic), HumanMessage(content="reintenta")]
    assert not _quant_trader_reddit_history_anchor_intent("reintenta", msgs)


def test_quant_trader_vlm_incoming_market_figure_detection() -> None:
    vlm = (
        "Usuario dice: (sin caption)\nContexto visual adjunto: Advanced Micro Devices: 465.00.\n"
        "[VLM_CONTEXT image_hash=abc]"
    )
    assert _quant_trader_vlm_incoming_suggests_market_figure(vlm)
    assert not _quant_trader_vlm_incoming_suggests_market_figure("solo texto 465.00 sin vlm")
    assert not _quant_trader_vlm_incoming_suggests_market_figure(
        "Contexto visual adjunto: sin decimal tipo cotización"
    )


def test_quant_trader_reddit_anchor_suppressed_when_vlm_turn_is_newer() -> None:
    """Retry genérico no debe forzar reddit_* si hubo foto/VLM después del share."""
    share = "https://www.reddit.com/r/quant/s/AbCdEfGhIj"
    msgs = [
        HumanMessage(content=f"Mira {share}"),
        HumanMessage(
            content="Usuario dice: (sin caption)\nContexto visual adjunto: AMD 465 semiconductor.\n[VLM_CONTEXT image_hash=test123trunc...]"
        ),
        HumanMessage(content="vuelve a intentar"),
    ]
    assert not _quant_trader_reddit_history_anchor_intent("vuelve a intentar", msgs)


def test_resolve_reddit_share_url_follows_redirect_to_comments() -> None:
    share = "https://www.reddit.com/r/worldnews/s/oKlI2Uc2lf"
    canonical = "https://www.reddit.com/r/worldnews/comments/abc123xyz/us_begins_blockade"

    mock_resp = MagicMock()
    mock_resp.geturl.return_value = canonical
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_resp
    mock_cm.__exit__.return_value = False

    with patch("duckclaw.workers.factory._urllib_request.urlopen", return_value=mock_cm):
        assert _resolve_reddit_share_url_to_comments_url(share) == canonical


def test_resolve_reddit_share_url_rejects_app_share_tracking_redirect() -> None:
    """Evidencia gateway: /s/… 301 a /comments/<id>?share_id=…&utm_medium=android_app puede ser post incorrecto."""
    share = "https://www.reddit.com/r/USNEWS/s/Fuaino2nbg"
    tracked = (
        "https://www.reddit.com/r/USNEWS/comments/1t95z0u/title/"
        "?share_id=BsNx2q_jvW5sdc_wpg_m9&utm_source=share&utm_medium=android_app"
    )
    mock_resp = MagicMock()
    mock_resp.geturl.return_value = tracked
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_resp
    mock_cm.__exit__.return_value = False

    with patch("duckclaw.workers.factory._urllib_request.urlopen", return_value=mock_cm):
        assert _resolve_reddit_share_url_to_comments_url(share) is None


def test_resolve_reddit_share_url_trust_env_restores_tracking_redirect(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    share = "https://www.reddit.com/r/USNEWS/s/Fuaino2nbg"
    tracked = (
        "https://www.reddit.com/r/USNEWS/comments/1t95z0u/title/"
        "?share_id=BsNx2q_jvW5sdc_wpg_m9&utm_source=share"
    )
    mock_resp = MagicMock()
    mock_resp.geturl.return_value = tracked
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_resp
    mock_cm.__exit__.return_value = False

    monkeypatch.setenv("DUCKCLAW_REDDIT_TRUST_SHARE_TRACKING_REDIRECT", "1")
    with patch("duckclaw.workers.factory._urllib_request.urlopen", return_value=mock_cm):
        expected = tracked.split("#")[0].split("?")[0].rstrip("/")
        assert _resolve_reddit_share_url_to_comments_url(share) == expected


def test_resolve_reddit_share_url_returns_none_when_not_share_link() -> None:
    assert _resolve_reddit_share_url_to_comments_url("https://example.com") is None


def test_subreddit_and_post_id_from_comments_url() -> None:
    u = "https://www.reddit.com/r/worldnews/comments/1skcbpd/us_begins_blockade/?x=1"
    assert _subreddit_and_post_id_from_reddit_comments_url(u) == ("worldnews", "1skcbpd")


def test_patch_reddit_get_post_overwrites_slug_with_real_post_id() -> None:
    canonical = "https://www.reddit.com/r/worldnews/comments/1skcbpd/title/"
    msg = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "reddit_get_post",
                "args": {"subreddit": "worldnews", "post_id": "oKlI2Uc2lf"},
                "id": "call_1",
            }
        ],
    )
    out = _patch_reddit_get_post_args_from_canonical_url(msg, canonical)
    assert out.tool_calls[0]["args"]["post_id"] == "1skcbpd"
    assert out.tool_calls[0]["args"]["subreddit"] == "worldnews"


def test_schema_heuristic_false_for_lone_article_url_with_estructura_slug() -> None:
    u = (
        "https://www.elconfidencial.com/tecnologia/ciencia/"
        "2026-05-10/europa-colombia-estructura-5-5-km-1qrt_4350818/"
    )
    assert not incoming_is_schema_query_heuristic(u)


def test_schema_heuristic_true_for_explicit_table_question() -> None:
    assert incoming_is_schema_query_heuristic("qué tablas hay en duckdb")


def test_reddit_share_shortlink_fallback_query_not_raw_url() -> None:
    u = "https://www.reddit.com/r/USNEWS/s/h3kvg1pisI"
    assert reddit_share_shortlink_fallback_query(u) == "r/USNEWS shortlink h3kvg1pisI"
    assert "http" not in reddit_share_shortlink_fallback_query(u)


def test_reddit_share_search_query_for_attempt_progression() -> None:
    u = "https://www.reddit.com/r/USNEWS/s/h3kvg1pisI"
    assert reddit_share_search_query_for_attempt(u, 0) == "r/USNEWS shortlink h3kvg1pisI"
    assert reddit_share_search_query_for_attempt(u, 1) == "USNEWS h3kvg1pisI"
    assert reddit_share_search_query_for_attempt(u, 2) == "h3kvg1pisI"


def test_quant_lone_reddit_url_message_for_share_link() -> None:
    anchor = "https://www.reddit.com/r/USNEWS/s/h3kvg1pisI"
    assert quant_trader_lone_reddit_url_message(
        "quant_trader",
        anchor,
        anchor,
    )
    assert not quant_trader_lone_reddit_url_message(
        "quant_trader",
        f"Mira este post\n{anchor}",
        anchor,
    )
    assert not quant_trader_lone_reddit_url_message("finanz", anchor, anchor)


def test_quant_reddit_history_anchor_vuelve_a_intentar() -> None:
    share = "https://www.reddit.com/r/worldnews/s/GSxMO27P59"
    msgs = [
        HumanMessage(content=share),
        HumanMessage(content="Vuelve a intentar"),
    ]
    assert _quant_trader_reddit_history_anchor_intent("Vuelve a intentar", msgs)


def test_fetch_reddit_post_via_public_json_parses_listing() -> None:
    comments_url = "https://www.reddit.com/r/worldnews/comments/abc123/title/"
    reddit_payload = [
        {
            "data": {
                "children": [
                    {
                        "data": {
                            "title": "Test headline",
                            "selftext": "Body text",
                            "score": 42,
                            "permalink": "/r/worldnews/comments/abc123/title/",
                            "is_self": True,
                            "url": "https://www.reddit.com/r/worldnews/comments/abc123/title/",
                        }
                    }
                ]
            }
        }
    ]
    mock_resp = MagicMock()
    mock_resp.read.return_value = json.dumps(reddit_payload).encode("utf-8")
    mock_cm = MagicMock()
    mock_cm.__enter__.return_value = mock_resp
    mock_cm.__exit__.return_value = False

    with patch("duckclaw.workers.factory._urllib_request.urlopen", return_value=mock_cm):
        out = _fetch_reddit_post_via_public_json(comments_url)

    assert out is not None
    parsed = json.loads(out)
    assert parsed["success"] is True
    assert parsed["subreddit"] == "worldnews"
    assert len(parsed["posts"]) == 1
    assert parsed["posts"][0]["title"] == "Test headline"
    assert parsed["posts"][0]["id"] == "abc123"


def test_fetch_reddit_post_via_public_json_returns_none_on_bad_url() -> None:
    assert _fetch_reddit_post_via_public_json("https://example.com") is None


def test_groq_tools_without_reddit_for_bind_filters_prefix() -> None:
    class T:
        def __init__(self, name: str) -> None:
            self.name = name

    mixed = [T("read_sql"), T("reddit_get_post"), T("reddit_search_reddit")]
    out = _groq_tools_without_reddit_for_bind(mixed)
    assert [x.name for x in out] == ["read_sql"]
