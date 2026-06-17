"""Reddit URL/share resolution helpers for worker graph."""

from __future__ import annotations

import json
import logging
import os
import re
import time
from typing import Any, Optional
from urllib import request as _urllib_request
from urllib.parse import parse_qs, urlparse

_log = logging.getLogger(__name__)

_REDDIT_SHARE_PATH_RE = re.compile(r"reddit\.com/r/[\w_]+/s/[a-zA-Z0-9]+", re.IGNORECASE)
_REDDIT_COMMENTS_IN_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?reddit\.com/r/[\w_]+/comments/[a-z0-9]+",
    re.IGNORECASE,
)
# post_id en la ruta (p. ej. 1skcbpd), no el slug /s/xxxx
_REDDIT_COMMENTS_SUB_POST_RE = re.compile(
    r"reddit\.com/r/([\w_]+)/comments/([a-z0-9]+)",
    re.IGNORECASE,
)


def reddit_share_shortlink_fallback_query(share_url: str) -> str:
    """
    reddit_search_reddit con ``query=<URL /s/…>`` rompe el servidor MCP (`children`).
    Preferir texto ``r/<subreddit> shortlink <slug>`` (alineado con la spec Reddit MCP).
    """
    raw = (share_url or "").strip()
    m = re.search(r"/r/([\w_]+)/s/([a-zA-Z0-9]+)", raw, re.IGNORECASE)
    if m:
        return f"r/{m.group(1)} shortlink {m.group(2)}"
    return raw


def reddit_share_search_query_for_attempt(share_url: str, attempt_index: int) -> str:
    """
    Evidencia gateway: ``r/<sub> shortlink <slug>`` devolvió hilos irrelevantes (p. ej. r/all).
    Segundo intento: query más corta ``<sub> <slug>``; siguientes: sólo ``<slug>``.
    ``attempt_index`` = nº de ToolMessage ``reddit_search_reddit`` ya en el historial antes de esta llamada.
    """
    raw = (share_url or "").strip()
    slug_m = re.search(r"/s/([a-zA-Z0-9]+)", raw, re.IGNORECASE)
    slug = slug_m.group(1) if slug_m else ""
    sub_m = re.search(r"/r/([\w_]+)/s/", raw, re.IGNORECASE)
    sub = sub_m.group(1) if sub_m else ""
    if attempt_index <= 0:
        return reddit_share_shortlink_fallback_query(raw)
    if slug and sub:
        if attempt_index == 1:
            return f"{sub} {slug}"
        return slug
    return reddit_share_shortlink_fallback_query(raw)


def _reddit_trust_share_tracking_redirect() -> bool:
    """
    Reddit puede 301 /r/*/s/<slug> hacia .../comments/<id>/?share_id=&utm_=android_app
    donde <id> no coincide con lo que enlazaba el cliente. Default: **no confiar**.
    Override: ``DUCKCLAW_REDDIT_TRUST_SHARE_TRACKING_REDIRECT=1``.
    """
    return (os.environ.get("DUCKCLAW_REDDIT_TRUST_SHARE_TRACKING_REDIRECT") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _reddit_tools_paused() -> bool:
    """Opt-in: omitir invocaciones reddit_* (p. ej. API 403 / OAuth roto). ``DUCKCLAW_REDDIT_PAUSED=1``."""
    return (os.environ.get("DUCKCLAW_REDDIT_PAUSED") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _reddit_comments_url_has_share_tracking(canonical_comments_url: str) -> bool:
    """
    Redirects intermedios típicos de «compartir desde app»: utm_medium=android_app + share_id=…
    (evidencia runtime: mismo slug /s/Fu… redirige vía servidor a otro submission).
    """
    try:
        q = parse_qs(urlparse(canonical_comments_url).query or "")
        if q.get("share_id"):
            return True
        utm_src = [str(x).lower() for x in q.get("utm_source", [])]
        utm_med = [str(x).lower() for x in q.get("utm_medium", [])]
        if "share" in utm_src:
            return True
        if any(x in {"android_app", "iphone_app", "mobile_app"} for x in utm_med):
            return True
        return False
    except Exception:
        return False


def _subreddit_and_post_id_from_reddit_comments_url(url: str) -> tuple[Optional[str], Optional[str]]:
    m = _REDDIT_COMMENTS_SUB_POST_RE.search(url or "")
    if not m:
        return None, None
    return m.group(1), m.group(2)


def _patch_reddit_get_post_args_from_canonical_url(resp: Any, canonical_comments_url: str) -> Any:
    """
    tool_choice fuerza reddit_get_post pero el modelo a veces pone el slug /s/... como post_id.
    Si ya resolvimos la URL canónica, sobrescribimos subreddit/post_id antes de tools_node.
    """
    sub, pid = _subreddit_and_post_id_from_reddit_comments_url(canonical_comments_url)
    if not sub or not pid or resp is None:
        return resp
    tcs = list(getattr(resp, "tool_calls", None) or [])
    if not tcs:
        return resp
    new_tcs: list[Any] = []
    patched_any = False
    for tc in tcs:
        if isinstance(tc, dict):
            name = tc.get("name")
            if name != "reddit_get_post":
                new_tcs.append(tc)
                continue
            args = dict(tc.get("args") or {})
            args["subreddit"] = sub
            args["post_id"] = pid
            new_tcs.append({**tc, "args": args})
            patched_any = True
            continue
        name = getattr(tc, "name", None)
        if name != "reddit_get_post":
            new_tcs.append(tc)
            continue
        base = getattr(tc, "args", None)
        args = dict(base) if isinstance(base, dict) else {}
        args["subreddit"] = sub
        args["post_id"] = pid
        try:
            new_tcs.append(tc.model_copy(update={"args": args}))
            patched_any = True
        except Exception:
            new_tcs.append(tc)
    if not patched_any:
        return resp
    try:
        return resp.model_copy(update={"tool_calls": new_tcs})
    except Exception:
        return resp


def _resolve_reddit_share_url_to_comments_url(url: str, *, timeout: float = 12.0) -> Optional[str]:
    """
    Sigue redirecciones HTTP de enlaces de compartir /r/<sub>/s/<slug> hasta la URL canónica
    .../comments/<post_id>/... para usar reddit_get_post. mcp-reddit suele fallar con
    reddit_search_reddit(query=<url>) (p. ej. error leyendo 'children').
    """
    raw = (url or "").strip()
    if not raw or not _REDDIT_SHARE_PATH_RE.search(raw):
        return None
    ua = (os.environ.get("REDDIT_USER_AGENT") or "duckclaw:share-resolve/0.1 (by duckclaw)").strip()
    t0 = time.perf_counter()
    try:
        req = _urllib_request.Request(raw, headers={"User-Agent": ua, "Accept": "text/html"})
        with _urllib_request.urlopen(req, timeout=timeout) as resp:
            raw_final = resp.geturl()
        if not isinstance(raw_final, str):
            _log.info(
                "reddit share resolve: sin URL final en %.2fs url=%r",
                time.perf_counter() - t0,
                raw[:80],
            )
            return None
        if not _reddit_trust_share_tracking_redirect() and _reddit_comments_url_has_share_tracking(
            raw_final
        ):
            _log.info(
                "reddit share resolve: redirect con tracking rechazado en %.2fs → reddit_search",
                time.perf_counter() - t0,
            )
            return None
        final = raw_final.split("#")[0].split("?")[0].rstrip("/")
        if not _REDDIT_COMMENTS_IN_URL_RE.search(final):
            _log.info(
                "reddit share resolve: sin /comments/ en %.2fs final=%r",
                time.perf_counter() - t0,
                raw_final[:96],
            )
            return None
        if not final.lower().startswith("http"):
            final = f"https://{final}"
        _log.info(
            "reddit share resolve: ok en %.2fs → %r",
            time.perf_counter() - t0,
            final[:96],
        )
        return final
    except Exception as exc:
        _log.info(
            "reddit share resolve: falló en %.2fs url=%r err=%s",
            time.perf_counter() - t0,
            raw[:80],
            exc,
        )
        return None


def _fetch_reddit_post_via_public_json(comments_url: str, *, timeout: float = 15.0) -> Optional[str]:
    """
    Obtiene un post vía API pública .json de Reddit (sin MCP).
    Devuelve JSON compacto compatible con format_reddit_mcp_reply_if_applicable.
    """
    sub, pid = _subreddit_and_post_id_from_reddit_comments_url(comments_url)
    if not sub or not pid:
        return None
    ua = (os.environ.get("REDDIT_USER_AGENT") or "duckclaw:public-json/0.1 (by duckclaw)").strip()
    api_url = f"https://www.reddit.com/r/{sub}/comments/{pid}/.json?raw_json=1"
    try:
        req = _urllib_request.Request(
            api_url,
            headers={"User-Agent": ua, "Accept": "application/json"},
        )
        with _urllib_request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
        data = json.loads(body)
        if not isinstance(data, list) or not data:
            return None
        listing = data[0] if isinstance(data[0], dict) else {}
        children = (listing.get("data") or {}).get("children") or []
        if not children or not isinstance(children[0], dict):
            return None
        post_data = children[0].get("data") or {}
        if not isinstance(post_data, dict):
            return None
        payload = {
            "success": True,
            "subreddit": sub,
            "posts": [
                {
                    "id": pid,
                    "title": post_data.get("title") or "",
                    "score": post_data.get("score"),
                    "permalink": post_data.get("permalink") or "",
                    "selftext": post_data.get("selftext") or "",
                    "is_self": bool(post_data.get("is_self")),
                    "url": post_data.get("url") or "",
                }
            ],
        }
        return json.dumps(payload, ensure_ascii=False)
    except Exception as exc:
        _log.info(
            "reddit public json fetch failed url=%r err=%s",
            (comments_url or "")[:80],
            exc,
        )
        return None


def _extract_first_reddit_url(text: str) -> Optional[str]:
    if not text or not str(text).strip():
        return None
    m = re.search(r"https?://(?:www\.)?reddit\.com/[^\s)>\]\"']+", str(text), re.IGNORECASE)
    if m:
        u = m.group(0)
        while u and u[-1] in ".,);":
            u = u[:-1]
        return u or None
    m2 = re.search(r"https?://redd\.it/[a-zA-Z0-9]+", str(text), re.IGNORECASE)
    return m2.group(0) if m2 else None


def _most_recent_reddit_url_in_human_messages(messages: list[Any]) -> Optional[str]:
    from langchain_core.messages import HumanMessage

    from duckclaw.integrations.llm_providers import lc_message_content_to_text

    for m in reversed(messages or []):
        if not isinstance(m, HumanMessage):
            continue
        txt = lc_message_content_to_text(m)
        u = _extract_first_reddit_url(txt)
        if u:
            return u
    return None


def _latest_human_index_with_reddit_share_url(messages: list[Any]) -> Optional[int]:
    """Índice (en `messages`, 0-based) del Human más reciente cuya URL Reddit es /r/…/s/… share."""
    from langchain_core.messages import HumanMessage

    from duckclaw.integrations.llm_providers import lc_message_content_to_text

    for i in range(len(messages or []) - 1, -1, -1):
        m = messages[i]
        if not isinstance(m, HumanMessage):
            continue
        txt = lc_message_content_to_text(m)
        u = _extract_first_reddit_url(txt)
        if u and _REDDIT_SHARE_PATH_RE.search(u):
            return i
    return None
