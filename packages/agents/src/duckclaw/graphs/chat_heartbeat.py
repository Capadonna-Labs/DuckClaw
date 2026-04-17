"""
Heartbeat de observabilidad por chat: flag en Redis + DM proactivo vía **Bot API nativa**
(``TELEGRAM_BOT_TOKEN``) o webhook ``DUCKCLAW_HEARTBEAT_WEBHOOK_URL`` / ``N8N_OUTBOUND_WEBHOOK_URL``.

Fire-and-forget: el envío corre en un hilo daemon; no bloquear el grafo del agente.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
import time
from urllib.error import HTTPError, URLError
from urllib import request as urllib_request

from duckclaw.integrations.telegram import effective_telegram_bot_token_outbound
from duckclaw.utils.telegram_markdown_v2 import llm_markdown_to_telegram_html

_log = logging.getLogger(__name__)

_HEARTBEAT_KEY_PREFIX = "duckclaw:heartbeat:"
_HEARTBEAT_TTL_SECONDS = 7 * 24 * 3600


def normalize_telegram_chat_id_for_outbound(chat_id: str | None) -> str:
    """
    n8n a veces manda un etiquetado tipo «@Juan (1726618406)».
    Telegram sendMessage/sendPhoto exige el id numérico; el webhook outbound debe recibirlo así.
    """
    s = str(chat_id or "").strip()
    if not s:
        return ""
    if re.fullmatch(r"-?\d+", s):
        return s
    m = re.search(r"\((-?\d+)\)\s*$", s)
    if m:
        return m.group(1)
    m = re.search(r"-?\d{5,}", s)
    if m:
        return m.group(0)
    return s


def heartbeat_chat_id_variants(chat_id: str | None) -> list[str]:
    """Variantes de chat_id para Redis (raw del gateway + id numérico si difiere)."""
    raw = str(chat_id or "").strip()
    if not raw:
        return ["unknown"]
    norm = normalize_telegram_chat_id_for_outbound(raw)
    out: list[str] = []
    for x in (norm, raw):
        if x and x not in out:
            out.append(x)
    return out or ["unknown"]


def _all_redis_keys_for_heartbeat_lookup(tenant_id: str, chat_id: str | None) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for cid in heartbeat_chat_id_variants(chat_id):
        for k in _heartbeat_read_keys(tenant_id, cid):
            if k not in seen:
                seen.add(k)
                out.append(k)
    return out


def _redis_url() -> str:
    return (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()


def heartbeat_redis_configured() -> bool:
    return bool(_redis_url())


def heartbeat_outbound_webhook_url() -> str:
    """Webhook del nodo «salida proactiva» (p. ej. ruta distinta de /webhook/send-dm del chat principal)."""
    return (
        (os.getenv("DUCKCLAW_HEARTBEAT_WEBHOOK_URL") or "").strip()
        or (os.getenv("N8N_OUTBOUND_WEBHOOK_URL") or "").strip()
    )


def heartbeat_outbound_configured() -> bool:
    """Hay canal de salida si existe token Bot API o URL de webhook."""
    return bool(effective_telegram_bot_token_outbound()) or bool(heartbeat_outbound_webhook_url())


def heartbeat_redis_key(tenant_id: str, chat_id: str) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    cid = str(chat_id or "").strip() or "unknown"
    return f"{_HEARTBEAT_KEY_PREFIX}{tid}:{cid}"


def heartbeat_chat_alias_key(chat_id: str) -> str:
    """
    Clave solo por chat_id (sin tenant). Evita que el flag quede inactivo si el fly command
    guardó con tenant efectivo del gateway (p. ej. SIATA) y un nodo del grafo lee otro tenant.
    """
    cid = str(chat_id or "").strip() or "unknown"
    return f"{_HEARTBEAT_KEY_PREFIX}chat:{cid}"


def _heartbeat_storage_keys(tenant_id: str, chat_id: str) -> list[str]:
    canonical = heartbeat_redis_key(tenant_id, chat_id)
    alias = heartbeat_chat_alias_key(chat_id)
    if canonical == alias:
        return [canonical]
    return [canonical, alias]


def _heartbeat_read_keys(tenant_id: str, chat_id: str) -> list[str]:
    """Claves a consultar: tenant actual, alias por chat, y tenant del gateway (claves antiguas)."""
    seen: set[str] = set()
    out: list[str] = []
    for k in _heartbeat_storage_keys(tenant_id, chat_id):
        if k not in seen:
            seen.add(k)
            out.append(k)
    gw = (os.getenv("DUCKCLAW_GATEWAY_TENANT_ID") or "").strip()
    if gw:
        k = heartbeat_redis_key(gw, chat_id)
        if k not in seen:
            seen.add(k)
            out.append(k)
    return out


def is_chat_heartbeat_enabled(tenant_id: str, chat_id: str) -> bool:
    url = _redis_url()
    if not url:
        return False
    try:
        import redis as redis_sync  # noqa: PLC0415

        client = redis_sync.Redis.from_url(url, decode_responses=True)
        for key in _all_redis_keys_for_heartbeat_lookup(tenant_id, chat_id):
            v = (client.get(key) or "").strip().lower()
            if v == "on":
                return True
        return False
    except Exception:
        return False


def set_chat_heartbeat_enabled(tenant_id: str, chat_id: str, on: bool) -> tuple[bool, str]:
    """Persiste on|off en Redis con TTL 7 días (todas las variantes de chat_id + alias por tenant)."""
    url = _redis_url()
    if not url:
        return False, "REDIS_URL (o DUCKCLAW_REDIS_URL) no está configurado."
    try:
        import redis as redis_sync  # noqa: PLC0415

        client = redis_sync.Redis.from_url(url, decode_responses=True)
        val = "on" if on else "off"
        seen_keys: set[str] = set()
        for cid in heartbeat_chat_id_variants(chat_id):
            for key in _heartbeat_storage_keys(tenant_id, cid):
                if key not in seen_keys:
                    seen_keys.add(key)
                    client.setex(key, _HEARTBEAT_TTL_SECONDS, val)
        return True, ""
    except Exception as exc:
        return False, str(exc)[:500]


def _heartbeat_env_int(name: str, default: int) -> int:
    """
    ``os.environ.get(k, d)`` no usa el default si la clave existe con valor vacío;
    eso provocaba ``int('')`` al cargar el módulo.
    """
    raw = (os.environ.get(name) or "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


_HEARTBEAT_DELEGATION_MAX_CHARS = max(
    800,
    _heartbeat_env_int("DUCKCLAW_HEARTBEAT_DELEGATION_MAX_CHARS", 2800),
)
_HEARTBEAT_PLAN_TITLE_INLINE_MAX = max(
    24,
    _heartbeat_env_int("DUCKCLAW_HEARTBEAT_PLAN_TITLE_INLINE_MAX", 90),
)


def format_delegation_heartbeat_message(
    plan_title: str | None,
    tasks: list | None,
    *,
    task_summary: str = "",
    subagent_header: str | None = None,
) -> str:
    """
    Primer DM de heartbeat al delegar: storytelling corto + plan (tasks del manager).
    Texto plano (válido para Telegram vía n8n sin Markdown).

    ``subagent_header`` (p. ej. ``BI-Analyst 1``) va en la misma línea intro para no
    duplicar encabezados sueltos en el chat.
    """
    title = (plan_title or "").strip()
    hint = (task_summary or "").strip()
    if not title:
        title = hint[:120] if hint else "Plan en curso"
    head = (subagent_header or "").strip()
    opener = (
        f"📖 {head} — Acabo de recibir la tarea del Manager y arranco así:"
        if head
        else "📖 Acabo de recibir la tarea del Manager y arranco así:"
    )
    lines: list[str] = [
        opener,
        "",
        f"🎯 Objetivo: {title}",
    ]
    raw = tasks if isinstance(tasks, list) else []
    tlist = [str(x).strip() for x in raw if str(x).strip()]
    if tlist:
        lines.append("")
        lines.append("Pasos que voy siguiendo:")
        for i, item in enumerate(tlist[:15], start=1):
            one = item
            if len(one) > 220:
                one = one[:217] + "..."
            lines.append(f"{i}. {one}")
    elif hint and hint.lower() != title.lower():
        lines.append("")
        body = hint
        if len(body) > 650:
            body = body[:647] + "..."
        lines.append(body)
    out = "\n".join(lines).strip()
    if len(out) > _HEARTBEAT_DELEGATION_MAX_CHARS:
        out = out[: _HEARTBEAT_DELEGATION_MAX_CHARS - 3].rstrip() + "..."
    return out


def heartbeat_message_for_tool(name: str) -> str:
    n = (name or "").strip()
    mapping = {
        "get_schema_info": "🔎 Paso actual: entender columnas y tipos con get_schema_info…",
        "read_sql": "📊 Paso actual: consultar la base con read_sql (solo lectura)…",
        "run_sql": "📊 Paso actual: ejecutar SQL con run_sql…",
        "admin_sql": "📊 Paso actual: escritura SQL con admin_sql…",
        "run_sandbox": "⚙️ Paso actual: procesar o graficar en el sandbox (run_sandbox)…",
        "run_browser_sandbox": "🌐 Paso actual: navegación aislada en Strix browser (run_browser_sandbox)…",
        "inspect_schema": "🗂️ Paso actual: listar qué hay en la base con inspect_schema…",
        "scrape_siata_radar_realtime": "📡 Paso actual: último producto del radar (scrape_siata_radar_realtime)…",
    }
    if n in mapping:
        return mapping[n]
    return f"🔄 Paso actual: llamo a la herramienta {n}…"


def format_heartbeat_elapsed(elapsed_sec: float | None) -> str:
    """Texto corto para DM de progreso (p. ej. «⏱️ 12.3s»)."""
    if elapsed_sec is None:
        return ""
    try:
        e = max(0.0, float(elapsed_sec))
    except (TypeError, ValueError):
        return ""
    if e < 60:
        return f"⏱️ {e:.1f}s"
    m = int(e // 60)
    s = int(e % 60)
    return f"⏱️ {m}m {s}s"


def _shorten_heartbeat_plan_title(title: str) -> str:
    t = " ".join((title or "").split())
    if len(t) > _HEARTBEAT_PLAN_TITLE_INLINE_MAX:
        return t[: _HEARTBEAT_PLAN_TITLE_INLINE_MAX - 1].rstrip() + "…"
    return t


def format_tool_heartbeat(
    subagent_header: str | None,
    tool_message: str,
    *,
    plan_title: str | None = None,
    elapsed_sec: float | None = None,
) -> str:
    """
    Antepone ``BI-Analyst 1`` y opcionalmente el título del plan del manager
    a los DMs de progreso por herramienta. ``elapsed_sec`` = segundos desde el
    inicio del turno del subagente (``subagent_turn_started_monotonic``).
    """
    head = (subagent_header or "").strip()
    plan = _shorten_heartbeat_plan_title((plan_title or "").strip())
    body = (tool_message or "").strip()
    if not body:
        return ""
    segments: list[str] = []
    if head:
        segments.append(head)
    if plan:
        segments.append(f"📋 {plan}")
    segments.append(body)
    elapsed_txt = format_heartbeat_elapsed(elapsed_sec)
    if elapsed_txt:
        segments.append(elapsed_txt)
    return " — ".join(segments)


def _post_outbound_sync(
    chat_id: str,
    user_id: str,
    text: str,
    *,
    plan_title_log: str | None = None,
    outbound_bot_token: str | None = None,
) -> None:
    cid = normalize_telegram_chat_id_for_outbound(chat_id) or str(chat_id or "").strip()
    uid_raw = str(user_id or "").strip()
    uid = normalize_telegram_chat_id_for_outbound(uid_raw) or uid_raw or cid
    raw = (text or "").strip()
    if not cid or not raw:
        return

    token = (outbound_bot_token or "").strip() or effective_telegram_bot_token_outbound()
    # region agent log
    try:
        _fp = hashlib.sha1(token.encode("utf-8")).hexdigest()[:10] if token else ""
        with open(
            "/Users/juanjosearevalocamargo/Desktop/duckclaw/.cursor/debug-c964f7.log",
            "a",
            encoding="utf-8",
        ) as _df:
            _df.write(
                json.dumps(
                    {
                        "sessionId": "c964f7",
                        "runId": "pre-fix",
                        "hypothesisId": "H11_heartbeat_token_choice",
                        "location": "packages/agents/src/duckclaw/graphs/chat_heartbeat.py:_post_outbound_sync",
                        "message": "heartbeat_token_selected",
                        "data": {
                            "chat_id": str(cid),
                            "plan": str((plan_title_log or "")[:120]),
                            "token_fp": _fp,
                            "has_explicit_token": bool((outbound_bot_token or "").strip()),
                        },
                        "timestamp": int(time.time() * 1000),
                    }
                )
                + "\n"
            )
    except Exception:
        pass
    # endregion
    if token:
        try:
            from duckclaw.integrations.telegram.telegram_outbound_sync import (
                send_long_plain_text_markdown_v2_chunks_sync,
            )

            pl = (plan_title_log or "").strip()
            if pl:
                _log.info(
                    "chat heartbeat: envío nativo chat_id=%r plan=%r partes_plain_len=%s",
                    cid,
                    pl[:120],
                    len(raw),
                )
            else:
                _log.info(
                    "chat heartbeat: envío nativo chat_id=%r partes_plain_len=%s",
                    cid,
                    len(raw),
                )
            n = send_long_plain_text_markdown_v2_chunks_sync(
                bot_token=token,
                chat_id=cid,
                plain_text=raw,
                log=_log,
            )
            if n > 0:
                _log.info("chat heartbeat: nativo OK chat_id=%r partes=%s", cid, n)
                return
            _log.warning("chat heartbeat: nativo sin partes OK; fallback webhook chat_id=%r", cid)
        except Exception as exc:
            _log.warning("chat heartbeat: error nativo chat_id=%r: %s; fallback webhook", cid, exc)

    if (os.getenv("DUCKCLAW_TELEGRAM_OUTBOUND_VIA") or "").strip().lower() != "n8n":
        _log.debug("chat heartbeat: sin fallback n8n (DUCKCLAW_TELEGRAM_OUTBOUND_VIA!=n8n) chat_id=%r", cid)
        return

    url = heartbeat_outbound_webhook_url()
    if not url:
        _log.warning(
            "chat heartbeat: sin TELEGRAM_BOT_TOKEN ni webhook (DUCKCLAW_HEARTBEAT / N8N_OUTBOUND) chat_id=%r",
            cid,
        )
        return
    auth = (os.getenv("N8N_AUTH_KEY") or "").strip()
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["X-DuckClaw-Secret"] = auth
    safe = llm_markdown_to_telegram_html(raw)
    payload = json.dumps(
        {"chat_id": cid, "user_id": uid, "text": safe, "parse_mode": "HTML"},
        ensure_ascii=False,
    ).encode("utf-8")
    req = urllib_request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=8) as resp:
            _ = resp.read()
        _log.info("chat heartbeat: webhook OK chat_id=%r url=%s", cid, url[:80])
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            pass
        _log.warning(
            "chat heartbeat outbound HTTP %s %s (chat_id=%r). url=%s | "
            "Si usas n8n: URL debe coincidir con un flujo ACTIVO. response_body=%r",
            exc.code,
            exc.reason,
            cid,
            url,
            body,
        )
    except URLError as exc:
        _log.warning("chat heartbeat outbound failed (chat_id=%r) url=%s: %s", cid, url, exc)
    except Exception as exc:
        _log.warning("chat heartbeat outbound error (chat_id=%r) url=%s: %s", cid, url, exc)


def schedule_chat_heartbeat_dm(
    tenant_id: str,
    chat_id: str,
    user_id: str,
    text: str,
    *,
    log_worker_id: str | None = None,
    log_username: str | None = None,
    log_plan_title: str | None = None,
    outbound_bot_token: str | None = None,
) -> None:
    """
    Si el heartbeat está activo para el chat, encola un POST al webhook (hilo daemon).
    No espera red; no lanza al llamante.

    ``log_worker_id`` (p. ej. ``BI-Analyst 1``) y ``log_username`` alimentan ``set_log_context``
    en ese hilo para que las líneas «chat heartbeat» en PM2 identifiquen al subagente.
    ``log_plan_title`` se añade a la línea de log del envío nativo (título del plan del manager).
    ``outbound_bot_token``: token explícito (p. ej. webhook multiplex); los hilos no heredan ContextVar.
    """
    if not is_chat_heartbeat_enabled(tenant_id, chat_id):
        return
    if not heartbeat_outbound_configured():
        return
    cid_raw = str(chat_id or "").strip()
    cid_eff = normalize_telegram_chat_id_for_outbound(cid_raw) or cid_raw
    uid_raw = str(user_id or "").strip()
    uid_eff = normalize_telegram_chat_id_for_outbound(uid_raw) or uid_raw or cid_eff
    msg = (text or "").strip()
    if not cid_eff or not msg:
        return
    tid_for_log = (tenant_id or "default").strip() or "default"
    worker_for_log = (log_worker_id or "").strip() or None
    uname_for_log = (log_username or "").strip() or None
    plan_for_log = (log_plan_title or "").strip() or None
    token_for_thread = (outbound_bot_token or "").strip() or None

    def _run() -> None:
        if worker_for_log:
            from duckclaw.utils.logger import (
                format_chat_log_identity,
                reset_log_context,
                set_log_context,
            )

            chat_lbl = format_chat_log_identity(cid_eff, uname_for_log)
            try:
                set_log_context(tenant_id=tid_for_log, worker_id=worker_for_log, chat_id=chat_lbl)
                _post_outbound_sync(
                    cid_eff,
                    uid_eff,
                    msg,
                    plan_title_log=plan_for_log,
                    outbound_bot_token=token_for_thread,
                )
            finally:
                reset_log_context()
        else:
            _post_outbound_sync(
                cid_eff,
                uid_eff,
                msg,
                plan_title_log=plan_for_log,
                outbound_bot_token=token_for_thread,
            )

    threading.Thread(target=_run, name="duckclaw-chat-heartbeat", daemon=True).start()
