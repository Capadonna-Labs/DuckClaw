"""Optional per-turn pack router: asks a typed classifier which tool packs the turn needs.

Manifest (``tool_surface.runtime_packs.router``)::

    router:
      kind: jev                 # OpenRouter Decisions (typesafe/jev-*), one yes/no per pack
      threshold: 0.5            # probability to activate a pack
      timeout_sec: 4
      packs:                    # pack_id -> what it is for (the question Jev answers)
        research: "buscar noticias o información en internet"
        mcp_google_gmail: "leer, buscar o enviar correos de Gmail"

The router only adds packs on top of always/signals/sticky/unlocked ones; on any failure it adds
none and the agent can still call ``unlock_tool_pack``. Measured on 92 real turns (16-Nov-2026,
threshold 0.5): 0 misses for web/gmail/telegram, ~0.23 s and ~$0.00003 per turn.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Iterable

_log = logging.getLogger(__name__)


def router_config(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    r = (raw or {}).get("router")
    if not isinstance(r, dict) or str(r.get("kind") or "").strip().lower() != "jev":
        return None
    packs = r.get("packs")
    if not isinstance(packs, dict) or not packs:
        return None
    return r


@lru_cache(maxsize=256)
def _ask(intent: str, questions: tuple[tuple[str, str], ...], threshold: float, timeout: float, model: str) -> frozenset[str]:
    # ponytail: cached per (intent, questions) in-process; one call per turn even though the agent node
    # re-filters tools on every LLM round. Redis cache if several gateway workers ever share turns.
    from duckclaw.forge.skills.jev_decide_bridge import DEFAULT_JEV_MODEL, jev_decide_impl

    qs = {
        pid: {
            "type": "noul",
            "instructions": f"¿Para responder este mensaje hace falta {desc}?",
            "criteria": {"true": f"el mensaje pide o implica {desc}", "false": "no hace falta"},
        }
        for pid, desc in questions
    }
    res = json.loads(jev_decide_impl(intent, json.dumps(qs, ensure_ascii=False), model=model or DEFAULT_JEV_MODEL, timeout=timeout))
    if not res.get("ok"):
        raise RuntimeError(str(res.get("error") or "jev_failed"))
    answers = res.get("answers") or {}
    return frozenset(
        pid for pid, _ in questions
        if float((answers.get(pid) or {}).get("noul", 0) or 0) >= threshold
    )


def route_packs(raw: dict[str, Any] | None, intent: str, available_pack_ids: Iterable[str]) -> frozenset[str]:
    """Packs the router says this turn needs (subset of ``available_pack_ids``); empty on no router or failure."""
    r = router_config(raw)
    text = (intent or "").strip()
    if r is None or not text:
        return frozenset()
    available = set(available_pack_ids)
    questions = tuple(sorted((str(k), str(v)) for k, v in r["packs"].items() if str(k) in available and str(v).strip()))
    if not questions:
        return frozenset()
    try:
        return _ask(
            text[:6000],
            questions,
            float(r.get("threshold", 0.5)),
            float(r.get("timeout_sec", 4)),
            str(r.get("model") or ""),
        )
    except Exception as exc:  # noqa: BLE001  the router is an optimisation: never block the turn
        _log.warning("tool pack router failed, no packs added: %s", exc)
        return frozenset()
