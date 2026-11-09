"""Local-model fallback for an agent turn whose primary LLM is unreachable."""

from __future__ import annotations

import logging
from typing import Any

_log = logging.getLogger(__name__)

# Errors that mean "the cloud model is unreachable", not "the request was bad": only these switch to the local fallback.
_UNREACHABLE = ("connect", "timed out", "timeout", "name or service not known", "temporary failure in name resolution",
                "network is unreachable", "no route to host", "502", "503", "504")


def _invoke_offline_fallback(fallback: Any, bind_tools: Any, primary: Any, messages: Any, exc: BaseException, wl: str) -> Any:
    """Answer with the local model (DUCKCLAW_LLM_FALLBACK_* / DUCKCLAW_LOCAL_LLM_*) when the primary one is unreachable.

    Same tools as the primary call, so the turn keeps its permissions; the reply says it came from the local model. None when
    there is no fallback, the error is not a connectivity one, or the fallback fails too.
    """
    text = f"{type(exc).__name__} {exc}".lower()
    if fallback is None or not any(k in text for k in _UNREACHABLE):
        return None
    try:
        tools = (getattr(primary, "kwargs", None) or {}).get("tools") or []
        resp = (bind_tools(fallback, tools) if tools else fallback).invoke(messages)
    except Exception as fb_exc:  # noqa: BLE001
        _log.warning("[%s] local fallback failed too: %s", wl, fb_exc)
        return None
    _log.warning("[%s] primary LLM unreachable (%s): answered with the local fallback", wl, exc)
    if isinstance(getattr(resp, "content", None), str) and resp.content.strip() and not getattr(resp, "tool_calls", None):
        resp.content = resp.content.rstrip() + "\n\n_(Respuesta del modelo local: sin conexión con el modelo principal.)_"
    return resp
