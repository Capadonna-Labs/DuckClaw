"""
WorkerFactory: build a LangGraph instance from a worker template.

Input: worker_id, db_path, optional telegram_chat_id, instance_name.
Output: Compiled LangGraph with persistent state, ready for events.
"""

from __future__ import annotations

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import URLError
from urllib import request as _urllib_request
from urllib.parse import parse_qs, urlparse

_log = logging.getLogger(__name__)

from pathlib import Path
from typing import Any, Literal, Optional

from duckclaw.db_write_queue import enqueue_duckdb_write_sync, poll_task_status_sync
try:
    from langchain_core.runnables import RunnableConfig
except ImportError:
    RunnableConfig = Any  # type: ignore[misc, assignment]

from duckclaw.integrations.telegram import effective_telegram_bot_token_outbound
from duckclaw.utils.logger import format_chat_log_identity, log_tool_execution_sync, set_log_context
from duckclaw.utils.telegram_markdown_v2 import llm_markdown_to_telegram_html
from duckclaw.gateway_db import get_gateway_db_path
from duckclaw.guardrails.loader import load_guardrail
from duckclaw.prompt_policies import PromptPolicyResolver
from duckclaw.egress.tool_response_repair import (
    clock_only_lone_url_no_repair as _clock_only_lone_url_no_repair,
    deterministic_tool_response_summary as _deterministic_tool_response_summary,
    latest_tool_json_since as _latest_tool_json_since,
    parse_get_current_time_json as _parse_get_current_time_json,
    post_tools_synthesis_needed as _post_tools_synthesis_needed,
    repair_tool_response_egress_reply as _repair_tool_response_egress_reply,
    reply_is_get_current_time_json_only as _reply_is_get_current_time_json_only,
    reply_is_tool_json_echo as _reply_is_tool_json_echo,
    tool_response_needs_egress_repair as _tool_response_needs_egress_repair,
)
from duckclaw.workers import read_pool
from duckclaw.graphs.proactive_review_markers import proactive_review_event_phrase_in_text
from duckclaw.workers.discovery import list_workers
from duckclaw.workers.manifest import WorkerSpec, load_manifest
from duckclaw.workers.loader import append_domain_closure_block, load_system_prompt, load_skills
from duckclaw.forge.rag.prompt_policy import rag_turn_system_prompt
from duckclaw.forge.rag.tool_policy import should_prioritize_rag_over_storage_tools, without_storage_tools
from duckclaw.workers.runtime_policy_helpers import (
    worker_has_runtime_capability as _worker_has_runtime_capability,
    worker_runtime_capability_flag as _worker_runtime_capability_flag,
    worker_runtime_capability_policy as _worker_runtime_capability_policy,
    worker_runtime_policy as _worker_runtime_policy,
    worker_use_heuristic_first_tool as _worker_use_heuristic_first_tool,
)
from duckclaw.workers.visual_evidence_policy import (
    visual_evidence_max_retries as _visual_evidence_max_retries,
)
from duckclaw.workers.tool_output_truncation import (
    compact_run_sandbox_tool_content_for_llm as _compact_run_sandbox_tool_content_for_llm,
    truncate_tool_messages_for_llm as _truncate_tool_messages,
)
from duckclaw.workers.provider_input_budget import (
    apply_groq_message_budget as _apply_groq_message_budget,
    apply_mlx_message_budget as _apply_mlx_message_budget,
    apply_provider_input_budget as _apply_provider_input_budget,
    estimate_tokens_from_messages as _estimate_tokens_from_messages,
    groq_max_estimated_input_tokens as _groq_max_estimated_input_tokens,
    groq_tool_message_max_chars as _groq_tool_message_max_chars,
    mlx_max_estimated_input_tokens as _mlx_max_estimated_input_tokens,
    mlx_tool_message_max_chars as _mlx_tool_message_max_chars,
    normalized_context_pruning as _normalized_context_pruning,
    split_for_pruning as _split_for_pruning,
    trim_messages_to_estimated_cap as _trim_messages_to_estimated_cap,
)
from duckclaw.workers.context_monitor import (
    build_context_monitor_node as _build_context_monitor_node,
    build_summary_llm as _build_summary_llm,
    compose_context_summary_prompt as _compose_context_summary_prompt,
    llm_fold_conversation_summary as _llm_fold_conversation_summary,
    serialize_messages_for_summary as _serialize_messages_for_summary,
)
from duckclaw.workers.tool_invocation_policy import (
    decide_current_time_tool_invocation as _decide_current_time_tool_invocation,
    decide_db_first_tool_invocation as _decide_db_first_tool_invocation,
    decide_market_data_tool_invocation as _decide_market_data_tool_invocation,
)

from duckclaw.workers.identity import load_worker_runtime_policy
from duckclaw.workers.db_intent_policy import (
    TABLE_CONTENT_PHRASE as _TABLE_CONTENT_PHRASE,
    explicit_duckdb_schema_request,
    incoming_is_manager_planned_guardrail_task,
    incoming_is_schema_query_heuristic,
    incoming_is_table_content_query as _incoming_is_table_content_query,
    is_no_task as _is_no_task,
)
from duckclaw.workers.db_runtime import (
    RUN_SANDBOX_TOOL_LLM_MAX_CHARS as _RUN_SANDBOX_TOOL_LLM_MAX_CHARS,
    apply_forge_attaches as _apply_forge_attaches,
    bootstrap_shared_main_schema as _bootstrap_shared_main_schema,
    get_db_path as _get_db_path,
    infer_user_id_for_writer as _infer_user_id_for_writer,
    resolve_shared_db_path as _resolve_shared_db_path,
    same_duckdb_file as _same_duckdb_file,
    truncate_read_sql_result_for_llm as _truncate_read_sql_result_for_llm,
)

def _raise_if_chat_cancelled_from_state(state: dict) -> None:
    from duckclaw.graphs.chat_cancel import raise_if_chat_cancelled

    cid = str(state.get("chat_id") or state.get("session_id") or "").strip()
    if cid:
        raise_if_chat_cancelled(cid)




    # endregion



# Debe coincidir con duckclaw.graphs.manager_graph._LONE_HTTP_URL_ONLY_LINE.



# Preguntas por filas/contenido (no catálogo). Incluye «hay algo en la tabla X» (evita confundir con listar tablas).










# Preguntas sobre DB/tablas/esquema son siempre tarea concreta (evitar "¿Cuál es mi tarea?")

# read_sql sobre read_json_auto sin LIMIT puede devolver megabytes y saturar el contexto del LLM.

# run_sandbox puede volcar cientos de KB; sin context_monitor el ToolMessage iría entero al LLM.

# Tarea explícita del manager (plan): nunca tratar como "sin tarea"
def _worker_log_label(worker_id: str) -> str:
    """Etiqueta corta solo para texto de log (no sustituye el id real del estado)."""
    w = (worker_id or "").strip()
    return w or "worker"






































def _duckclaw_env_truthy(name: str) -> bool:
    v = (os.environ.get(name) or "").strip().lower()
    return v in ("1", "true", "yes", "on")




















































































def _spec_logical_worker_id(spec: Any) -> str:
    return (getattr(spec, "logical_worker_id", None) or getattr(spec, "worker_id", "") or "").strip()


















def _last_human_message_index(messages: list[Any]) -> int:
    from langchain_core.messages import HumanMessage

    for idx in range(len(messages or []) - 1, -1, -1):
        if isinstance(messages[idx], HumanMessage):
            return idx
    return -1


def _tool_called_since(messages: list[Any], last_human_idx: int, tool_name: str) -> bool:
    from langchain_core.messages import ToolMessage

    if not tool_name:
        return False
    for msg in (messages or [])[max(0, last_human_idx + 1) :]:
        if isinstance(msg, ToolMessage) and (getattr(msg, "name", "") or "") == tool_name:
            return True
    return False


def _parse_comfyui_edit_inbound(incoming: str) -> dict[str, str] | None:
    """Compat wrapper for admin/Telegram inbound visual-edit payloads."""
    s = (incoming or "").strip()
    if "[COMFYUI_EDIT" not in s:
        return None
    m = _COMFYUI_EDIT_PATH_RE.search(s)
    if not m:
        return None
    source_path = m.group(1).strip()
    if not source_path:
        return None
    cap_m = re.search(r"Instrucciones:\s*«([^»]+)»", s)
    edit_prompt = cap_m.group(1).strip() if cap_m else ""
    if not edit_prompt:
        for line in s.splitlines():
            low = line.lower()
            if low.startswith("usuario dice:"):
                edit_prompt = line.split(":", 1)[-1].strip()
                break
    if not edit_prompt:
        edit_prompt = s[:500]
    return {"source_image_path": source_path, "edit_prompt": edit_prompt[:500]}

_TASK_AWARENESS_PROMPT = load_guardrail("prompts", "task_awareness_default")
















def _identity_fields(state: dict) -> dict:
    return {
        "chat_id": state.get("chat_id") or state.get("session_id"),
        "tenant_id": state.get("tenant_id") or "default",
        "user_id": state.get("user_id") or "",
        "username": (state.get("username") or "").strip(),
        "vault_db_path": state.get("vault_db_path") or "",
    }


def _groq_tools_without_reddit_for_bind(tools: list[Any]) -> list[Any]:
    """
    Groq tier on_demand (~12k TPM por petición) cuenta mensajes + **definiciones de tools**.
    El MCP de Reddit registra muchas herramientas; en rutas genéricas (p. ej. presupuestos) no hacen falta
    y empujan el request por encima del límite. Las rutas forzadas Reddit siguen ligando el set completo.
    """
    return [t for t in (tools or []) if not str(getattr(t, "name", None) or "").startswith("reddit_")]


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
_COMFYUI_EDIT_PATH_RE = re.compile(
    r"\[COMFYUI_EDIT\s+source_image_path=([^\]]+)\]",
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


def _latest_human_index_with_vlm_visual_markers(messages: list[Any]) -> Optional[int]:
    """Human más reciente con payload VLM (mismo marcador que el gateway al Multimodal)."""
    from langchain_core.messages import HumanMessage

    from duckclaw.integrations.llm_providers import lc_message_content_to_text

    for i in range(len(messages or []) - 1, -1, -1):
        m = messages[i]
        if not isinstance(m, HumanMessage):
            continue
        txt = lc_message_content_to_text(m) or ""
        if "[VLM_CONTEXT" in txt or "Contexto visual adjunto:" in txt:
            return i
    return None






def _visual_asset_calls_since_last_human(messages: list[Any]) -> int:
    """Cuántas veces se invocó generate_visual_asset desde el último HumanMessage."""
    from langchain_core.messages import HumanMessage, ToolMessage

    count = 0
    for msg in reversed(messages or []):
        if isinstance(msg, HumanMessage):
            break
        if isinstance(msg, ToolMessage) and (getattr(msg, "name", "") or "") == "generate_visual_asset":
            count += 1
    return count










def _agent_node_llm_failure_user_message(exc: BaseException, *, provider: str) -> str:
    """Mensaje Telegram cuando falla invoke del LLM en agent_node (sin culpar a MLX si el proveedor es Groq)."""
    pl = (provider or "").strip().lower()
    raw = str(exc)
    low = raw.lower()
    mlx_hint = load_guardrail("errors", "llm_failure_mlx")
    groq_tokens_hint = load_guardrail("errors", "llm_failure_groq_tpm")
    is_groq_size_or_tpm = (
        "413" in raw
        or "rate_limit_exceeded" in low
        or "tokens per minute" in low
        or "request too large" in low
        or "too large for model" in low
    )
    if pl == "groq" and is_groq_size_or_tpm:
        return groq_tokens_hint
    detail = raw[:380] + ("…" if len(raw) > 380 else "")
    if pl == "groq":
        return load_guardrail("errors", "llm_failure_groq_generic").format(detail=detail)
    if pl == "deepseek":
        return load_guardrail("errors", "llm_failure_deepseek").format(detail=detail)
    if pl == "openai":
        return load_guardrail("errors", "llm_failure_openai").format(detail=detail)
    if pl == "openrouter" and ("402" in raw or "payment required" in low or "more credits" in low):
        return (
            "OpenRouter rechazó la petición (créditos insuficientes o `max_tokens` demasiado alto). "
            "Opciones: añade créditos en openrouter.ai/settings/credits, usa DeepSeek/Groq en el selector, "
            "o baja `DUCKCLAW_OPENROUTER_MAX_OUTPUT_TOKENS` (p. ej. 2048). "
            f"Detalle: {detail}"
        )
    if pl in ("mlx", "iotcorelabs"):
        return mlx_hint
    return load_guardrail("errors", "llm_failure_generic").format(detail=detail)


def _sandbox_heartbeat_allowed(spec: WorkerSpec) -> bool:
    cp = _normalized_context_pruning(spec)
    if not cp.get("sandbox_heartbeat"):
        return False
    v = (os.getenv("DUCKCLAW_SANDBOX_HEARTBEAT", "true").strip().lower())
    if v in ("0", "false", "no", "off"):
        return False
    return bool(effective_telegram_bot_token_outbound())


def _heartbeat_elapsed_sec(state: dict) -> float | None:
    t0 = state.get("subagent_turn_started_monotonic")
    if not isinstance(t0, (int, float)):
        return None
    return max(0.0, time.monotonic() - float(t0))


def _send_sandbox_heartbeat_telegram(state: dict) -> None:
    from duckclaw.graphs.chat_heartbeat import (
        format_tool_heartbeat,
        is_admin_ui_chat_session,
        normalize_telegram_chat_id_for_outbound,
    )

    cid_raw = str(state.get("chat_id") or state.get("session_id") or "").strip()
    if is_admin_ui_chat_session(cid_raw):
        return
    cid = normalize_telegram_chat_id_for_outbound(cid_raw) or cid_raw
    uid = str(state.get("user_id") or "").strip() or cid
    if not cid:
        return
    _hb = (state.get("subagent_instance_label") or "").strip() or None
    _pt = (state.get("heartbeat_plan_title") or "").strip() or None
    text = format_tool_heartbeat(
        _hb,
        "📊 Estoy procesando los datos y generando tus gráficos. "
        "Esto puede tomar unos segundos...",
        plan_title=_pt,
        elapsed_sec=_heartbeat_elapsed_sec(state),
    )
    token = effective_telegram_bot_token_outbound()
    if token:
        try:
            from duckclaw.integrations.telegram.telegram_outbound_sync import (
                send_long_plain_text_markdown_v2_chunks_sync,
            )

            n = send_long_plain_text_markdown_v2_chunks_sync(
                bot_token=token,
                chat_id=cid,
                plain_text=text,
                log=_log,
            )
            if n > 0:
                _log.info("sandbox heartbeat: nativo OK chat_id=%r", cid)
                return
        except Exception as exc:
            _log.debug("sandbox heartbeat nativo falló: %s", exc)
    _log.debug("sandbox heartbeat: sin token Bot API para chat_id=%r", cid)


def _novnc_pre_dm_always_enabled() -> bool:
    v = (os.getenv("DUCKCLAW_BROWSER_NOVNC_PRE_DM") or "").strip().lower()
    return v in ("1", "true", "yes", "on", "always")


def _send_novnc_pre_dm_fallback(
    state: dict,
    vnc_url: str,
    *,
    routing_worker_id: str,
    novnc_session_id: str = "",
) -> None:
    """DM corto con enlace si heartbeat de chat está off y ``DUCKCLAW_BROWSER_NOVNC_PRE_DM=always``."""
    import threading

    from duckclaw.graphs.chat_heartbeat import (
        _resolve_heartbeat_outbound_bot_token,
        normalize_telegram_chat_id_for_outbound,
    )
    from duckclaw.graphs import novnc_registry as nr  # noqa: PLC0415
    from duckclaw.integrations.telegram.telegram_outbound_sync import (
        send_long_plain_text_markdown_v2_chunks_sync,
    )

    cid_raw = str(state.get("chat_id") or state.get("session_id") or "").strip()
    cid = normalize_telegram_chat_id_for_outbound(cid_raw) or cid_raw
    if not cid or not vnc_url:
        return
    _ns = (novnc_session_id or "").strip()
    if _ns and not nr.consume_initial_vnc_telegram_link(_ns):
        return
    tok_ex = (state.get("outbound_telegram_bot_token") or "").strip() or None
    token = _resolve_heartbeat_outbound_bot_token(
        tok_ex,
        (routing_worker_id or "").strip() or None,
    )
    if not token:
        _log.debug("novnc pre-dm: sin token Bot API")
        return
    plain = (
        "🖥️ NoVNC (sandbox browser)\n\n"
        f"{vnc_url}\n\n"
        "🌐 El agente ejecutará la automatización en el sandbox."
    )

    def _run() -> None:
        try:
            n = send_long_plain_text_markdown_v2_chunks_sync(
                bot_token=token,
                chat_id=cid,
                plain_text=plain,
                log=_log,
            )
            if n > 0:
                _log.info("novnc pre-dm fallback: nativo OK chat_id=%r", cid)
        except Exception as exc:
            _log.debug("novnc pre-dm fallback failed: %s", exc)

    threading.Thread(target=_run, name="duckclaw-novnc-pre-dm", daemon=True).start()


def _schedule_run_browser_novnc_tool_heartbeat(
    state: dict,
    *,
    routing_worker_id: str,
    vnc_url: str | None,
    novnc_session_id: str = "",
) -> None:
    from duckclaw.graphs import novnc_registry as nr  # noqa: PLC0415
    from duckclaw.graphs.chat_heartbeat import (
        format_tool_heartbeat,
        heartbeat_message_for_tool,
        is_admin_ui_chat_session,
        is_chat_heartbeat_enabled,
        schedule_chat_heartbeat_dm,
    )

    _hcid = str(state.get("chat_id") or state.get("session_id") or "").strip()
    if is_admin_ui_chat_session(_hcid):
        # Admin SSE: publish_admin_tool_event (vía _schedule_tool_heartbeat) ya cubre start/done.
        return

    _hb_head = (state.get("subagent_instance_label") or "").strip() or None
    _hb_uname = (state.get("username") or "").strip() or None
    _hb_plan = (state.get("heartbeat_plan_title") or "").strip() or None
    _hb_tok = (state.get("outbound_telegram_bot_token") or "").strip() or None
    _htid = (state.get("tenant_id") or "default").strip() or "default"
    _huid = str(state.get("user_id") or "").strip() or _hcid

    _ns = (novnc_session_id or "").strip()
    _hb_on = is_chat_heartbeat_enabled(_htid, _hcid)

    if vnc_url:
        if _hb_on:
            _include_link = nr.consume_initial_vnc_telegram_link(_ns) if _ns else True
            if _include_link:
                body = (
                    "🖥️ Enlace noVNC (pantalla del navegador en vivo):\n"
                    f"{vnc_url}\n\n"
                    "🌐 El agente ejecutará ahora la automatización en el sandbox; puedes seguirla en este enlace."
                )
            else:
                body = (
                    "🌐 Automatización del sandbox en curso. "
                    "El enlace noVNC ya se envió al inicio de esta sesión; si lo necesitas otra vez, "
                    "pide «enlace noVNC» o usa la herramienta get_browser_session_url."
                )
        else:
            body = heartbeat_message_for_tool("run_browser_sandbox")
    else:
        body = heartbeat_message_for_tool("run_browser_sandbox")

    _elapsed = _heartbeat_elapsed_sec(state)
    text = format_tool_heartbeat(
        _hb_head,
        body,
        plan_title=_hb_plan,
        elapsed_sec=_elapsed,
    )

    if _hb_on:
        schedule_chat_heartbeat_dm(
            _htid,
            _hcid,
            _huid,
            text,
            log_worker_id=_hb_head,
            log_username=_hb_uname,
            log_plan_title=_hb_plan,
            outbound_bot_token=_hb_tok,
            routing_worker_id=routing_worker_id,
        )
    elif vnc_url and _novnc_pre_dm_always_enabled():
        _send_novnc_pre_dm_fallback(
            state,
            vnc_url,
            routing_worker_id=routing_worker_id,
            novnc_session_id=_ns,
        )


def _ensure_worker_duckdb_extensions(db: Any, spec: WorkerSpec) -> None:
    """INSTALL/LOAD extensiones declaradas en manifest (p. ej. httpfs + json para APIs remotas)."""
    exts = getattr(spec, "duckdb_extensions", None) or []
    if not exts:
        return
    for raw in exts:
        ext = str(raw).strip().lower()
        if not ext or not re.match(r"^[a-z][a-z0-9_]*$", ext):
            continue
        try:
            db.execute(f"INSTALL {ext};")
        except Exception:
            pass
        try:
            db.execute(f"LOAD {ext};")
        except Exception:
            pass


def _build_worker_tools(db: Any, spec: WorkerSpec) -> list:
    """Build tool list: template skills + read/admin SQL (with allow-list)."""
    from langchain_core.tools import StructuredTool

    tools = load_skills(spec, db)
    schema = spec.schema_name

    # TimeContextSkill: si el manifest declara get_current_time o time_context, añadir la tool
    skills_list = getattr(spec, "skills_list", None) or []
    if "get_current_time" in skills_list or "time_context" in skills_list:
        try:
            from duckclaw.forge.skills.time_context import get_current_time
            tools.append(get_current_time)
        except Exception:
            pass

    def _enforce_allowed_tables(q_upper: str) -> Optional[json]:
        """Allow-list validation for queries touching DB tables."""
        if not spec.allowed_tables:
            return None
        # Permitir siempre information_schema (SHOW TABLES, esquema, etc.)
        if "INFORMATION_SCHEMA" in q_upper or "SHOW TABLES" in q_upper or "SHOW " in q_upper:
            return None
        for t in spec.allowed_tables:
            t_str = str(t)
            if t_str.upper() in q_upper or f"{schema}.{t_str}".upper() in q_upper:
                return None
        # No allowed table mentioned; check if query likely touches tables.
        if any(k in q_upper for k in ("FROM", "INTO", "UPDATE", "DELETE", "JOIN", "TABLE")):
            return json.dumps({"error": f"Solo se permiten las tablas: {', '.join(spec.allowed_tables)}."})
        return None

    def _qualify_allowed_tables(query: str, schema_name: str) -> str:
        """
        Prefix allowed table names with schema when unqualified.
        Example: FROM my_table -> FROM main.my_table
        """
        if not spec.allowed_tables:
            return query
        out = query
        for table in spec.allowed_tables:
            if "." in str(table):
                continue
            escaped = re.escape(table)
            # Replace only unqualified names (not already schema.table)
            out = re.sub(rf"(?<!\.)\b{escaped}\b", f"{schema_name}.{table}", out, flags=re.IGNORECASE)
        return out

    def _read_sql_worker(query: str) -> str:
        return read_pool.run_worker_read_sql(lambda qq: db.query(qq), spec, query)

    _read_sql_worker = log_tool_execution_sync(name="read_sql")(_read_sql_worker)

    tools.append(
        StructuredTool.from_function(
            _read_sql_worker,
            name="read_sql",
            description="Solo lectura SQL. SELECT/WITH/SHOW/DESCRIBE/EXPLAIN/PRAGMA. Restringe a tablas permitidas del worker.",
        )
    )

    def _admin_sql_worker(query: str) -> str:
        if not query or not query.strip():
            return json.dumps({"error": "Query vacío."})
        q = query.strip()
        upper = q.upper()

        allowed_tables_error = _enforce_allowed_tables(upper)
        if allowed_tables_error:
            return allowed_tables_error

        # Respetar read_only del worker para operaciones destructivas/escrituras.
        if spec.read_only and any(
            kw in upper
            for kw in ("INSERT", "UPDATE", "DELETE", "DROP", "CREATE", "ALTER", "TRUNCATE")
        ):
            return json.dumps({"error": "Este trabajador es solo lectura. No se permiten escrituras."})

        try:
            # Para cualquier query de lectura, usar query()
            if upper.startswith(("SELECT", "WITH", "SHOW", "DESCRIBE", "EXPLAIN", "PRAGMA")):
                return db.query(q)

            # Escrituras: cola singleton (workers RO) o ejecución en proceso (workers RW).
            db_path_str = str(getattr(db, "_path", "") or "").strip()
            if not db_path_str:
                return json.dumps({"error": "Sin ruta de base de datos para encolar escritura."})
            ro = bool(getattr(db, "_read_only", False))
            # Worker RW: este proceso ya mantiene ``duckdb.connect(..., read_only=False)`` al archivo.
            # Encolar un segundo RW en db-writer falla con lock en el mismo PID (gateway); ver logs db-writer.
            # Alineado con ``insert_transaction``: mutar en el handle actual.
            if not ro and db_path_str != ":memory:":
                try:
                    db.execute(q)
                    return json.dumps({"status": "success"})
                except Exception as e:
                    return json.dumps({"error": str(e)})

            released_ro = False
            st = None
            try:
                # DuckDB: un handle RO en el gateway puede impedir que db-writer tome lock RW;
                # suspender antes de encolar.
                if ro and db_path_str != ":memory:":
                    susp = getattr(db, "suspend_readonly_file_handle", None)
                    resu = getattr(db, "resume_readonly_file_handle", None)
                    if callable(susp) and callable(resu):
                        susp()
                        released_ro = True
                resolved = str(Path(db_path_str).expanduser().resolve())
                uid = _infer_user_id_for_writer(resolved)
                task_id = enqueue_duckdb_write_sync(
                    db_path=resolved,
                    query=q,
                    user_id=uid,
                    tenant_id="default",
                )
                _poll = 15.0 if released_ro else 3.0
                st = poll_task_status_sync(task_id, timeout_sec=_poll)
            except Exception as e:
                return json.dumps({"error": str(e)})
            finally:
                if released_ro:
                    try:
                        resu = getattr(db, "resume_readonly_file_handle", None)
                        if callable(resu):
                            resu()
                    except Exception:
                        pass
            if st is not None and st.status == "success":
                return json.dumps({"status": "success"})
            if st is not None and st.status == "failed":
                return json.dumps({"status": "failed", "detail": st.detail or "writer failed"})
            return json.dumps({"status": "enqueued_pending_confirmation"})
        except Exception as e:
            return json.dumps({"error": str(e)})

    if not spec.read_only:
        tools.append(
            StructuredTool.from_function(
                _admin_sql_worker,
                name="admin_sql",
                description="SQL con permisos admin: lectura + escrituras (INSERT/UPDATE/DELETE/CREATE/ALTER/DROP si el worker no es read_only). Respeta allow-list de tablas del worker si aplica.",
            )
        )

    def _inspect_schema_worker() -> str:
        """Lista tablas de todos los esquemas disponibles para el worker."""
        return read_pool.run_inspect_schema_worker(lambda qq: db.query(qq))

    tools.append(
        StructuredTool.from_function(
            _inspect_schema_worker,
            name="inspect_schema",
            description="Lista las tablas disponibles en la base de datos. Usar para preguntas sobre tablas, esquema o estructura.",
        )
    )

    from duckclaw.graphs.tools import get_db_path as _get_db_path_tool

    def _get_db_path_worker() -> str:
        return _get_db_path_tool(db)

    tools.append(
        StructuredTool.from_function(
            _get_db_path_worker,
            name="get_db_path",
            description="Devuelve la ruta o nombre del archivo .duckdb al que tiene acceso el agente. Usar cuando pregunten por el nombre de la base de datos.",
        )
    )
    return tools


def filter_tools_for_sandbox(tools: list[Any], enabled: bool) -> list[Any]:
    """
    Helper (unit-testable): si sandbox está OFF, elimina `run_sandbox`, `run_browser_sandbox` y `get_browser_session_url`.
    """
    if enabled:
        return list(tools)
    deny = {
        "run_sandbox",
        "run_browser_sandbox",
        "get_browser_session_url",
    }
    return [t for t in tools if getattr(t, "name", "") not in deny]


class WorkerFactory:
    """Factory for Virtual Workers (template-based LangGraph agents)."""

    def __init__(self, templates_root: Optional[Path] = None):
        self.templates_root = templates_root

    def create(
        self,
        worker_id: str,
        db_path: Optional[str] = None,
        telegram_chat_id: Optional[str] = None,
        instance_name: Optional[str] = None,
        llm_provider: Optional[str] = None,
        llm_model: Optional[str] = None,
        llm_base_url: Optional[str] = None,
        shared_db_path: Optional[str] = None,
    ) -> Any:
        """
        Build and return a compiled LangGraph for the worker.
        Shim: delega a build_worker_graph (compatible con AgentAssembler).
        """
        return build_worker_graph(
            worker_id,
            db_path,
            None,
            templates_root=self.templates_root,
            instance_name=instance_name,
            llm_provider=llm_provider,
            llm_model=llm_model,
            llm_base_url=llm_base_url,
            shared_db_path=shared_db_path,
            tool_surface="full",
        )


def build_worker_graph(
    worker_id: str,
    db_path: Optional[str],
    llm: Optional[Any],
    *,
    templates_root: Optional[Path] = None,
    instance_name: Optional[str] = None,
    llm_provider: Optional[str] = None,
    llm_model: Optional[str] = None,
    llm_base_url: Optional[str] = None,
    shared_db_path: Optional[str] = None,
    reuse_db: Any | None = None,
    tool_surface: Literal["full", "context_synthesis", "visual_generation", "url_research"] = "full",
    incoming_hint: str | None = None,
    open_vault_read_only: bool = False,
    db: Any | None = None,
    tenant_id: str = "default",
) -> Any:
    """
    Build a compiled LangGraph for a worker. Used by AgentAssembler._build_worker
    and by WorkerFactory.create() (shim).

    Si ``reuse_db`` apunta al mismo archivo que ``path``, **no** está en solo lectura,
    y el worker **no** necesita catálogo ``shared`` (``shared_resolved`` vacío), reutiliza
    esa conexión y omite ATTACH del privado para no duplicar handles. Si ``reuse_db`` es RO
    (manager/gateway típico) **no** reutilizar: abrir ``DuckClaw(path, read_only=spec.read_only)``
    para que workers con ``read_only: false`` puedan ejecutar sus mutaciones declaradas.
    Si hace falta ``shared``, se abre otra conexión para no pisar el estado ATTACH entre
    workers distintos en caché.

    ``tool_surface=context_synthesis``: turnos con directivas ``SUMMARIZE_*`` del gateway;
    omite bridges MCP stdio pesados para reducir cold start.
    **Reddit** sí se registra si el manifest lo declara: URLs ``/r/.../s/...`` en
    ``SUMMARIZE_NEW_CONTEXT`` deben poder usar ``reddit_get_post`` / ``reddit_search_reddit``.

    ``tool_surface=visual_generation``: omite bridges MCP stdio pesados y Reddit
    (cold start ~2 min) y delega en ``generate_visual_asset`` si el worker lo declara.

    ``tool_surface=url_research``: mensaje solo URL; omite bridges MCP stdio pesados.
    Reddit MCP solo si ``incoming_hint`` contiene ``reddit.com`` (lazy por dominio, no cold start ~3 min).

    ``open_vault_read_only``: para ``SUMMARIZE_NEW_CONTEXT`` / ``SUMMARIZE_STORED_CONTEXT`` el worker no debe
    escribir en la bóveda (spec Context Injection). Abrir RW compite con el **db-writer** cuando éste inserta
    contexto vía cola en el mismo ``.duckdb``; DuckDB permite **solo lectura** concurrente con otro proceso en RW.

    Si ``db`` se proporciona, el WorkerSpec se carga desde el DB catalog
    (``admin_worker_catalog``) en lugar del filesystem ``forge/templates/``.
    """
    spec = load_manifest(worker_id, templates_root, db=db, tenant_id=tenant_id)
    if db is not None:
        try:
            spec.runtime_policy = load_worker_runtime_policy(
                db,
                getattr(spec, "logical_worker_id", None) or worker_id,
                tenant_id=tenant_id,
            )
        except Exception as exc:
            _log.debug("worker runtime policy unavailable for %s: %s", worker_id, exc)
    is_market_analysis_worker = _worker_has_runtime_capability(spec, "market_analysis")
    path = _get_db_path(worker_id, instance_name, db_path)
    shared_resolved = _resolve_shared_db_path(spec, shared_db_path)

    from duckclaw import DuckClaw

    reuse_path = ""
    if reuse_db is not None:
        reuse_path = str(getattr(reuse_db, "_path", "") or "").strip()
    reuse_read_only = bool(getattr(reuse_db, "_read_only", False)) if reuse_db is not None else False
    same_as_reuse = bool(reuse_db is not None and reuse_path and _same_duckdb_file(reuse_path, path))
    effective_vault_ro = bool(spec.read_only) or bool(open_vault_read_only)
    if same_as_reuse and not (shared_resolved or "").strip() and not open_vault_read_only:
        db = reuse_db
        _log.debug(
            "build_worker_graph: reuse DuckClaw (same file) path=%s ro=%s",
            path, reuse_read_only,
        )
    else:
        # Motor Python para RW en archivo: el manager ya abrió RO con duckdb Python; mezclar bridge C++ (auto)
        # + Python en el mismo .duckdb en un PID provoca «different configuration».
        _engine: Literal["auto", "python"] = (
            "python"
            if not effective_vault_ro and (path or "").strip() not in ("", ":memory:")
            else "auto"
        )
        db = DuckClaw(path, read_only=effective_vault_ro, engine=_engine)
    # DuckDB no permite dos conexiones con config distinta al mismo archivo en el mismo PID.
    # Si ya tenemos una conexión (reuse_db) al mismo path, reusarla sin abrir otra.
    db_open_path = str(getattr(db, "_path", "") or path or "").strip()
    vault_path_for_attach = str(path or "").strip()
    same_as_attached = _same_duckdb_file(db_open_path, vault_path_for_attach)
    skip_private_attach = same_as_reuse or same_as_attached
    if same_as_attached:
        _log.debug(
            "build_worker_graph: vault path == db path, skip ATTACH. path=%s",
            path,
        )
    _apply_forge_attaches(
        db,
        path,
        shared_resolved,
        private_attach_read_only=effective_vault_ro,
        shared_attach_read_only=True,
        skip_private_attach=skip_private_attach,
    )
    prompt_policies = PromptPolicyResolver(db=db)

    system_prompt = load_system_prompt(spec)
    tools = _build_worker_tools(db, spec)
    _hint_low = (incoming_hint or "").strip().lower()
    _register_trends = tool_surface == "full"
    # Reddit MCP (npx cold start ~2–3 min): solo cuando el turno lo necesita, no en cada full.
    _register_reddit = bool(getattr(spec, "reddit_config", None)) and (
        tool_surface == "context_synthesis"
        or (tool_surface == "url_research" and "reddit.com" in _hint_low)
        or (tool_surface == "full" and "reddit.com" in _hint_low)
    )
    if _register_trends and getattr(spec, "google_trends_config", None) is not None:
        try:
            from duckclaw.forge.skills.google_trends_bridge import register_google_trends_skill

            register_google_trends_skill(tools, spec.google_trends_config)
        except Exception:
            pass
    # Reddit: SUMMARIZE_NEW_CONTEXT con URL /r/.../s/...; url_research solo si dominio reddit.com.
    if _register_reddit and getattr(spec, "reddit_config", None):
        try:
            from duckclaw.forge.skills.reddit_bridge import register_reddit_skill

            register_reddit_skill(tools, spec.reddit_config)
        except Exception:
            pass
    tools_by_name = {t.name: t for t in tools}

    # Inferencia Elástica (Hardware-Aware): si el manifest tiene inference y no se pasó provider/model/base_url explícito, detectar hardware
    inference_config = getattr(spec, "inference_config", None)
    if inference_config is not None and not llm_provider and not llm_model and not llm_base_url:
        try:
            from duckclaw.integrations.hardware_detector import (
                get_inference_config,
                resolve_llm_params_from_config,
            )
            config = get_inference_config(inference_config)
            provider, model, base_url = resolve_llm_params_from_config(config)
            provider = (provider or "none_llm").strip().lower()
            model = (model or "").strip()
            base_url = (base_url or "").strip()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning("Hardware detection failed or fallback disabled: %s", e)
            provider = "none_llm"
            model = ""
            base_url = ""
    else:
        provider = (llm_provider or os.environ.get("DUCKCLAW_LLM_PROVIDER") or "none_llm").strip().lower()
        model = (llm_model or os.environ.get("DUCKCLAW_LLM_MODEL") or "").strip()
        base_url = (llm_base_url or os.environ.get("DUCKCLAW_LLM_BASE_URL") or "").strip()

    if llm is None and provider != "none_llm":
        from duckclaw.integrations.llm_providers import build_llm

        llm = build_llm(provider, model, base_url)
    elif llm is None:
        llm = None

    if llm is not None:
        from duckclaw.integrations.llm_providers import reconcile_worker_provider_label

        provider = reconcile_worker_provider_label(llm, provider, llm_provider)

    llm_fallback: Any | None = None
    if llm is not None:
        try:
            from duckclaw.integrations.llm_providers import build_llm_fallback_from_env

            llm_fallback = build_llm_fallback_from_env()
        except Exception as _fb_exc:
            _log.debug("LLM fallback skipped: %s", _fb_exc)

    _cp_early = _normalized_context_pruning(spec)
    llm_summary: Any = None
    if llm is not None and _cp_early.get("enabled"):
        llm_summary = _build_summary_llm(llm, provider=provider, model=model, base_url=base_url)

    if getattr(spec, "research_config", None):
        try:
            from duckclaw.forge.skills.research_bridge import register_research_skill
            register_research_skill(tools, spec.research_config, llm=llm)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            pass

    if getattr(spec, "openweather_config", None) is not None:
        try:
            from duckclaw.forge.skills.openweather_bridge import register_openweather_skill

            register_openweather_skill(tools, spec.openweather_config, getattr(spec, "research_config", None))
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            pass

    if getattr(spec, "tailscale_config", None):
        try:
            from duckclaw.forge.skills.tailscale_bridge import register_tailscale_skill
            register_tailscale_skill(tools, spec.tailscale_config)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            pass

    if getattr(spec, "fmp_config", None) is not None:
        try:
            from duckclaw.forge.skills.fmp_bridge import register_fmp_skill

            register_fmp_skill(tools, spec.fmp_config)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            pass

    if getattr(spec, "comfyui_config", None) is not None:
        try:
            from duckclaw.forge.skills.comfyui_bridge import register_comfyui_skill

            register_comfyui_skill(tools, spec.comfyui_config, duckclaw_db=db)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            _log.debug("comfyui skills registration skipped", exc_info=True)

    if getattr(spec, "homeostasis_config", None):
        try:
            from duckclaw.forge.skills.homeostasis_bridge import register_homeostasis_skill
            register_homeostasis_skill(tools, spec, db, tools_by_name)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            pass
    else:
        try:
            from duckclaw.forge.skills.homeostasis_bridge import register_goals_alignment_skill
            register_goals_alignment_skill(tools, db)
            tools_by_name = {t.name: t for t in tools}
        except Exception:
            pass

    # Strix Sandbox: `run_sandbox` si hay security_policy.yaml; `run_browser_sandbox` si browser_sandbox en manifest.
    try:
        security_policy_path = spec.worker_dir / "security_policy.yaml"
        if security_policy_path.is_file() and llm is not None:
            from duckclaw.graphs.sandbox import (
                browser_sandbox_tool_factory,
                get_browser_session_url_tool_factory,
                sandbox_tool_factory,
            )

            if getattr(spec, "browser_sandbox", False) and "run_browser_sandbox" not in tools_by_name:
                tools.append(browser_sandbox_tool_factory(db, llm))
                tools_by_name = {t.name: t for t in tools}
            if getattr(spec, "browser_sandbox", False) and "get_browser_session_url" not in tools_by_name:
                tools.append(get_browser_session_url_tool_factory(db, llm))
                tools_by_name = {t.name: t for t in tools}
            if "run_sandbox" not in tools_by_name:
                tools.append(sandbox_tool_factory(db, llm))
                tools_by_name = {t.name: t for t in tools}
    except Exception:
        pass

    # Aplicar LangSmith config al grafo final (no solo al llm) si está habilitado
    send_to_langsmith = os.environ.get("DUCKCLAW_SEND_TO_LANGSMITH", "false").lower() == "true"
    if send_to_langsmith:
        os.environ["LANGCHAIN_TRACING_V2"] = "true"
        # Honor explicitly set project in env, otherwise fallback to spec name or default
        if not os.environ.get("LANGCHAIN_PROJECT"):
            os.environ["LANGCHAIN_PROJECT"] = instance_name or getattr(spec, "name", "DuckClaw") or "default"
        # Si la API KEY no existe en el entorno, LangSmith simplemente la ignorará o fallará silenciosamente
    else:
        # Desactivar explícitamente para esta instanciación si estaba globalmente activo
        os.environ["LANGCHAIN_TRACING_V2"] = "false"

    from langgraph.graph import END, StateGraph
    from langchain_core.messages import HumanMessage, SystemMessage, AIMessage, ToolMessage

    has_homeostasis = bool(getattr(spec, "homeostasis_config", None))
    _task_block = _TASK_AWARENESS_PROMPT.strip()
    _system_prompt_only = (system_prompt or "").strip()
    _task_block_resolved = _task_block
    effective_prompt = _system_prompt_only + "\n\n" + _task_block_resolved
    # Cierre de dominio = última instrucción al modelo (domain_closure.md del worker).
    effective_prompt = append_domain_closure_block(effective_prompt, spec)
    _lid = (getattr(spec, "logical_worker_id", None) or spec.worker_id or "").strip()
    _cp = _normalized_context_pruning(spec)
    use_cm = bool(_cp.get("enabled"))
    _schema_digest = ""
    if _cp.get("enabled"):
        schema_name = (str(getattr(spec, "schema_name", None) or "")).strip()
        allowed_tables = list(getattr(spec, "allowed_tables", None) or [])
        at = ", ".join(str(table) for table in allowed_tables) if allowed_tables else "(ninguna lista explícita)"
        _schema_digest = (
            f"\n\nContexto de datos:\nEsquema configurado: {schema_name or '(no especificado)'}; "
            f"tablas permitidas: {at}. Para tipos y DDL exactos, usa get_schema_info si está disponible.\n"
        )
    _context_prompt_base: str | None = (effective_prompt + _schema_digest) if _cp.get("enabled") else None

    def prepare_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        cfg = config or {}
        conf_obj = cfg.get("configurable")
        meta = cfg.get("metadata") or {}
        conf_incoming = (conf_obj.get("incoming") if isinstance(conf_obj, dict) else None) or (meta.get("incoming") if meta else None)
        incoming = (
            (state.get("incoming") or state.get("input") or "").strip()
            or (str(conf_incoming).strip() if conf_incoming else "")
        )
        if not incoming and state.get("messages"):
            for m in reversed(state["messages"]):
                if isinstance(m, HumanMessage) and getattr(m, "content", None):
                    incoming = (str(m.content) or "").strip()
                    break
        if not isinstance(incoming, str):
            incoming = str(incoming or "").strip()
        if _context_prompt_base is not None:
            prompt = _compose_context_summary_prompt(
                _context_prompt_base,
                (state.get("analytical_summary") or state.get("context_summary") or "").strip(),
            )
        else:
            prompt = effective_prompt
        messages = [SystemMessage(content=prompt)]
        for h in (state.get("history") or []):
            role = (h.get("role") or "").lower()
            content = h.get("content") or ""
            if role == "user":
                messages.append(HumanMessage(content=content))
            elif role == "assistant":
                messages.append(AIMessage(content=content))
        needs_task = state.get("homeostasis_hint") == "ask_task" or _is_no_task(incoming)
        if needs_task:
            user_content = (
                f"[El usuario dijo: '{incoming.strip() or '(vacío)'}'. No ha indicado una tarea concreta. "
                "Pregúntale: ¿Cuál es mi tarea? Y ofrece ejemplos de lo que puedes hacer según tu rol.]"
            )
        else:
            user_content = incoming
        messages.append(HumanMessage(content=user_content))
        messages = _apply_provider_input_budget(messages, provider=provider)
        # LangGraph puede reemplazar/limitar el state entre nodos; preservamos chat_id para
        # que _sandbox_enabled_for_state (y otros flags por sesión) lean el ID correcto.
        out = {**state, "messages": messages, "incoming": incoming}
        if (state.get("analytical_summary") or "").strip():
            out["analytical_summary"] = (state.get("analytical_summary") or "").strip()
        out.update(_identity_fields(state))
        return out

    context_monitor_node = _build_context_monitor_node(
        pruning_config=_cp,
        prompt_base=_context_prompt_base or effective_prompt,
        llm_summary=llm_summary,
        identity_fields=_identity_fields,
    ) if use_cm else None

    def _sandbox_enabled_for_state(state: dict) -> bool:
        """Sandbox flag per chat/session (defaults OFF; ON for admin UI si no hay override)."""
        from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session
        from duckclaw.graphs.on_the_fly_commands import get_chat_state

        chat_id = state.get("chat_id") or state.get("session_id") or "default"
        raw = get_chat_state(db, chat_id, "sandbox_enabled")
        v = (raw or "").strip().lower()
        if not v and is_admin_ui_chat_session(str(chat_id)):
            return True
        return v in ("true", "1", "on", "sí", "si")

    tools_sandbox_off = filter_tools_for_sandbox(tools, enabled=False)
    tools_by_name_sandbox_off = {t.name: t for t in tools_sandbox_off}

    _groq_bind = (provider or "").strip().lower() == "groq"
    _tools_for_llm_bind = _groq_tools_without_reddit_for_bind(tools) if _groq_bind else tools
    _tools_sandbox_off_bind = (
        _groq_tools_without_reddit_for_bind(tools_sandbox_off) if _groq_bind else tools_sandbox_off
    )
    if _groq_bind:
        _log.info(
            "Groq: bind genérico sin reddit_* (%d tools; forzados Reddit/otros usan set acorde).",
            len(_tools_for_llm_bind),
        )

    if llm is None:
        def agent_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
            out = {
                **state,
                "messages": state["messages"] + [AIMessage(content="Sin LLM configurado. Configura DUCKCLAW_LLM_PROVIDER.")],
            }
            out.update(_identity_fields(state))
            return out
    else:
        from duckclaw.integrations.llm_providers import (
            bind_tools_with_parallel_default as _bind_tools,
            extract_embedded_tool_invokes,
        )

        # Cache de re-ligado por modo (evita re-bind costoso por chat/turno).
        # parallel_tool_calls=True en APIs OpenAI-compat (incl. MLX): permite varias tool_calls en un turno.
        # Groq (~12k TPM): rutas genéricas sin reddit_* (ver _tools_for_llm_bind); Reddit forzado usa `tools` completo.
        llm_with_tools_on = _bind_tools(llm, _tools_for_llm_bind)
        llm_with_tools_off = _bind_tools(llm, _tools_sandbox_off_bind)

        has_read_sql = "read_sql" in tools_by_name
        has_admin_sql = "admin_sql" in tools_by_name
        has_run_sandbox = "run_sandbox" in tools_by_name
        tool_choice_inspect_schema = {"type": "function", "function": {"name": "inspect_schema"}}
        tool_choice_read_sql = {"type": "function", "function": {"name": "read_sql"}}
        tool_choice_admin_sql = {"type": "function", "function": {"name": "admin_sql"}}
        tool_choice_run_sandbox = {"type": "function", "function": {"name": "run_sandbox"}}

        llm_force_schema_on = _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_inspect_schema)
        llm_force_schema_off = _bind_tools(
            llm, _tools_sandbox_off_bind, tool_choice=tool_choice_inspect_schema
        )
        llm_force_read_sql_on = _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_read_sql)
        llm_force_read_sql_off = _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_read_sql)
        llm_force_admin_sql_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_admin_sql) if has_admin_sql else None
        )
        llm_force_admin_sql_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_admin_sql)
            if has_admin_sql
            else None
        )
        llm_force_run_sandbox_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_run_sandbox)
            if has_run_sandbox
            else None
        )
        llm_force_run_sandbox_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_run_sandbox)
            if "run_sandbox" in tools_by_name_sandbox_off
            else None
        )

        has_tavily = "tavily_search" in tools_by_name
        tool_choice_tavily = {"type": "function", "function": {"name": "tavily_search"}}
        llm_force_tavily_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_tavily) if has_tavily else None
        )
        llm_force_tavily_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_tavily) if has_tavily else None
        )

        has_generate_visual = "generate_visual_asset" in tools_by_name
        tool_choice_generate_visual = {
            "type": "function",
            "function": {"name": "generate_visual_asset"},
        }
        llm_force_generate_visual_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_generate_visual)
            if has_generate_visual
            else None
        )
        llm_force_generate_visual_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_generate_visual)
            if "generate_visual_asset" in tools_by_name_sandbox_off
            else None
        )

        has_fetch_market = "fetch_market_data" in tools_by_name
        tool_choice_fetch_market = {"type": "function", "function": {"name": "fetch_market_data"}}
        llm_force_fetch_market_on = (
            _bind_tools(llm, _tools_for_llm_bind, tool_choice=tool_choice_fetch_market)
            if has_fetch_market
            else None
        )
        llm_force_fetch_market_off = (
            _bind_tools(llm, _tools_sandbox_off_bind, tool_choice=tool_choice_fetch_market)
            if has_fetch_market
            else None
        )

        _reddit_tool_names = sorted(k for k in tools_by_name if (k or "").startswith("reddit_"))
        has_reddit_tools = bool(_reddit_tool_names)

        def _reddit_tool_choice_dict(tool_nm: str) -> dict[str, Any]:
            return {"type": "function", "function": {"name": tool_nm}}

        llm_force_reddit_post_on = (
            _bind_tools(llm, tools, tool_choice=_reddit_tool_choice_dict("reddit_get_post"))
            if "reddit_get_post" in tools_by_name
            else None
        )
        llm_force_reddit_post_off = (
            _bind_tools(llm, tools_sandbox_off, tool_choice=_reddit_tool_choice_dict("reddit_get_post"))
            if "reddit_get_post" in tools_by_name_sandbox_off
            else None
        )
        llm_force_reddit_search_on = (
            _bind_tools(llm, tools, tool_choice=_reddit_tool_choice_dict("reddit_search_reddit"))
            if "reddit_search_reddit" in tools_by_name
            else None
        )
        llm_force_reddit_search_off = (
            _bind_tools(llm, tools_sandbox_off, tool_choice=_reddit_tool_choice_dict("reddit_search_reddit"))
            if "reddit_search_reddit" in tools_by_name_sandbox_off
            else None
        )
        _reddit_fallback_nm = None
        if has_reddit_tools and not llm_force_reddit_post_on and not llm_force_reddit_search_on:
            _reddit_fallback_nm = _reddit_tool_names[0]
        llm_force_reddit_fallback_on = (
            _bind_tools(llm, tools, tool_choice=_reddit_tool_choice_dict(_reddit_fallback_nm))
            if _reddit_fallback_nm and _reddit_fallback_nm in tools_by_name
            else None
        )
        llm_force_reddit_fallback_off = (
            _bind_tools(llm, tools_sandbox_off, tool_choice=_reddit_tool_choice_dict(_reddit_fallback_nm))
            if _reddit_fallback_nm and _reddit_fallback_nm in tools_by_name_sandbox_off
            else None
        )

        def _incoming_has_reddit_url(text: str) -> bool:
            if not text or not str(text).strip():
                return False
            return bool(re.search(r"(?:reddit\.com|redd\.it)/", str(text), re.IGNORECASE))

        def _incoming_looks_like_reddit_post_url(text: str) -> bool:
            if not text or not str(text).strip():
                return False
            return bool(
                re.search(
                    r"(?:https?://)?(?:www\.)?reddit\.com/r/[\w_]+/comments/[\w]+",
                    str(text),
                    re.IGNORECASE,
                )
            )

        def _first_reddit_url_in_text(text: str) -> Optional[str]:
            return _extract_first_reddit_url(text)

        def _incoming_has_reddit_share_path(text: str) -> bool:
            return bool(re.search(r"reddit\.com/r/[\w_]+/s/[a-zA-Z0-9]+", str(text or ""), re.IGNORECASE))

        def _reddit_share_slug_from_incoming(text: str) -> Optional[str]:
            m = re.search(r"/r/[\w_]+/s/([a-zA-Z0-9]+)", str(text or ""), re.IGNORECASE)
            return m.group(1) if m else None

        def _count_tool_messages_named(messages: list[Any], tool_name: str) -> int:
            n = 0
            for m in messages or []:
                if isinstance(m, ToolMessage) and (getattr(m, "name", None) or "") == tool_name:
                    n += 1
            return n

        def _reddit_tool_message_no_data(msg: Any) -> bool:
            if not isinstance(msg, ToolMessage):
                return False
            name = str(getattr(msg, "name", "") or "").strip()
            if not name.startswith("reddit_"):
                return False
            content = str(getattr(msg, "content", "") or "")
            low = content.lower()
            if "not found" in low:
                return True
            if '"posts": []' in content:
                return True
            return False

        def _tc_args_as_dict(tc: Any) -> dict[str, Any]:
            if isinstance(tc, dict):
                args = tc.get("args")
                if isinstance(args, dict):
                    return dict(args)
                raw = tc.get("arguments")
                if isinstance(raw, str) and raw.strip():
                    try:
                        parsed = json.loads(raw)
                        if isinstance(parsed, dict):
                            return dict(parsed)
                    except Exception:
                        pass
            return {}

        def _patch_ai_reddit_share_tool_calls(resp: Any, share_url: str, *, attempt_index: int = 0) -> Any:
            """
            Fallback si no hubo resolución HTTP a URL /comments/ en agent_node: el slug /s/ no es post_id.
            Reescribe get_post (o search con query=URL) → reddit_search_reddit con query shortlink.
            El camino preferido sigue siendo _resolve_reddit_share_url_to_comments_url + reddit_get_post.
            """
            if not share_url or not _incoming_has_reddit_share_path(share_url):
                return resp
            tcs = list(getattr(resp, "tool_calls", None) or [])
            if not tcs:
                return resp
            _q_safe = reddit_share_search_query_for_attempt(share_url, attempt_index)
            patched: list[Any] = []
            changed = False
            for tc in tcs:
                name = tc.get("name") if isinstance(tc, dict) else getattr(tc, "name", "")
                tid = (tc.get("id") if isinstance(tc, dict) else getattr(tc, "id", None)) or ""
                if name == "reddit_get_post":
                    patched.append(
                        {"name": "reddit_search_reddit", "args": {"query": _q_safe}, "id": tid}
                    )
                    changed = True
                    continue
                if name == "reddit_search_reddit":
                    if isinstance(tc, dict):
                        args = _tc_args_as_dict(tc)
                        args["query"] = _q_safe
                        new_tc = {**tc, "args": args}
                        new_tc.pop("arguments", None)
                        patched.append(new_tc)
                        changed = True
                        continue
                    try:
                        base = getattr(tc, "args", None)
                        args = dict(base) if isinstance(base, dict) else {}
                        args["query"] = _q_safe
                        patched.append(tc.model_copy(update={"args": args}))
                        changed = True
                    except Exception:
                        patched.append(tc)
                    continue
                patched.append(tc)
            if not changed:
                return resp
            return resp.model_copy(update={"tool_calls": patched})

        def _is_schema_query(text: str) -> bool:
            return incoming_is_schema_query_heuristic(text)


        def _is_latest_game_query(text: str) -> bool:
            if not text or not text.strip():
                return False
            t = text.strip().lower()
            return bool(
                re.search(r"\b(ultima|última|mas\s+reciente|más\s+reciente)\s+partida\b", t)
            ) or ("partida" in t and ("ultima" in t or "última" in t or "reciente" in t))

        def agent_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
            _raise_if_chat_cancelled_from_state(state)
            if state.get("visual_evidence_graph_retry"):
                state = {**state, "visual_evidence_graph_retry": False}
            _chat_ctx = state.get("chat_id") or state.get("session_id") or "default"
            _tenant_ctx = (state.get("tenant_id") or "").strip() or "default"
            _log_chat = format_chat_log_identity(str(_chat_ctx).strip() or "default", state.get("username"))
            set_log_context(tenant_id=_tenant_ctx, worker_id=worker_id, chat_id=_log_chat)
            try:
                from duckclaw.forge.skills.goals_tool_context import (
                    set_goals_tool_chat_id,
                    set_goals_tool_db_path,
                    set_goals_tool_worker_id,
                )

                set_goals_tool_chat_id(str(_chat_ctx))
                set_goals_tool_worker_id(worker_id)
                set_goals_tool_db_path(str(path))
            except Exception:
                pass
            _wl = _worker_log_label(worker_id)
            cfg = config or {}
            incoming = (
                (state.get("incoming") or state.get("input") or "").strip()
                or (cfg.get("configurable") or {}).get("incoming") or ""
            )
            if isinstance(incoming, str):
                incoming = incoming.strip()
            else:
                incoming = str(incoming or "").strip()
            # Fallback: extraer del último HumanMessage
            if not incoming and state.get("messages"):
                for m in reversed(state["messages"]):
                    if isinstance(m, HumanMessage) and getattr(m, "content", None):
                        incoming = (str(m.content) or "").strip()
                        break
            _user_incoming_raw = (state.get("user_incoming") or "").strip()
            _intent_incoming = (
                _user_incoming_raw
                if _user_incoming_raw
                and incoming_is_manager_planned_guardrail_task(incoming)
                else incoming
            )
            telegram_context_summarize_directive = (
                "[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]" in (incoming or "")
                or "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]" in (incoming or "")
            )
            summarize_stored_directive = "[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]" in (incoming or "")
            _is_goals_tick_msg = (
                str(incoming or "").strip().startswith("[SYSTEM_EVENT:")
                and proactive_review_event_phrase_in_text(str(incoming or ""))
            )
            if _is_goals_tick_msg:
                try:
                    from duckclaw.forge.homeostasis.goals_alignment import (
                        alignment_review_phrase_in_text,
                        pick_nudge_opener,
                    )
                    from duckclaw.graphs.chat_heartbeat import publish_admin_chat_heartbeat

                    if alignment_review_phrase_in_text(str(incoming or "")):
                        publish_admin_chat_heartbeat(
                            str(_chat_ctx),
                            pick_nudge_opener(str(_chat_ctx), time.time()),
                            kind="alignment",
                            worker_id=worker_id,
                        )
                except Exception:
                    pass
            is_schema = _is_schema_query(_intent_incoming)
            is_table_content = _incoming_is_table_content_query(_intent_incoming)
            is_latest_game = _is_latest_game_query(_intent_incoming)
            # Resumen post /context --add | --summary: el volcado ya va en el mensaje; no forzar inspect_schema
            # (p. ej. "esquemas criptográficos" dispara is_schema por subcadena "esquema"), read_sql, Reddit, etc.
            # SUMMARIZE_STORED_CONTEXT suele incluir URLs (reddit.com/...): sin esto, force_reddit roba el turno
            # y el modelo nunca sintetiza el snapshot de main.semantic_memory.
            if telegram_context_summarize_directive:
                is_schema = False
                is_table_content = False
                is_latest_game = False
            # No forzar herramienta si el último mensaje ya es ToolMessage (ya ejecutamos la tool):
            # así el LLM puede responder con texto y no entrar en bucle (inspect_schema -> agent -> inspect_schema).
            last_msg = (state.get("messages") or [])[-1] if state.get("messages") else None
            already_has_tool_result = last_msg is not None and isinstance(last_msg, ToolMessage)

            _orch = None
            _orch_forced: str | None = None
            try:
                from duckclaw.workers.tool_orchestration import (
                    parse_tool_orchestration,
                    resolve_forced_tool,
                )

                _orch = parse_tool_orchestration(spec)
                if _orch and not telegram_context_summarize_directive:
                    _orch_forced = resolve_forced_tool(
                        _orch,
                        incoming,
                        state.get("messages") or [],
                        tools_by_name,
                    )
            except Exception:
                _orch = None
                _orch_forced = None

            if (
                _orch_forced == "get_current_time"
                and "get_current_time" in tools_by_name
                and not telegram_context_summarize_directive
            ):
                _lh_orch_gct = _last_human_message_index(state.get("messages") or [])
                if not _tool_called_since(
                    state.get("messages") or [], _lh_orch_gct, "get_current_time"
                ):
                    _forced_tid_orch_gct = f"call_orch_get_current_time_{int(time.time() * 1000)}"
                    _forced_tc_orch_gct = [
                        {
                            "name": "get_current_time",
                            "args": {},
                            "id": _forced_tid_orch_gct,
                            "type": "tool_call",
                        }
                    ]
                    _log.info("[%s] tool_orchestration → get_current_time", _wl)
                    _out_orch_gct = {
                        **state,
                        "messages": state["messages"]
                        + [AIMessage(content="", tool_calls=_forced_tc_orch_gct)],
                    }
                    _out_orch_gct.update(_identity_fields(state))
                    return _out_orch_gct

            db_first_tool_decision = _decide_db_first_tool_invocation(
                spec=spec,
                incoming=incoming,
                available_tools=tools_by_name,
                already_has_tool_result=already_has_tool_result,
                summarize_directive=telegram_context_summarize_directive,
                orchestration_active=bool(_orch),
            )

            force_schema = is_schema and not already_has_tool_result
            force_admin_sql = bool(
                _orch_forced == "admin_sql"
                or db_first_tool_decision.is_tool("admin_sql")
            )
            force_read_sql = bool(
                _orch_forced == "read_sql"
                or db_first_tool_decision.is_tool("read_sql")
                or (
                    (
                        is_table_content
                        or is_latest_game
                    )
                    and not already_has_tool_result
                )
            )
            force_tavily = False

            _reddit_anchor_u: Optional[str] = None
            if _incoming_has_reddit_url(incoming):
                _reddit_anchor_u = _first_reddit_url_in_text(incoming)
            incoming_for_reddit = incoming
            if _reddit_anchor_u and (_reddit_anchor_u not in (incoming or "")):
                incoming_for_reddit = f"{incoming}\n{_reddit_anchor_u}"

            _reddit_resolved_comments_url: Optional[str] = None
            if _reddit_anchor_u and _incoming_has_reddit_share_path(_reddit_anchor_u):
                _reddit_resolved_comments_url = _resolve_reddit_share_url_to_comments_url(_reddit_anchor_u)
            if _reddit_resolved_comments_url:
                incoming_for_reddit = (
                    f"{incoming_for_reddit}\nCanonical Reddit thread: {_reddit_resolved_comments_url}"
                )

            share_slug = _reddit_share_slug_from_incoming(incoming_for_reddit)
            reddit_search_tool_count = _count_tool_messages_named(state.get("messages") or [], "reddit_search_reddit")
            need_share_followup = bool(
                share_slug
                and already_has_tool_result
                and isinstance(last_msg, ToolMessage)
                and (last_msg.name or "") == "reddit_search_reddit"
                and share_slug not in str(last_msg.content or "")
                and reddit_search_tool_count < 2
                and not _reddit_tool_message_no_data(last_msg)
            )
            # SUMMARIZE_NEW_CONTEXT con solo URL de Reddit debe poder forzar Reddit (fetch); STORED con URLs en
            # el volcado no debe robar el turno (sintetizar snapshot DuckDB).
            if (
                _reddit_tools_paused()
                and _reddit_anchor_u
                and _incoming_has_reddit_url(incoming)
                and not already_has_tool_result
            ):
                _paused_ai = AIMessage(
                    content=(
                        "🔴 Reddit pausado (`DUCKCLAW_REDDIT_PAUSED=1`). "
                        "No se invocaron herramientas reddit_* en este turno."
                    )
                )
                _out_rp = {**state, "messages": state["messages"] + [_paused_ai]}
                _out_rp.update(_identity_fields(state))
                return _out_rp
            _visual_calls_this_turn = _visual_asset_calls_since_last_human(state.get("messages") or [])
            _visual_tool_already_ok = bool(
                already_has_tool_result
                and isinstance(last_msg, ToolMessage)
                and (last_msg.name or "") == "generate_visual_asset"
                and '"ok":true' in str(last_msg.content or "").replace(" ", "")
            )
            force_visual = bool(
                has_generate_visual
                and tool_surface == "visual_generation"
                and not telegram_context_summarize_directive
                and not summarize_stored_directive
                and _visual_calls_this_turn == 0
                and not already_has_tool_result
                and not _visual_tool_already_ok
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_tavily
                )
            )
            _visual_tool_failed = bool(
                already_has_tool_result
                and isinstance(last_msg, ToolMessage)
                and (last_msg.name or "") == "generate_visual_asset"
                and '"ok":false' in str(last_msg.content or "").replace(" ", "")
            )
            if _visual_tool_failed:
                err_msg = "No pude generar la imagen."
                try:
                    payload = json.loads(str(last_msg.content or ""))
                    if isinstance(payload, dict) and payload.get("error"):
                        err_msg = str(payload["error"])
                except (json.JSONDecodeError, TypeError):
                    pass
                if "cancelad" in err_msg.lower():
                    err_msg = (
                        f"{err_msg} Si enviaste otro mensaje mientras generaba, "
                        "espera a que termine ComfyUI (~3 min en Mac) antes de escribir de nuevo."
                    )
                _fail_ai = AIMessage(content=f"⚠️ {err_msg}")
                _out_fail = {**state, "messages": state["messages"] + [_fail_ai]}
                _out_fail.update(_identity_fields(state))
                return _out_fail

            if _visual_tool_already_ok:
                caption = "Imagen generada."
                try:
                    payload = json.loads(str(last_msg.content or ""))
                    if isinstance(payload, dict):
                        caption = str(payload.get("message") or caption).strip() or caption
                except (json.JSONDecodeError, TypeError):
                    pass
                _ok_ai = AIMessage(content=caption)
                _out_ok = {**state, "messages": state["messages"] + [_ok_ai]}
                _out_ok.update(_identity_fields(state))
                return _out_ok

            _allow_reddit_force = bool(
                _incoming_has_reddit_url(incoming)
                or (telegram_context_summarize_directive and _reddit_anchor_u)
            )
            force_reddit = bool(
                not force_visual
                and not _reddit_tools_paused()
                and
                _allow_reddit_force
                and has_reddit_tools
                and _reddit_anchor_u is not None
                and not summarize_stored_directive
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_tavily
                )
                and (not already_has_tool_result or need_share_followup)
            )
            # Tras 2× reddit_search_reddit en /s/… el MCP suele seguir sin el hilo correcto; si no cortamos,
            # el LLM re-invoca reddit_search en bucle (evidencia: pm2 logs 13:52, forced_tool=auto).
            _reddit_share_mcp_exhausted = bool(
                _worker_use_heuristic_first_tool(spec)
                and _allow_reddit_force
                and bool(share_slug)
                and bool(_reddit_anchor_u)
                and _incoming_has_reddit_share_path(str(_reddit_anchor_u))
                and reddit_search_tool_count >= 2
            )

            if not _worker_use_heuristic_first_tool(spec):
                force_schema = False
                force_admin_sql = False
                if not (
                    db_first_tool_decision.is_tool("read_sql")
                    and not db_first_tool_decision.requires_heuristic_first_tool
                ):
                    force_read_sql = False
                force_tavily = False
                force_reddit = False
                force_visual = False

            market_data_tool_decision = _decide_market_data_tool_invocation(
                spec=spec,
                incoming=incoming,
                available_tools=tools_by_name,
                already_has_tool_result=already_has_tool_result,
                summarize_ok_for_forced_ohlcv=not telegram_context_summarize_directive,
                blocked_by_prior_decision=bool(
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_tavily
                    or force_reddit
                ),
                heuristic_first_tool_enabled=_worker_use_heuristic_first_tool(spec),
            )
            force_fetch_market_data = market_data_tool_decision.is_tool("fetch_market_data")

            _incoming_l = (incoming or "").lower()
            _is_graph_request = any(
                k in _incoming_l
                for k in (
                    "gráfica",
                    "grafica",
                    "gráfico",
                    "grafico",
                    "diagrama",
                    "plot",
                    "streamplot",
                    "subplot",
                    "matplotlib",
                    "seaborn",
                    "plotly",
                )
            )
            _is_plot_docs_request = any(
                k in _incoming_l
                for k in (
                    "matplotlib.org",
                    "seaborn.pydata.org",
                    "plotly.com/python",
                    "docs matplotlib",
                    "doc matplotlib",
                    "docs seaborn",
                    "doc seaborn",
                    "docs plotly",
                    "doc plotly",
                )
            )
            _plot_capable_worker = _worker_has_runtime_capability(spec, "plot_docs_lookup")
            force_plot_docs = bool(
                has_tavily
                and _plot_capable_worker
                and _is_plot_docs_request
                and not telegram_context_summarize_directive
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_reddit
                    or force_fetch_market_data
                )
                and not already_has_tool_result
            )
            force_run_sandbox = bool(
                has_run_sandbox
                and _plot_capable_worker
                and _is_graph_request
                and not telegram_context_summarize_directive
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_tavily
                    or force_plot_docs
                    or force_reddit
                    or force_fetch_market_data
                )
                and not already_has_tool_result
            )
            if not _worker_use_heuristic_first_tool(spec):
                force_plot_docs = False
                force_run_sandbox = False
            if force_plot_docs:
                force_tavily = True

            _lh_current_time = _last_human_message_index(state.get("messages") or [])
            _called_time_tools = (
                {"get_current_time"}
                if _tool_called_since(
                    state.get("messages") or [], _lh_current_time, "get_current_time"
                )
                else set()
            )
            current_time_tool_decision = _decide_current_time_tool_invocation(
                spec=spec,
                incoming=incoming,
                available_tools=tools_by_name,
                called_tools_since_last_human=_called_time_tools,
                already_has_tool_result=already_has_tool_result,
                summarize_directive=telegram_context_summarize_directive,
                orchestration_active=bool(_orch),
            )
            if current_time_tool_decision.direct_tool_call and current_time_tool_decision.tool_name:
                _forced_tid_current_time = f"call_policy_{current_time_tool_decision.tool_name}_{int(time.time() * 1000)}"
                _forced_tc_current_time = [
                    {
                        "name": current_time_tool_decision.tool_name,
                        "args": dict(current_time_tool_decision.tool_args),
                        "id": _forced_tid_current_time,
                        "type": "tool_call",
                    }
                ]
                _log.info(
                    "[%s] runtime policy → %s reason=%s",
                    _wl,
                    current_time_tool_decision.tool_name,
                    current_time_tool_decision.reason,
                )
                _out_current_time = {
                    **state,
                    "messages": state["messages"] + [AIMessage(content="", tool_calls=_forced_tc_current_time)],
                }
                _out_current_time.update(_identity_fields(state))
                return _out_current_time

            sandbox_enabled = _sandbox_enabled_for_state(state)

            _force_vlm_evidence_retry = bool(
                int(state.get("visual_evidence_retry_count") or 0) > 0
                and is_market_analysis_worker
                and has_read_sql
                and _worker_use_heuristic_first_tool(spec)
                and not telegram_context_summarize_directive
                and not summarize_stored_directive
                and not already_has_tool_result
                and not (
                    force_schema
                    or force_admin_sql
                    or force_read_sql
                    or force_tavily
                    or force_reddit
                    or force_fetch_market_data
                    or force_plot_docs
                    or force_run_sandbox
                )
            )
            if _force_vlm_evidence_retry:
                force_read_sql = True
            _reddit_http_prefetch_ctx: Optional[str] = None

            if (
                force_visual
                and has_generate_visual
                and not already_has_tool_result
                and not _visual_tool_already_ok
            ):
                _vis_prompt = (incoming or "").strip()[:1200]
                _forced_tid = f"call_generate_visual_{int(time.time() * 1000)}"
                _forced_tc = [
                    {
                        "name": "generate_visual_asset",
                        "args": {
                            "prompt": _vis_prompt,
                            "negative_prompt": "",
                            "aspect_ratio": "1:1",
                        },
                        "id": _forced_tid,
                        "type": "tool_call",
                    }
                ]
                _log.info(
                    "[%s] runtime policy visual → generate_visual_asset prompt=%r",
                    _wl,
                    _vis_prompt[:120],
                )
                _forced_resp = AIMessage(content="", tool_calls=_forced_tc)
                _out_vis = {**state, "messages": state["messages"] + [_forced_resp]}
                _out_vis.update(_identity_fields(state))
                return _out_vis

            llm_with_tools = llm_with_tools_on if sandbox_enabled else llm_with_tools_off
            forced_name = "auto"
            if force_admin_sql:
                forced_name = "admin_sql"
            elif force_read_sql:
                forced_name = "read_sql"
            elif force_schema:
                forced_name = "inspect_schema"
            elif force_visual:
                forced_name = "generate_visual_asset"
            elif force_tavily:
                forced_name = "tavily_search"
            elif force_reddit:
                forced_name = "reddit"
            elif force_fetch_market_data:
                forced_name = "fetch_market_data"
            elif force_run_sandbox:
                forced_name = "run_sandbox"
            _log.info(
                "[%s] incoming=%r | is_schema=%s | is_table_content=%s | is_latest_game=%s | forced_tool=%s",
                _wl,
                incoming[:80] + ("..." if len(incoming) > 80 else ""),
                is_schema,
                is_table_content,
                is_latest_game,
                forced_name,
            )
            from duckclaw.utils.formatters import sanitize_reddit_tool_messages_for_llm

            _msg_list = sanitize_reddit_tool_messages_for_llm(list(state["messages"]))
            if not _worker_use_heuristic_first_tool(spec):
                _msg_list = [
                    SystemMessage(content=prompt_policies.load("directive", "tool_choice_generic"))
                ] + _msg_list
            if _reddit_share_mcp_exhausted:
                _msg_list = [
                    SystemMessage(content=prompt_policies.load("directive", "reddit_share_exhausted"))
                ] + _msg_list
            if _visual_tool_already_ok:
                _msg_list = [
                    SystemMessage(
                        content=(
                            "La imagen ya fue generada con generate_visual_asset en este turno. "
                            "Responde al usuario con la ruta/artefacto; NO vuelvas a llamar "
                            "generate_visual_asset ni edit_visual_asset."
                        )
                    )
                ] + _msg_list
            _reddit_ctx_block: Optional[str] = None
            if _reddit_http_prefetch_ctx and not already_has_tool_result:
                _reddit_ctx_block = _reddit_http_prefetch_ctx
            if not _reddit_ctx_block:
                for _rm in reversed(_msg_list):
                    if isinstance(_rm, ToolMessage) and str(getattr(_rm, "name", "") or "").startswith(
                        "reddit_"
                    ):
                        from duckclaw.utils.formatters import build_reddit_llm_context_block

                        _reddit_ctx_block = build_reddit_llm_context_block(str(_rm.content or ""))
                        break
            if _reddit_ctx_block:
                _msg_list = [SystemMessage(content=_reddit_ctx_block)] + _msg_list
            _rag_turn_without_db_intent = should_prioritize_rag_over_storage_tools(
                incoming,
                _intent_incoming,
                explicit_storage_request=explicit_duckdb_schema_request,
            )
            if _rag_turn_without_db_intent:
                _msg_list = [
                    SystemMessage(content=rag_turn_system_prompt(prompt_policies, _lid))
                ] + [m for m in _msg_list if not isinstance(m, SystemMessage)]
            _groq_msgs = _apply_provider_input_budget(_msg_list, provider=provider)
            _invoked_llm: Any = llm_with_tools
            if force_admin_sql:
                _fa = llm_force_admin_sql_on if sandbox_enabled else llm_force_admin_sql_off
                _invoked_llm = _fa or llm_with_tools
            elif force_schema and not force_read_sql:
                _invoked_llm = (
                    llm_force_schema_on if sandbox_enabled else llm_force_schema_off
                )
            elif force_read_sql:
                _invoked_llm = (
                    llm_force_read_sql_on if sandbox_enabled else llm_force_read_sql_off
                )
            elif force_tavily:
                _ft = llm_force_tavily_on if sandbox_enabled else llm_force_tavily_off
                _invoked_llm = _ft or llm_with_tools
            elif force_visual:
                _fgv = llm_force_generate_visual_on if sandbox_enabled else llm_force_generate_visual_off
                _invoked_llm = _fgv or llm_with_tools
            elif force_reddit:
                _fr = None
                if _reddit_resolved_comments_url and _incoming_looks_like_reddit_post_url(
                    _reddit_resolved_comments_url
                ):
                    _fr = llm_force_reddit_post_on if sandbox_enabled else llm_force_reddit_post_off
                elif _incoming_has_reddit_share_path(incoming_for_reddit):
                    # Enlace /s/ sin URL canónica resuelta: forzar reddit_get_post; el parche posterior
                    # sustituye por reddit_search_reddit(query=r/<sub> shortlink <slug>). Forzar search
                    # directo empujaba query=URL y el MCP fallaba (evidencia: children undefined).
                    _fr = llm_force_reddit_post_on if sandbox_enabled else llm_force_reddit_post_off
                elif _incoming_looks_like_reddit_post_url(incoming_for_reddit):
                    _fr = llm_force_reddit_post_on if sandbox_enabled else llm_force_reddit_post_off
                if _fr is None:
                    _fr = llm_force_reddit_search_on if sandbox_enabled else llm_force_reddit_search_off
                if _fr is None:
                    _fr = llm_force_reddit_fallback_on if sandbox_enabled else llm_force_reddit_fallback_off
                _invoked_llm = _fr or llm_with_tools
            elif force_fetch_market_data:
                _ffmd = llm_force_fetch_market_on if sandbox_enabled else llm_force_fetch_market_off
                _invoked_llm = _ffmd or llm_with_tools
            elif force_run_sandbox:
                _frs = llm_force_run_sandbox_on if sandbox_enabled else llm_force_run_sandbox_off
                _invoked_llm = _frs or llm_with_tools
            if _reddit_share_mcp_exhausted and _invoked_llm is llm_with_tools:
                _bind_base_ex = _tools_for_llm_bind if sandbox_enabled else _tools_sandbox_off_bind
                _nr_ex = [
                    t
                    for t in _bind_base_ex
                    if not str(getattr(t, "name", "") or "").startswith("reddit_")
                ]
                _invoked_llm = _bind_tools(llm, _nr_ex)
            if _rag_turn_without_db_intent and forced_name == "auto":
                _bind_base_rag = _tools_for_llm_bind if sandbox_enabled else _tools_sandbox_off_bind
                _rag_tools = without_storage_tools(_bind_base_rag)
                if len(_rag_tools) < len(_bind_base_rag):
                    _invoked_llm = _bind_tools(llm, _rag_tools)
            _llm_invoke_exc: BaseException | None = None
            try:
                _raise_if_chat_cancelled_from_state(state)
                from duckclaw.integrations.llm_providers import invoke_chat_model_with_transient_retries

                resp = invoke_chat_model_with_transient_retries(_invoked_llm, _groq_msgs)
                if (
                    is_market_analysis_worker
                    and resp is not None
                    and getattr(resp, "tool_calls", None)
                ):
                    _ru_share = _first_reddit_url_in_text(incoming_for_reddit)
                    if (
                        _ru_share
                        and _incoming_has_reddit_share_path(_ru_share)
                        and not _reddit_resolved_comments_url
                    ):
                        resp = _patch_ai_reddit_share_tool_calls(
                            resp, _ru_share, attempt_index=reddit_search_tool_count
                        )
                    elif _reddit_resolved_comments_url:
                        resp = _patch_reddit_get_post_args_from_canonical_url(
                            resp, _reddit_resolved_comments_url
                        )
            except Exception as exc:
                from duckclaw.graphs.chat_cancel import ChatCancelledError

                if isinstance(exc, ChatCancelledError):
                    raise
                _llm_invoke_exc = exc
                _log.warning("[%s] LLM invoke failed in agent_node: %s", _wl, exc, exc_info=True)
                from duckclaw.integrations.llm_providers import failure_provider_label_for_llm_invoke

                _pl_fail = failure_provider_label_for_llm_invoke(_invoked_llm, provider)
                resp = AIMessage(content=_agent_node_llm_failure_user_message(exc, provider=_pl_fail))
            tool_calls = getattr(resp, "tool_calls", None) or []
            _is_goals_tick = (
                str(incoming or "").strip().startswith("[SYSTEM_EVENT:")
                and proactive_review_event_phrase_in_text(str(incoming or ""))
            )
            if tool_calls:
                _tc_names: list[Any] = []
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        _tc_names.append(tc.get("name"))
                    else:
                        _tc_names.append(getattr(tc, "name", None))
                _log.info("[%s] LLM tool_calls=%s", _wl, _tc_names)
            _resp_content = ""
            try:
                from duckclaw.integrations.llm_providers import lc_message_content_to_text

                _resp_content = (lc_message_content_to_text(resp) or "").strip()
            except Exception:
                _resp_content = str(getattr(resp, "content", "") or "").strip()
            _lh_gct_fix = _last_human_message_index(state.get("messages") or [])
            _post_tools_synthesis = _post_tools_synthesis_needed(
                state.get("messages") or [],
                incoming,
                last_human_idx=_lh_gct_fix,
                already_has_tool_result=already_has_tool_result,
            )
            _json_echo = _reply_is_tool_json_echo(_resp_content)
            _gct_lone_url_skip = _clock_only_lone_url_no_repair(
                incoming,
                state.get("messages") or [],
                last_human_idx=_lh_gct_fix,
            )
            _inline_repair_gate = _post_tools_synthesis or (
                _json_echo and not _gct_lone_url_skip
            )
            _inline_will_synth = bool(
                not tool_calls
                and _llm_invoke_exc is None
                and is_market_analysis_worker
                and _inline_repair_gate
                and (not _resp_content or _json_echo)
            )
            _market_inline_synth_attempted = False
            if (
                not tool_calls
                and _llm_invoke_exc is None
                and is_market_analysis_worker
                and _inline_repair_gate
                and (
                    not _resp_content
                    or _reply_is_tool_json_echo(_resp_content)
                )
            ):
                _market_inline_synth_attempted = True
                _gct_data = (
                    _parse_get_current_time_json(_resp_content)
                    or _latest_tool_json_since(
                        state.get("messages") or [], _lh_gct_fix, "get_current_time"
                    )
                    or {}
                )
                _day = str(_gct_data.get("day_of_week") or "")
                _tm = str(_gct_data.get("time") or "")[:5]
                _clock_hint = f"{_day} {_tm} COT".strip() if (_day or _tm) else ""
                _brand = (getattr(spec, "name", None) or _lid or "Worker").strip()
                _tools_ran = [
                    str(getattr(m, "name", "") or "")
                    for m in (state.get("messages") or [])[max(0, _lh_gct_fix + 1) :]
                    if isinstance(m, ToolMessage)
                ]
                _tools_hint = ", ".join(dict.fromkeys(_tools_ran)) if _tools_ran else "herramientas"
                _follow_sys = SystemMessage(
                    content=(
                        f"Ya ejecutaste {_tools_hint} en este turno. "
                        + (f"Encabezado {_brand} con {_clock_hint}. " if _clock_hint else "")
                        + "Redacta la respuesta final completa en español integrando el contexto visual "
                        "y los resultados de herramientas. PROHIBIDO pegar JSON crudo de herramientas."
                    )
                )
                try:
                    # Síntesis en prosa: sin bind_tools (evita re-forzar run_sandbox cuando el
                    # follow-up SystemMessage queda como último mensaje del batch).
                    resp = invoke_chat_model_with_transient_retries(
                        llm, list(_groq_msgs) + [_follow_sys]
                    )
                    try:
                        from duckclaw.integrations.llm_providers import lc_message_content_to_text

                        _resp_content = (lc_message_content_to_text(resp) or "").strip()
                    except Exception:
                        _resp_content = str(getattr(resp, "content", "") or "").strip()
                    tool_calls = getattr(resp, "tool_calls", None) or []
                except Exception as exc:
                    _log.warning("[%s] post-tools synthesis retry failed: %s", _wl, exc)
            out = {**state, "messages": state["messages"] + [resp]}
            if _market_inline_synth_attempted:
                out["market_inline_synthesis_attempted"] = True
            if _llm_invoke_exc is not None:
                from duckclaw.integrations.llm_providers import is_transient_inference_connection_error

                out["_duckclaw_worker_llm_invoke_failed"] = True
                out["_duckclaw_worker_llm_transient"] = bool(
                    is_transient_inference_connection_error(_llm_invoke_exc)
                )
                out["_duckclaw_worker_llm_failure_kind"] = type(_llm_invoke_exc).__name__
            else:
                for _k in (
                    "_duckclaw_worker_llm_invoke_failed",
                    "_duckclaw_worker_llm_transient",
                    "_duckclaw_worker_llm_failure_kind",
                ):
                    out.pop(_k, None)
            out.update(_identity_fields(state))
            return out

    def tools_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        _cid_tools = str(state.get("chat_id") or state.get("session_id") or "").strip()
        _raise_if_chat_cancelled_from_state(state)
        from duckclaw.graphs.chat_heartbeat import (
            format_tool_heartbeat,
            heartbeat_message_for_tool,
            schedule_chat_heartbeat_dm,
        )
        from duckclaw.utils.formatters import format_reddit_mcp_reply_if_applicable

        _chat_ctx = state.get("chat_id") or state.get("session_id") or "default"
        _tenant_ctx = (state.get("tenant_id") or "").strip() or "default"
        _log_chat = format_chat_log_identity(str(_chat_ctx).strip() or "default", state.get("username"))
        set_log_context(tenant_id=_tenant_ctx, worker_id=worker_id, chat_id=_log_chat)
        _wl = _worker_log_label(worker_id)
        messages = state["messages"]
        last = messages[-1]
        tool_calls = getattr(last, "tool_calls", None) or []
        _tool_round = int(state.get("_tool_round") or 0) + 1
        new_msgs = list(messages)
        sandbox_enabled = _sandbox_enabled_for_state(state)
        tool_lookup = tools_by_name if sandbox_enabled else tools_by_name_sandbox_off
        sandbox_b64: str | None = state.get("sandbox_photo_base64") if isinstance(state.get("sandbox_photo_base64"), str) else None
        visual_artifact_id: str | None = (
            str(state.get("visual_artifact_id") or "").strip() or None
        )
        _hb_head = (state.get("subagent_instance_label") or "").strip() or None
        _hb_uname = (state.get("username") or "").strip() or None
        _hb_plan = (state.get("heartbeat_plan_title") or "").strip() or None
        _hb_tok = (state.get("outbound_telegram_bot_token") or "").strip() or None

        _duck_exts = list(getattr(spec, "duckdb_extensions", None) or [])
        # DuckDB mismo PID: sesión principal RW (read_only=False) + connect RO efímero al mismo archivo →
        # "different configuration than existing". Workers RO pueden desactivar pool vía manifest
        # por contención con db-writer.
        use_ephemeral_parallel = (
            read_pool.read_pool_active_for_worker(spec)
            and read_pool.should_parallelize_ephemeral_tool_calls(tool_calls)
            and bool(getattr(spec, "read_only", False))
        )

        def _notify_admin_tool_phase(
            tool_name: str,
            phase: str,
            detail: str = "",
            *,
            elapsed_ms: float | None = None,
        ) -> None:
            _hcid = str(state.get("chat_id") or state.get("session_id") or "").strip()
            if not _hcid:
                return
            try:
                from duckclaw.graphs.chat_heartbeat import (
                    is_admin_ui_chat_session,
                    publish_admin_tool_event,
                )

                if not is_admin_ui_chat_session(_hcid):
                    return
                publish_admin_tool_event(
                    _hcid,
                    tool_name,
                    phase,
                    worker_id=(_hb_head or worker_id or "").strip() or None,
                    detail=detail,
                    elapsed_ms=elapsed_ms,
                )
            except Exception:
                pass

        def _schedule_tool_heartbeat(tool_name: str) -> None:
            _htid = (state.get("tenant_id") or "default").strip() or "default"
            _hcid = str(state.get("chat_id") or state.get("session_id") or "").strip()
            _huid = str(state.get("user_id") or "").strip() or _hcid
            try:
                from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

                _admin_ui = is_admin_ui_chat_session(_hcid)
            except Exception:
                _admin_ui = False
            if _admin_ui:
                _notify_admin_tool_phase(tool_name, "start")
                return
            _elapsed = _heartbeat_elapsed_sec(state)
            schedule_chat_heartbeat_dm(
                _htid,
                _hcid,
                _huid,
                format_tool_heartbeat(
                    _hb_head,
                    heartbeat_message_for_tool(tool_name),
                    plan_title=_hb_plan,
                    elapsed_sec=_elapsed,
                ),
                log_worker_id=_hb_head,
                log_username=_hb_uname,
                log_plan_title=_hb_plan,
                outbound_bot_token=_hb_tok,
                routing_worker_id=worker_id,
            )

        if use_ephemeral_parallel:
            _log.info("[%s] tools_node: ephemeral read-pool parallel (%d calls)", _wl, len(tool_calls))
            n_workers = min(len(tool_calls), read_pool.read_pool_max_concurrency())

            def _parallel_job(idx_tc: tuple[int, dict[str, Any]]) -> tuple[int, str, str, str]:
                idx, tc = idx_tc
                name = (tc.get("name") or "").strip()
                args = tc.get("args") or {}
                tid = tc.get("id") or ""
                _schedule_tool_heartbeat(name)
                _tool_t0 = time.perf_counter()
                try:
                    if name == "read_sql":
                        q = str(args.get("query", "")) if isinstance(args, dict) else ""
                        content = read_pool.run_ephemeral_read_sql(
                            spec, path, path, shared_resolved, _duck_exts, q
                        )
                    elif name == "inspect_schema":
                        content = read_pool.run_ephemeral_inspect_schema(
                            path, path, shared_resolved, _duck_exts
                        )
                    else:
                        content = json.dumps({"error": f"Herramienta inesperada en read-pool: {name}"})
                except Exception as e:
                    content = f"Error: {e}"
                    _log.warning("[%s] ephemeral tool=%s failed: %s", _wl, name, e)
                    _notify_admin_tool_phase(
                        name,
                        "error",
                        str(e)[:240],
                        elapsed_ms=(time.perf_counter() - _tool_t0) * 1000,
                    )
                else:
                    _notify_admin_tool_phase(
                        name,
                        "done",
                        "",
                        elapsed_ms=(time.perf_counter() - _tool_t0) * 1000,
                    )
                _log.info(
                    "[%s] tool=%s | ephemeral | result_len=%d | preview=%r",
                    _wl,
                    name,
                    len(content),
                    content[:120] + ("..." if len(content) > 120 else ""),
                )
                return idx, tid, name, content

            ordered_slots: list[tuple[str, str, str] | None] = [None] * len(tool_calls)
            with ThreadPoolExecutor(max_workers=max(1, n_workers)) as pool:
                futs = [pool.submit(_parallel_job, (i, tc)) for i, tc in enumerate(tool_calls)]
                for fut in as_completed(futs):
                    idx, tid, name, content = fut.result()
                    ordered_slots[idx] = (tid, name, content)
            for i in range(len(tool_calls)):
                slot = ordered_slots[i]
                if slot is None:
                    tc = tool_calls[i]
                    new_msgs.append(
                        ToolMessage(
                            content=json.dumps({"error": "read_pool: resultado faltante"}),
                            tool_call_id=tc.get("id") or "",
                            name=(tc.get("name") or "").strip(),
                        )
                    )
                    continue
                tid, name, content = slot
                new_msgs.append(ToolMessage(content=content, tool_call_id=tid, name=name))
        else:
            for tc in tool_calls:
                _raise_if_chat_cancelled_from_state(state)
                name = (tc.get("name") or "").strip()
                args = tc.get("args") or {}
                tid = tc.get("id") or ""
                tool = tool_lookup.get(name)
                if tool:
                    _tool_t0: float | None = None
                    try:
                        invoke_args: Any = args
                        if isinstance(args, dict):
                            invoke_args = {**args}
                        if name in (
                            "run_sandbox",
                            "run_browser_sandbox",
                            "execute_sandbox_script",
                        ):
                            if not str(invoke_args.get("worker_id") or "").strip():
                                invoke_args["worker_id"] = worker_id
                            _cid_sb = str(state.get("chat_id") or state.get("session_id") or "").strip()
                            if _cid_sb and not str(invoke_args.get("chat_id") or "").strip():
                                invoke_args["chat_id"] = _cid_sb
                            if _cid_sb and not str(invoke_args.get("session_id") or "").strip():
                                from duckclaw.graphs.novnc_registry import sanitize_chat_to_session_id

                                invoke_args["session_id"] = sanitize_chat_to_session_id(_cid_sb)
                        if name == "get_browser_session_url":
                            if not isinstance(invoke_args, dict):
                                invoke_args = {}
                            _cid = str(state.get("chat_id") or state.get("session_id") or "").strip()
                            if _cid and not str(invoke_args.get("chat_id") or "").strip():
                                invoke_args["chat_id"] = _cid
                        if name == "run_browser_sandbox":
                            from duckclaw.graphs.sandbox import ensure_browser_novnc_session

                            _sid = str(invoke_args.get("session_id") or "").strip()
                            _cid_sb = str(invoke_args.get("chat_id") or state.get("chat_id") or "").strip()
                            _vnc_pre = (
                                ensure_browser_novnc_session(
                                    worker_id,
                                    _sid,
                                    db=db,
                                    chat_id=_cid_sb or None,
                                )
                                if _sid
                                else None
                            )
                            _schedule_run_browser_novnc_tool_heartbeat(
                                state,
                                routing_worker_id=worker_id,
                                vnc_url=_vnc_pre,
                                novnc_session_id=_sid or "",
                            )
                        _schedule_tool_heartbeat(name)
                        if (
                            name == "run_sandbox"
                            and _sandbox_heartbeat_allowed(spec)
                        ):
                            from duckclaw.graphs.chat_heartbeat import is_chat_heartbeat_enabled

                            _htid = (state.get("tenant_id") or "default").strip() or "default"
                            _hcid = str(state.get("chat_id") or state.get("session_id") or "").strip()
                            if not is_chat_heartbeat_enabled(_htid, _hcid):
                                _send_sandbox_heartbeat_telegram(state)
                        _tool_t0 = time.perf_counter()
                        result = tool.invoke(invoke_args)
                        content = str(result) if result is not None else "OK"
                        if name in ("run_sandbox", "run_browser_sandbox"):
                            try:
                                payload = json.loads(content)
                                if isinstance(payload, dict) and payload.get("exit_code") == 0:
                                    fb = payload.get("figure_base64")
                                    if isinstance(fb, str) and len(fb) > 32:
                                        sandbox_b64 = fb
                            except (json.JSONDecodeError, TypeError):
                                pass
                        if name in ("generate_visual_asset", "edit_visual_asset"):
                            try:
                                payload = json.loads(content)
                                if isinstance(payload, dict) and payload.get("ok"):
                                    aid = str(payload.get("artifact_id") or "").strip()
                                    if aid:
                                        visual_artifact_id = aid
                                        try:
                                            from duckclaw.graphs.chat_heartbeat import (
                                                is_admin_ui_chat_session,
                                                publish_admin_chat_heartbeat,
                                            )

                                            _cid = str(state.get("chat_id") or "").strip()
                                            if _cid and is_admin_ui_chat_session(_cid):
                                                publish_admin_chat_heartbeat(
                                                    _cid,
                                                    "Imagen generada (ComfyUI)",
                                                    kind="visual",
                                                    artifact_id=aid,
                                                    artifact_tenant_id=_tenant_ctx,
                                                )
                                        except Exception:
                                            pass
                                    fb = payload.get("figure_base64")
                                    if isinstance(fb, str) and len(fb) > 32:
                                        sandbox_b64 = fb
                                    elif payload.get("artifacts"):
                                        from duckclaw.forge.skills.comfyui_bridge import (
                                            read_artifact_image_as_b64,
                                        )
                                        arts = payload.get("artifacts")
                                        if isinstance(arts, list) and arts:
                                            first = str(arts[0] or "").strip()
                                            if first:
                                                b64_art = read_artifact_image_as_b64(
                                                    first,
                                                    _tenant_ctx,
                                                )
                                                if b64_art:
                                                    sandbox_b64 = b64_art
                            except (json.JSONDecodeError, TypeError):
                                pass
                            if not use_cm:
                                content = _compact_run_sandbox_tool_content_for_llm(
                                    content, _RUN_SANDBOX_TOOL_LLM_MAX_CHARS
                                )
                        if name.startswith("reddit_"):
                            content = format_reddit_mcp_reply_if_applicable(content)
                        _prev = content[:120] + ("..." if len(content) > 120 else "")
                        _log.info(
                            "[%s] tool=%s | result_len=%d | preview=%r",
                            _wl,
                            name,
                            len(content),
                            _prev,
                        )
                        _admin_detail = _prev
                        if name in ("read_sql", "admin_sql", "inspect_schema", "get_schema_info"):
                            _admin_detail = ""
                        elif name == "run_browser_sandbox":
                            try:
                                _bp = json.loads(content)
                                if isinstance(_bp, dict) and _bp.get("browser_image_missing"):
                                    _admin_detail = str(_bp.get("hint") or _admin_detail)[:240]
                            except (json.JSONDecodeError, TypeError):
                                pass
                        _notify_admin_tool_phase(
                            name,
                            "done",
                            _admin_detail,
                            elapsed_ms=(time.perf_counter() - _tool_t0) * 1000,
                        )
                    except Exception as e:
                        content = f"Error: {e}"
                        _log.warning("[%s] tool=%s failed: %s", _wl, name, e)
                        _notify_admin_tool_phase(
                            name,
                            "error",
                            str(e)[:240],
                            elapsed_ms=(
                                (time.perf_counter() - _tool_t0) * 1000 if _tool_t0 is not None else None
                            ),
                        )
                else:
                    if not sandbox_enabled and name in (
                        "run_sandbox",
                        "run_browser_sandbox",
                        "get_browser_session_url",
                    ):
                        content = "Sandbox deshabilitado en esta sesión. Actívalo con /sandbox on."
                    else:
                        content = f"Herramienta desconocida: {name}"
                    _log.warning(
                        "[%s] unknown/unavailable tool: %s (sandbox_enabled=%s)",
                        _wl,
                        name,
                        sandbox_enabled,
                    )
                new_msgs.append(ToolMessage(content=content, tool_call_id=tid, name=name))
        out: dict[str, Any] = {**state, "messages": new_msgs, "_tool_round": _tool_round}
        if sandbox_b64:
            out["sandbox_photo_base64"] = sandbox_b64
        if visual_artifact_id:
            out["visual_artifact_id"] = visual_artifact_id
        out.update(_identity_fields(state))
        return out

    def set_reply(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        from duckclaw.utils.formatters import format_reddit_mcp_reply_if_applicable
        from duckclaw.utils import format_tool_reply
        from duckclaw.egress.user_reply_nl_synthesis import (
            incoming_has_context_summarize_directive,
            maybe_synthesize_reply,
            repair_summarize_new_context_egress,
            replace_bare_summarize_image_on_vlm_gateway_down,
            replace_bare_wrong_summarize_stored_echo,
            rescind_trivial_context_summary_reply,
            state_evidence_for_context_summary_rescind,
        )
        from duckclaw.graphs.chat_heartbeat import format_tool_heartbeat, schedule_chat_heartbeat_dm
        from duckclaw.integrations.llm_providers import (
            lc_message_content_to_text,
            sanitize_worker_reply_phase1,
            sanitize_worker_reply_text,
        )
        from langchain_core.messages import ToolMessage

        def _notify_final_heartbeat() -> None:
            from duckclaw.graphs.chat_heartbeat import is_admin_ui_chat_session

            _cid_hb = str(state.get("chat_id") or state.get("session_id") or "").strip()
            if is_admin_ui_chat_session(_cid_hb):
                return
            _tid = (state.get("tenant_id") or "default").strip() or "default"
            _cid = _cid_hb
            _uid = str(state.get("user_id") or "").strip() or _cid
            _head = (state.get("subagent_instance_label") or "").strip() or None
            _un = (state.get("username") or "").strip() or None
            _pt = (state.get("heartbeat_plan_title") or "").strip() or None
            _elapsed = _heartbeat_elapsed_sec(state)
            _tok_f = (state.get("outbound_telegram_bot_token") or "").strip() or None
            schedule_chat_heartbeat_dm(
                _tid,
                _cid,
                _uid,
                format_tool_heartbeat(
                    _head,
                    "✅ Terminé los pasos con herramientas; te resumo el resultado en el siguiente mensaje.",
                    plan_title=_pt,
                    elapsed_sec=_elapsed,
                ),
                log_worker_id=_head,
                log_username=_un,
                log_plan_title=_pt,
                outbound_bot_token=_tok_f,
                routing_worker_id=str(getattr(spec, "worker_id", "") or "").strip() or None,
            )

        msgs = state.get("messages") or []
        last = msgs[-1] if msgs else None
        reply = lc_message_content_to_text(last) if last else ""
        reply = sanitize_worker_reply_phase1(reply)
        _inc_for_ctx = (state.get("incoming") or state.get("input") or "").strip()
        reply = replace_bare_wrong_summarize_stored_echo(reply, incoming=_inc_for_ctx)
        reply = replace_bare_summarize_image_on_vlm_gateway_down(reply, incoming=_inc_for_ctx)
        reply = repair_summarize_new_context_egress(reply, incoming=_inc_for_ctx)
        reply = format_reddit_mcp_reply_if_applicable(reply)
        suppress_egress = bool(state.get("suppress_subagent_egress"))

        def _nl_user_ask() -> str:
            inc = state.get("incoming") or state.get("input") or ""
            return (inc.strip() if isinstance(inc, str) else str(inc or "")).strip()

        def _apply_nl_synthesis(candidate: str) -> str:
            return maybe_synthesize_reply(llm, spec=spec, user_ask=_nl_user_ask(), reply_candidate=candidate)

        if not msgs:
            out_empty = {**state, "reply": "Sin respuesta generada."}
            out_empty.update(_identity_fields(state))
            return out_empty
        _embedded_invokes = extract_embedded_tool_invokes(reply)
        if _embedded_invokes:
            from duckclaw.utils import format_tool_reply
            sandbox_enabled = _sandbox_enabled_for_state(state)
            tool_lookup = tools_by_name if sandbox_enabled else tools_by_name_sandbox_off
            for name, _params in _embedded_invokes:
                if name not in tool_lookup:
                    _log.warning(
                        "[%s] assistant JSON tool not in registry: %s (sandbox_tools=%s)",
                        getattr(spec, "worker_id", "?"),
                        name,
                        sandbox_enabled,
                    )
                    err = json.dumps(
                        {"error": f"Herramienta no disponible en este modo: {name}"},
                        ensure_ascii=False,
                    )
                    _eb = sanitize_worker_reply_text(_apply_nl_synthesis(format_tool_reply(err)))
                    out_bad = {**state, "reply": _eb, "messages": msgs}
                    out_bad.update(_identity_fields(state))
                    return out_bad
            try:
                _parts: list[str] = []
                for name, params in _embedded_invokes:
                    result = tool_lookup[name].invoke(params)
                    _parts.append(f"### {name}\n{format_tool_reply(result)}")
                _combined = "\n\n".join(_parts)
                _notify_final_heartbeat()
                _formatted = sanitize_worker_reply_text(
                    _apply_nl_synthesis(_combined)
                )
                out_tool = {**state, "reply": _formatted, "internal_reply": _formatted, "messages": msgs}
                out_tool.update(_identity_fields(state))
                return out_tool
            except Exception as e:
                _log.warning(
                    "[%s] JSON tool invoke failed (embedded multi/single): %s",
                    getattr(spec, "worker_id", "?"),
                    e,
                    exc_info=True,
                )
                err = json.dumps(
                    {
                        "error": str(e),
                        "hint": "Si el error menciona lock de DuckDB, cierra otras conexiones (CLI, IDE) a ese .duckdb.",
                    },
                    ensure_ascii=False,
                )
                _ee = sanitize_worker_reply_text(_apply_nl_synthesis(format_tool_reply(err)))
                out_err = {**state, "reply": _ee, "messages": msgs}
                out_err.update(_identity_fields(state))
                return out_err
        _visual_only_turn = bool(
            (state.get("sandbox_photo_base64") or "").strip()
            or (state.get("visual_artifact_id") or "").strip()
        )
        if _visual_only_turn and tool_surface == "visual_generation":
            _short = (reply or "").strip()
            if not _short or len(_short) > 240:
                _short = "Imagen generada."
            reply = _short
        else:
            _spec_lid = _spec_logical_worker_id(spec)
            _lh_repair = _last_human_message_index(list(msgs) if msgs else [])
            _egress_needs_repair = _tool_response_needs_egress_repair(
                list(msgs) if msgs else [],
                _inc_for_ctx,
                reply or "",
                last_human_idx=_lh_repair,
                repair_enabled=is_market_analysis_worker,
            )
            if _egress_needs_repair:
                _inline_synth_done = bool(state.get("market_inline_synthesis_attempted"))
                _skip_llm_synth = _inline_synth_done and bool((reply or "").strip())
                reply = _repair_tool_response_egress_reply(
                    llm,
                    spec,
                    _inc_for_ctx,
                    reply or "",
                    msgs,
                    skip_llm_synthesis=_skip_llm_synth,
                    worker_display_name=str(getattr(spec, "name", None) or ""),
                )
                if _reply_is_tool_json_echo(reply or ""):
                    _det_egress = _deterministic_tool_response_summary(
                        list(msgs),
                        _lh_repair,
                        _spec_lid,
                        _inc_for_ctx,
                        worker_display_name=str(getattr(spec, "name", None) or ""),
                    )
                    if _det_egress and not _reply_is_tool_json_echo(_det_egress):
                        reply = _det_egress
            reply = _apply_nl_synthesis(reply or "")
        _rescind_incoming = state_evidence_for_context_summary_rescind(state)
        reply = rescind_trivial_context_summary_reply(
            llm, spec, incoming=_rescind_incoming, reply_candidate=reply or ""
        )
        reply = format_reddit_mcp_reply_if_applicable(reply or "")
        if not suppress_egress:
            _notify_final_heartbeat()
        try:
            from duckclaw.egress.evidence_validator import (
                VISUAL_EVIDENCE_RETRY_REASON,
                enforce_visual_evidence_rule,
                market_price_consistency_audit,
                visual_evidence_retry_system_message,
            )

            # Turnos /context (SUMMARIZE_*): sin auditorías cuánticas/VLM que puedan sustituir el resumen.
            if reply and not incoming_has_context_summarize_directive(_rescind_incoming):
                new_v, vreason = enforce_visual_evidence_rule(
                    incoming=(state.get("incoming") or ""),
                    messages=msgs,
                    reply=reply,
                    db=db,
                    spec=spec,
                )
                if vreason == VISUAL_EVIDENCE_RETRY_REASON:
                    _ve_max = _visual_evidence_max_retries()
                    _ve_count = int(state.get("visual_evidence_retry_count") or 0)
                    if _ve_count < _ve_max:
                        _log.warning(
                            "Visual evidence audit: %s — in-graph retry %s/%s",
                            vreason,
                            _ve_count + 1,
                            _ve_max,
                        )
                        _msgs_retry = list(msgs) + [visual_evidence_retry_system_message()]
                        out_retry: dict = {
                            **state,
                            "messages": _msgs_retry,
                            "reply": "",
                            "internal_reply": "",
                            "visual_evidence_retry_count": _ve_count + 1,
                            "visual_evidence_graph_retry": True,
                        }
                        out_retry.update(_identity_fields(state))
                        _sb_retry = (state.get("sandbox_photo_base64") or "").strip()
                        if _sb_retry:
                            out_retry["sandbox_photo_base64"] = _sb_retry
                        _aid_retry = (state.get("visual_artifact_id") or "").strip()
                        if _aid_retry:
                            out_retry["visual_artifact_id"] = _aid_retry
                        return out_retry
                    _log.warning(
                        "Visual evidence audit: %s — retries exhausted",
                        vreason,
                    )
                    _spec_lid_ve = _spec_logical_worker_id(spec)
                    _lh_ve = _last_human_message_index(list(msgs) if msgs else [])
                    _det_ve = _deterministic_tool_response_summary(
                        list(msgs),
                        _lh_ve,
                        _spec_lid_ve,
                        _inc_for_ctx,
                        worker_display_name=str(getattr(spec, "name", None) or ""),
                    )
                    if _det_ve:
                        reply = sanitize_worker_reply_text(_det_ve)
                    elif is_market_analysis_worker and llm is not None:
                        _repaired = _repair_tool_response_egress_reply(
                            llm,
                            spec,
                            _inc_for_ctx,
                            "",
                            list(msgs),
                            skip_llm_synthesis=False,
                            worker_display_name=str(getattr(spec, "name", None) or ""),
                        )
                        if (_repaired or "").strip():
                            reply = sanitize_worker_reply_text(_repaired)
                    if not (reply or "").strip():
                        reply = (
                            "No pude validar las cifras de mercado de la imagen con datos del ledger. "
                            "Intenta de nuevo o especifica el símbolo."
                        )
                elif vreason:
                    _log.warning("Visual evidence audit: %s", vreason)
                    reply = new_v
                new_r, price_reason = market_price_consistency_audit(db, spec, reply, messages=msgs)
                if price_reason:
                    _log.warning("Market price audit: %s", price_reason)
                    reply = new_r
        except Exception:
            pass
        reply = sanitize_worker_reply_text(reply or "")
        if (not reply or reply.strip().lower() in ("sin respuesta.", "sin respuesta")) and msgs:
            _spec_lid_fb = _spec_logical_worker_id(spec)
            _lh_fb = _last_human_message_index(list(msgs))
            if (not reply or reply.strip().lower() in ("sin respuesta.", "sin respuesta")):
                _det = _deterministic_tool_response_summary(
                    list(msgs),
                    _lh_fb,
                    _spec_lid_fb,
                    _inc_for_ctx,
                    worker_display_name=str(getattr(spec, "name", None) or ""),
                )
                if _det:
                    reply = sanitize_worker_reply_text(_det)
                else:
                    for _m in reversed(msgs):
                        if isinstance(_m, ToolMessage):
                            _fallback = sanitize_worker_reply_text(format_tool_reply(_m.content))
                            if _fallback:
                                reply = _fallback
                                break
        try:
            from duckclaw.graphs.conversation_traces import sync_final_assistant_egress_in_langchain_messages

            sync_final_assistant_egress_in_langchain_messages(msgs, reply or "")
        except Exception:
            pass
        if suppress_egress:
            out = {**state, "reply": "", "internal_reply": (reply or ""), "messages": msgs}
        else:
            out = {**state, "reply": reply or "", "internal_reply": (reply or ""), "messages": msgs}
        sb = (state.get("sandbox_photo_base64") or "").strip()
        if sb:
            out["sandbox_photo_base64"] = sb
        aid = (state.get("visual_artifact_id") or "").strip()
        if aid:
            out["visual_artifact_id"] = aid
        out.update(_identity_fields(state))
        return out

    def should_continue(state: dict) -> str:
        last = state["messages"][-1]
        _has_tools = bool(getattr(last, "tool_calls", None))
        return "tools" if _has_tools else "end"

    # Context-Guard (FactChecker + SelfCorrection) para workers con catalog_retriever
    context_guard_config = getattr(spec, "context_guard_config", None) or {}
    context_guard_enabled = (
        bool(context_guard_config.get("enabled", False))
        and "catalog_retriever" in (spec.skills_list or [])
    )
    max_retries = int(context_guard_config.get("max_retries", 2))

    def fact_check_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        from duckclaw.validators.context_guard import fact_checker_node as _fc
        return _fc(state, llm, max_retries=max_retries)

    def self_correction_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        from duckclaw.validators.context_guard import self_correction_node as _sc
        return _sc(state, llm)

    def handoff_reply_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        from duckclaw.validators.context_guard import handoff_reply_node as _hr
        return _hr(state)

    def route_after_fact_check(state: dict) -> str:
        return state.get("context_guard_route", "approved")

    def route_after_set_reply(state: dict) -> str:
        return "agent" if state.get("visual_evidence_graph_retry") else "end"

    def homeostasis_node(state: dict, config: Optional[RunnableConfig] = None) -> dict:
        """HomeostasisNode: Percepción-Sorpresa-Restauración-Actualización. Fase 1: pass-through (tabla ya creada en run_schema).
        IMPORTANTE: retornar state para preservar input/incoming; retornar {} vacío hace que LangGraph pierda el estado."""
        return state

    graph = StateGraph(dict)
    graph.add_node("prepare", prepare_node)
    if use_cm:
        graph.add_node("context_monitor", context_monitor_node)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", tools_node)
    graph.add_node("set_reply", set_reply)
    if context_guard_enabled:
        graph.add_node("fact_check", fact_check_node)
        graph.add_node("self_correction", self_correction_node)
        graph.add_node("handoff_reply", handoff_reply_node)
    if getattr(spec, "homeostasis_config", None):
        graph.add_node("homeostasis", homeostasis_node)
        graph.set_entry_point("homeostasis")
        graph.add_edge("homeostasis", "prepare")
    else:
        graph.set_entry_point("prepare")
    if use_cm:
        graph.add_edge("prepare", "context_monitor")
        graph.add_edge("context_monitor", "agent")
    else:
        graph.add_edge("prepare", "agent")
    if context_guard_enabled:
        graph.add_conditional_edges(
            "agent", should_continue,
            {"tools": "tools", "end": "fact_check"},
        )
        graph.add_conditional_edges(
            "fact_check", route_after_fact_check,
            {"approved": "set_reply", "correct": "self_correction", "handoff": "handoff_reply"},
        )
        graph.add_edge("self_correction", "fact_check")
        graph.add_edge("handoff_reply", END)
    else:
        graph.add_conditional_edges("agent", should_continue, {"tools": "tools", "end": "set_reply"})
    _tools_dest = "context_monitor" if use_cm else "agent"
    if use_cm:
        graph.add_edge("tools", "context_monitor")
    else:
        graph.add_edge("tools", "agent")
    graph.add_conditional_edges(
        "set_reply",
        route_after_set_reply,
        {"agent": "agent", "end": END},
    )

    compiled = graph.compile()
    compiled._worker_spec = spec
    compiled._worker_db = db
    return compiled
