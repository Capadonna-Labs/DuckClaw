"""Jev Decisions bridge — TypeSafe System One via OpenRouter Decisions API.

Not a chat model. Workers with skill ``jev_decide`` get a tool that POSTs
``state`` + typed ``questions`` to ``/api/alpha/decisions``.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from typing import Any, Optional

from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)

DEFAULT_JEV_MODEL = "typesafe/jev-1.13"
DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"
_ALLOWED_QUESTION_TYPES = frozenset({"noul", "choice", "score"})


class JevDecideInput(BaseModel):
    """Args schema for OpenAI-compatible tool calling."""

    state: str = Field(
        ...,
        description=(
            "Contenido a evaluar: texto plano, o JSON string de objeto/array "
            "(ticket, mensaje, contexto)."
        ),
    )
    questions_json: str = Field(
        ...,
        description=(
            "JSON object de preguntas Decisions. Cada valor: "
            '{"type":"noul"|"choice"|"score","instructions":"...","criteria":...}. '
            "noul criteria: {true,false}; choice: mapa label→desc; "
            "score: lista ordenada de rúbrica."
        ),
    )
    model: str = Field(
        default=DEFAULT_JEV_MODEL,
        description=f"Slug OpenRouter Decisions (default {DEFAULT_JEV_MODEL}).",
    )
    session_id: str = Field(
        default="",
        description="Opcional: agrupa requests relacionados (observabilidad).",
    )


def _parse_state(raw: str) -> Any:
    text = (raw or "").strip()
    if not text:
        return None
    if text[0] in "{[":
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text
    return text


def parse_and_validate_questions(questions_json: str) -> tuple[dict[str, Any] | None, str | None]:
    """Parse questions_json → (questions_dict, error_code)."""
    raw = (questions_json or "").strip()
    if not raw:
        return None, "questions_required"
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None, "questions_json_invalid"
    if not isinstance(parsed, dict) or not parsed:
        return None, "questions_must_be_nonempty_object"
    for key, q in parsed.items():
        name = str(key or "").strip()
        if not name:
            return None, "question_key_empty"
        if not isinstance(q, dict):
            return None, f"question_not_object:{name}"
        qtype = str(q.get("type") or "").strip().lower()
        if qtype not in _ALLOWED_QUESTION_TYPES:
            return None, f"question_type_invalid:{name}"
        instructions = str(q.get("instructions") or "").strip()
        if not instructions:
            return None, f"question_instructions_required:{name}"
        if "criteria" not in q:
            return None, f"question_criteria_required:{name}"
    return parsed, None


def jev_decide_impl(
    state: str,
    questions_json: str,
    model: str = DEFAULT_JEV_MODEL,
    session_id: str = "",
    *,
    db: Any | None = None,
    tenant_id: str = "default",
    urlopen: Any = None,
) -> str:
    """Call OpenRouter Decisions API; return compact JSON for the chat LLM."""
    parsed_state = _parse_state(state)
    if parsed_state is None or parsed_state == "":
        return json.dumps(
            {
                "ok": False,
                "error": "state_required",
                "hint": "Pasa state como texto o JSON string de objeto/array.",
            },
            ensure_ascii=False,
        )

    questions, qerr = parse_and_validate_questions(questions_json)
    if qerr or questions is None:
        return json.dumps(
            {
                "ok": False,
                "error": qerr or "questions_invalid",
                "hint": (
                    "questions_json debe ser un objeto JSON; cada pregunta con "
                    "type (noul|choice|score), instructions y criteria."
                ),
            },
            ensure_ascii=False,
        )

    from duckclaw.integrations.llm_providers import (
        OPENROUTER_ATTRIBUTION_HEADERS,
        normalize_openrouter_model_id,
    )
    from duckclaw.llm_bootstrap import resolve_llm_api_key

    key = resolve_llm_api_key(
        "openrouter",
        db=db,
        tenant_id=tenant_id,
    )
    if not key:
        return json.dumps(
            {
                "ok": False,
                "error": "missing_api_key:OPENROUTER_API_KEY",
                "message": (
                    "Falta OPENROUTER_API_KEY "
                    "(Admin → Integraciones → API keys o .env)."
                ),
            },
            ensure_ascii=False,
        )

    resolved_model = normalize_openrouter_model_id(model or DEFAULT_JEV_MODEL)
    if "/" not in resolved_model:
        resolved_model = DEFAULT_JEV_MODEL

    body: dict[str, Any] = {
        "model": resolved_model,
        "state": parsed_state,
        "questions": questions,
    }
    sid = str(session_id or "").strip()
    if sid:
        body["session_id"] = sid[:256]

    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        **dict(OPENROUTER_ATTRIBUTION_HEADERS),
    }
    req = urllib.request.Request(
        DECISIONS_URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    opener = urlopen or urllib.request.urlopen
    try:
        with opener(req, timeout=60) as resp:
            raw_body = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", None) or resp.getcode()
    except urllib.error.HTTPError as exc:
        err_body = ""
        try:
            err_body = exc.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            pass
        return json.dumps(
            {
                "ok": False,
                "error": f"http_{exc.code}",
                "message": err_body or str(exc.reason),
                "model": resolved_model,
            },
            ensure_ascii=False,
        )
    except Exception as exc:  # noqa: BLE001
        _log.warning("jev_decide request failed: %s", exc)
        return json.dumps(
            {
                "ok": False,
                "error": "request_failed",
                "message": str(exc)[:500],
                "model": resolved_model,
            },
            ensure_ascii=False,
        )

    try:
        payload = json.loads(raw_body) if raw_body else {}
    except json.JSONDecodeError:
        return json.dumps(
            {
                "ok": False,
                "error": "invalid_response_json",
                "status": status,
                "body_preview": raw_body[:400],
            },
            ensure_ascii=False,
        )

    if not isinstance(payload, dict):
        return json.dumps(
            {"ok": False, "error": "invalid_response_shape", "status": status},
            ensure_ascii=False,
        )

    answers = payload.get("answers")
    usage = payload.get("usage")
    return json.dumps(
        {
            "ok": True,
            "model": str(payload.get("model") or resolved_model),
            "id": payload.get("id"),
            "provider": payload.get("provider"),
            "answers": answers if isinstance(answers, dict) else answers,
            "usage": usage if isinstance(usage, dict) else usage,
        },
        ensure_ascii=False,
    )


def _jev_decide_tool(
    jev_config: Optional[dict] = None,
    *,
    db: Any | None = None,
    tenant_id: str = "default",
) -> Any | None:
    from langchain_core.tools import StructuredTool

    cfg = jev_config or {}
    if cfg.get("enabled") is False:
        return None
    default_model = str(cfg.get("model") or DEFAULT_JEV_MODEL).strip() or DEFAULT_JEV_MODEL

    def _run(
        state: str,
        questions_json: str,
        model: str = DEFAULT_JEV_MODEL,
        session_id: str = "",
    ) -> str:
        return jev_decide_impl(
            state,
            questions_json,
            model=model or default_model,
            session_id=session_id,
            db=db,
            tenant_id=tenant_id,
        )

    return StructuredTool.from_function(
        _run,
        name="jev_decide",
        description=(
            "[Jev/Decisions] Decide tipado (noul/choice/score) vía TypeSafe Jev en OpenRouter. "
            "NO genera texto de chat. Usa cuando necesitas clasificación, routing o verificación "
            "con probabilidades calibradas. Params: state, questions_json (JSON object), "
            f"model opcional (default {DEFAULT_JEV_MODEL}), session_id opcional."
        ),
        args_schema=JevDecideInput,
    )


def register_jev_decide_skill(
    tools_list: list[Any],
    jev_decide_config: Optional[dict] = None,
    *,
    db: Any | None = None,
    tenant_id: str = "default",
) -> None:
    """Append ``jev_decide`` when skill is configured on the worker."""
    if jev_decide_config is None:
        return
    try:
        tool = _jev_decide_tool(jev_decide_config, db=db, tenant_id=tenant_id)
        if tool:
            tools_list.append(tool)
    except Exception as exc:
        _log.warning("register_jev_decide_skill failed: %s", exc)
