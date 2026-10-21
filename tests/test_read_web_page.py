"""read_web_page: keyless page reader for agents, never a way into the host or the private network."""

from __future__ import annotations


def test_page_text_keeps_the_article_and_drops_chrome() -> None:
    from duckclaw.forge.skills.local_web_search import page_text

    title, text = page_text(
        "<html><head><title>Oil &amp; bonds</title><style>p{}</style></head><body>"
        "<nav>Home | Markets</nav><article><h1>Brent hits 111</h1><p>Prices rose 2% on Tuesday.</p></article>"
        "<script>track()</script><footer>© 2026</footer></body></html>"
    )
    assert title == "Oil & bonds"
    assert "Brent hits 111" in text and "Prices rose 2% on Tuesday." in text
    assert "Home" not in text and "track()" not in text and "2026" not in text


def test_internal_addresses_are_refused() -> None:
    from duckclaw.forge.skills.local_web_search import _public_http_url, read_web_page

    for url in ("http://127.0.0.1:8000/api", "http://localhost/", "http://169.254.169.254/latest/meta-data",
                "http://10.0.0.5/", "http://192.168.1.1/", "http://100.79.185.46:3000/", "file:///etc/passwd",
                "ftp://example.com/x"):
        assert _public_http_url(url), url
    assert read_web_page("http://127.0.0.1:8000/").startswith("No leída")
