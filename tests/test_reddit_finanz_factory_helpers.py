"""Helpers de Reddit / Groq en factory (URLs, intención follow-up, bind sin reddit_*)."""

from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

from duckclaw.workers.factory import (
    _extract_first_reddit_url,
    _finanz_followup_reddit_read_intent,
    _groq_tools_without_reddit_for_bind,
    _most_recent_reddit_url_in_human_messages,
    _patch_reddit_get_post_args_from_canonical_url,
    _resolve_reddit_share_url_to_comments_url,
    _subreddit_and_post_id_from_reddit_comments_url,
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


def test_groq_tools_without_reddit_for_bind_filters_prefix() -> None:
    class T:
        def __init__(self, name: str) -> None:
            self.name = name

    mixed = [T("read_sql"), T("reddit_get_post"), T("reddit_search_reddit")]
    out = _groq_tools_without_reddit_for_bind(mixed)
    assert [x.name for x in out] == ["read_sql"]
