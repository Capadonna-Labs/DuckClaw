"""Búsqueda web local-first: SearXNG si hay URL; si no, DuckDuckGo HTML.

Sin API key de terceros. Spec soberanía: research no monopoliza Tavily.
"""

from __future__ import annotations

import logging
import os
import re
from html import unescape
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)

SEARXNG_ENV = "DUCKCLAW_SEARXNG_URL"
_USER_AGENT = "DuckClaw/1.0 (+local research; httpx)"


class WebSearchInput(BaseModel):
    """Esquema para ``web_search`` (OpenAI-compat / MLX)."""

    query: str = Field(
        ...,
        description=(
            "Consulta de búsqueda web local (sin API cloud). "
            "Usa términos concretos; site:dominio cuando aplique."
        ),
    )


def searxng_base_url() -> str:
    return (os.environ.get(SEARXNG_ENV) or "").strip().rstrip("/")


def local_search_backend() -> str:
    """Nombre del backend activo (`searxng` | `duckduckgo`)."""
    return "searxng" if searxng_base_url() else "duckduckgo"


def _hostname(url: str) -> str:
    host = (urlparse(url).hostname or "").strip().lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _domain_allowed(url: str, include_domains: list[str] | None) -> bool:
    if not include_domains:
        return True
    host = _hostname(url)
    if not host:
        return False
    for spec in include_domains:
        d = (spec or "").strip().lower()
        if d.startswith("www."):
            d = d[4:]
        if not d:
            continue
        if host == d or host.endswith("." + d):
            return True
    return False


def _unwrap_ddg_href(href: str) -> str:
    """DuckDuckGo envuelve destinos en /l/?uddg=..."""
    raw = (href or "").strip()
    if not raw:
        return ""
    if "uddg=" in raw:
        parsed = urlparse(raw if "://" in raw else f"https://duckduckgo.com{raw}")
        qs = parse_qs(parsed.query)
        uddg = (qs.get("uddg") or [""])[0]
        if uddg:
            return unquote(uddg)
    if raw.startswith("//"):
        return "https:" + raw
    return raw


def _searxng_search(query: str, *, max_results: int) -> list[dict[str, str]]:
    import httpx

    base = searxng_base_url()
    url = f"{base}/search"
    with httpx.Client(timeout=20.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT}) as client:
        resp = client.get(url, params={"q": query, "format": "json"})
        resp.raise_for_status()
        payload = resp.json()
    results_raw = payload.get("results") if isinstance(payload, dict) else None
    if not isinstance(results_raw, list):
        return []
    out: list[dict[str, str]] = []
    for item in results_raw:
        if not isinstance(item, dict):
            continue
        link = str(item.get("url") or "").strip()
        title = str(item.get("title") or "Sin título").strip()
        content = str(item.get("content") or item.get("snippet") or "").strip()
        if not link:
            continue
        out.append({"title": title, "url": link, "content": content})
        if len(out) >= max_results:
            break
    return out


def _ddg_html_search(query: str, *, max_results: int) -> list[dict[str, str]]:
    import httpx

    with httpx.Client(timeout=20.0, follow_redirects=True, headers={"User-Agent": _USER_AGENT}) as client:
        resp = client.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
        )
        resp.raise_for_status()
        html = resp.text

    # result__a anchors (DDG HTML)
    pattern = re.compile(
        r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
        re.IGNORECASE | re.DOTALL,
    )
    snippet_pat = re.compile(
        r'class="result__snippet"[^>]*>(.*?)</(?:a|td|div)>',
        re.IGNORECASE | re.DOTALL,
    )
    snippets = [re.sub(r"<[^>]+>", "", unescape(s)).strip() for s in snippet_pat.findall(html)]

    out: list[dict[str, str]] = []
    for i, match in enumerate(pattern.finditer(html)):
        href = _unwrap_ddg_href(unescape(match.group(1)))
        title = re.sub(r"<[^>]+>", "", unescape(match.group(2))).strip() or "Sin título"
        if not href.startswith("http"):
            continue
        content = snippets[i] if i < len(snippets) else ""
        out.append({"title": title, "url": href, "content": content})
        if len(out) >= max_results:
            break
    return out


def search_web(
    query: str,
    *,
    max_results: int = 5,
    include_domains: list[str] | None = None,
) -> list[dict[str, str]]:
    """Ejecuta búsqueda local; filtra por include_domains si se pasa."""
    q = (query or "").strip()
    if not q:
        return []
    try:
        cap = max(1, min(int(max_results), 25))
    except (TypeError, ValueError):
        cap = 5

    fetch_n = cap * 3 if include_domains else cap
    try:
        if searxng_base_url():
            rows = _searxng_search(q, max_results=fetch_n)
        else:
            rows = _ddg_html_search(q, max_results=fetch_n)
    except Exception as exc:
        _log.warning("local_web_search falló (%s): %s", local_search_backend(), exc)
        raise

    if not include_domains:
        return rows[:cap]
    filtered = [r for r in rows if _domain_allowed(r.get("url", ""), include_domains)]
    return filtered[:cap]


def format_search_results(
    results: list[dict[str, str]],
    *,
    backend: str | None = None,
    error: str | None = None,
) -> str:
    if error:
        return f"Error búsqueda local ({backend or local_search_backend()}): {error}"
    if not results:
        return "No se encontraron resultados."
    label = backend or local_search_backend()
    parts = [f"## Fuentes ({label})\n"]
    for i, r in enumerate(results, 1):
        title = r.get("title") or "Sin título"
        url = r.get("url") or ""
        content = r.get("content") or ""
        parts.append(f"{i}. **{title}**\n   - URL: {url}\n")
        if content:
            clip = content[:500]
            parts.append(f"   - {clip}{'...' if len(content) > 500 else ''}\n")
    return "\n".join(parts)


def _host_from_domain_spec(spec: str) -> str:
    s = (spec or "").strip()
    if not s:
        return ""
    if "://" in s:
        return _hostname(s)
    host = s.split("/")[0].strip().lower()
    if ":" in host and host.rsplit(":", 1)[-1].isdigit():
        host = host.rsplit(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    return host


def _normalize_include_domains(raw: Any) -> list[str]:
    if raw is None:
        return []
    if isinstance(raw, str):
        items: list[Any] = [raw]
    elif isinstance(raw, (list, tuple)):
        items = list(raw)
    else:
        return []
    seen: set[str] = set()
    out: list[str] = []
    for it in items:
        h = _host_from_domain_spec(str(it))
        if h and h not in seen:
            seen.add(h)
            out.append(h)
    return out


class ReadWebPageInput(BaseModel):
    url: str = Field(..., description="URL pública http(s) del artículo o página a leer.")


_PAGE_MAX_BYTES = 2_000_000
_SKIP_TAGS = frozenset({"script", "style", "noscript", "svg", "nav", "footer", "header", "form", "aside", "iframe"})


def _public_http_url(url: str) -> str | None:
    """Error text if ``url`` is not a public http(s) URL (the agent picks it: no SSRF into the host,
    the tailnet, private ranges or cloud metadata)."""
    import ipaddress
    import socket

    parsed = urlparse((url or "").strip())
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        return "solo URLs http(s) públicas"
    try:
        infos = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except OSError as exc:
        return f"no se pudo resolver {parsed.hostname}: {exc}"
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if not ip.is_global or ip in ipaddress.ip_network("100.64.0.0/10"):
            return f"dirección no pública ({ip}): bloqueada"
    return None


def page_text(html_text: str) -> tuple[str, str]:
    """(title, readable text) with the stdlib parser: drops scripts, menus and footers."""
    from html.parser import HTMLParser

    class _P(HTMLParser):
        def __init__(self) -> None:
            super().__init__()
            self.skip = 0
            self.title = ""
            self.in_title = False
            self.parts: list[str] = []

        def handle_starttag(self, tag, attrs):  # noqa: ANN001
            if tag in _SKIP_TAGS:
                self.skip += 1
            elif tag == "title":
                self.in_title = True
            elif tag in ("p", "br", "li", "h1", "h2", "h3", "h4", "tr", "div", "section", "article"):
                self.parts.append("\n")

        def handle_endtag(self, tag):  # noqa: ANN001
            if tag in _SKIP_TAGS and self.skip:
                self.skip -= 1
            elif tag == "title":
                self.in_title = False

        def handle_data(self, data):  # noqa: ANN001
            if self.in_title:
                self.title += data
            elif not self.skip:
                self.parts.append(data)

    p = _P()
    p.feed(html_text)
    lines = [re.sub(r"[ \t\r\f\v]+", " ", ln).strip() for ln in "".join(p.parts).split("\n")]
    text = "\n".join(ln for ln in lines if len(ln) > 1)
    return unescape(p.title.strip()), re.sub(r"\n{3,}", "\n\n", text)


def read_web_page(url: str, *, max_chars: int = 12000) -> str:
    import httpx

    err = _public_http_url(url)
    if err:
        return f"No leída: {err}."
    try:
        with httpx.Client(timeout=20.0, follow_redirects=False, headers={"User-Agent": _USER_AGENT}) as client:
            target = url
            for _ in range(4):  # follow redirects by hand so every hop passes the public-URL check
                resp = client.get(target)
                if resp.is_redirect and resp.headers.get("location"):
                    target = str(resp.next_request.url) if resp.next_request else resp.headers["location"]
                    err = _public_http_url(target)
                    if err:
                        return f"No leída (redirección): {err}."
                    continue
                break
            if resp.status_code >= 400:
                return f"No leída: HTTP {resp.status_code} en {target} (¿muro de pago o bloqueo?)."
            ctype = resp.headers.get("content-type", "")
            if "html" not in ctype and "text" not in ctype:
                return f"No leída: tipo de contenido {ctype or 'desconocido'} (no es una página de texto)."
            title, text = page_text(resp.content[:_PAGE_MAX_BYTES].decode(resp.encoding or "utf-8", "replace"))
    except Exception as exc:  # noqa: BLE001
        return f"No leída: {exc}"
    if len(text) < 200:
        return f"{title}\n\n(La página casi no tiene texto legible: puede requerir JavaScript o registro.)\n{text}"
    cut = len(text) > max_chars
    return f"{title}\n{target}\n\n{text[:max_chars]}" + ("\n\n[… texto recortado]" if cut else "")


def local_read_page_tool(config: dict[str, Any] | None = None) -> Any | None:
    """StructuredTool ``read_web_page``: keyless page reader (stand-in for tavily_extract)."""
    cfg = config or {}
    if cfg.get("local_search_enabled") is False:
        return None
    from langchain_core.tools import StructuredTool

    return StructuredTool.from_function(
        lambda url: read_web_page(url),
        name="read_web_page",
        description=(
            "Lee el texto de una página web pública (artículo, nota de prensa) sin API key: úsala "
            "para abrir un resultado de web_search. No sirve para contenido tras registro o muro de pago."
        ),
        args_schema=ReadWebPageInput,
    )


def local_web_search_tool(config: dict[str, Any] | None = None) -> Any | None:
    """StructuredTool ``web_search`` (SearXNG o DuckDuckGo)."""
    cfg = config or {}
    if cfg.get("local_search_enabled") is False:
        return None

    from langchain_core.tools import StructuredTool

    try:
        max_results = int(cfg.get("max_results", 5))
    except (TypeError, ValueError):
        max_results = 5
    include_domains = _normalize_include_domains(cfg.get("include_domains"))
    backend = local_search_backend()

    def _search(query: str) -> str:
        try:
            rows = search_web(
                query,
                max_results=max_results,
                include_domains=include_domains or None,
            )
            return format_search_results(rows, backend=backend)
        except Exception as exc:
            err = str(exc)
            offline_hint = (
                " Sin red (o backend caído): no hay búsqueda web. "
                "Usa search_project_knowledge / list_project_knowledge / "
                "read_project_knowledge sobre la bóveda local, o semantic_memory."
            )
            low = err.lower()
            if any(
                x in low
                for x in (
                    "nodename",
                    "name or service not known",
                    "failed to resolve",
                    "connection refused",
                    "network is unreachable",
                    "timed out",
                    "timeout",
                    "temporary failure",
                    "offline",
                )
            ):
                return format_search_results([], backend=backend, error=err + offline_hint)
            return format_search_results([], backend=backend, error=err)

    desc = (
        f"Busca en internet sin Tavily ({backend}). "
        "Preferir esta tool cuando no haga falta profundidad comercial de Tavily. "
        "Parámetro: query."
    )
    if include_domains:
        desc += f" Dominios preferidos: {', '.join(include_domains)}."

    return StructuredTool.from_function(
        _search,
        name="web_search",
        description=desc,
        args_schema=WebSearchInput,
    )
