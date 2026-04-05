"""Helpers de Reddit / Groq en factory (URLs, intención follow-up, bind sin reddit_*)."""

from langchain_core.messages import HumanMessage

from duckclaw.workers.factory import (
    _extract_first_reddit_url,
    _finanz_followup_reddit_read_intent,
    _groq_tools_without_reddit_for_bind,
    _most_recent_reddit_url_in_human_messages,
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


def test_groq_tools_without_reddit_for_bind_filters_prefix() -> None:
    class T:
        def __init__(self, name: str) -> None:
            self.name = name

    mixed = [T("read_sql"), T("reddit_get_post"), T("reddit_search_reddit")]
    out = _groq_tools_without_reddit_for_bind(mixed)
    assert [x.name for x in out] == ["read_sql"]
