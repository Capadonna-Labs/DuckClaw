"""
Heartbeat de observabilidad por chat: flag en Redis + DM proactivo vía webhook n8n.

URL: ``DUCKCLAW_HEARTBEAT_WEBHOOK_URL`` (solo heartbeat) o, si falta, ``N8N_OUTBOUND_WEBHOOK_URL``.

Fire-and-forget: el POST outbound corre en un hilo daemon; no bloquear el grafo del agente.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
from urllib.error import HTTPError, URLError
from urllib import request as urllib_request

from duckclaw.utils.telegram_markdown_v2 import escape_telegram_markdown_v2

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


_HEARTBEAT_DELEGATION_MAX_CHARS = max(
    800,
    int(os.environ.get("DUCKCLAW_HEARTBEAT_DELEGATION_MAX_CHARS", "2800")),
)


def format_delegation_heartbeat_message(
    plan_title: str | None,
    tasks: list | None,
    *,
    task_summary: str = "",
) -> str:
    """
    Primer DM de heartbeat al delegar: storytelling corto + plan (tasks del manager).
    Texto plano (válido para Telegram vía n8n sin Markdown).
    """
    title = (plan_title or "").strip()
    hint = (task_summary or "").strip()
    if not title:
        title = hint[:120] if hint else "Plan en curso"
    lines: list[str] = [
        "📖 Acabo de recibir la tarea del Manager y arranco así:",
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
        "read_sql": "📊 Paso actual: traer datos del SIATA con read_sql (solo lectura)…",
        "run_sql": "📊 Paso actual: ejecutar SQL con run_sql…",
        "admin_sql": "📊 Paso actual: escritura SQL con admin_sql…",
        "run_sandbox": "⚙️ Paso actual: procesar o graficar en el sandbox (run_sandbox)…",
        "inspect_schema": "🗂️ Paso actual: listar qué hay en la base con inspect_schema…",
        "scrape_siata_radar_realtime": "📡 Paso actual: último producto del radar (scrape_siata_radar_realtime)…",
    }
    if n in mapping:
        return mapping[n]
    return f"🔄 Paso actual: llamo a la herramienta {n}…"


def _post_outbound_sync(chat_id: str, user_id: str, text: str) -> None:
    url = heartbeat_outbound_webhook_url()
    if not url:
        return
    cid = normalize_telegram_chat_id_for_outbound(chat_id) or str(chat_id or "").strip()
    uid_raw = str(user_id or "").strip()
    uid = normalize_telegram_chat_id_for_outbound(uid_raw) or uid_raw or cid
    raw = (text or "").strip()
    if not cid or not raw:
        return
    auth = (os.getenv("N8N_AUTH_KEY") or "").strip()
    headers = {"Content-Type": "application/json"}
    if auth:
        headers["X-DuckClaw-Secret"] = auth
    safe = escape_telegram_markdown_v2(raw)
    payload = json.dumps({"chat_id": cid, "user_id": uid, "text": safe}, ensure_ascii=False).encode("utf-8")
    req = urllib_request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=8) as resp:
            _ = resp.read()
    except HTTPError as exc:
        body = ""
        try:
            body = exc.read().decode("utf-8", errors="replace")[:800]
        except Exception:
            pass
        _log.warning(
            "chat heartbeat outbound HTTP %s %s (chat_id=%r). url=%s | "
            "n8n no crea ejecución en el Webhook si la URL no coincide con un flujo ACTIVO o devuelve 404. "
            "Revisa DUCKCLAW_HEARTBEAT_WEBHOOK_URL o N8N_OUTBOUND_WEBHOOK_URL (Production URL del nodo Webhook de salida). "
            "response_body=%r",
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


def schedule_chat_heartbeat_dm(tenant_id: str, chat_id: str, user_id: str, text: str) -> None:
    """
    Si el heartbeat está activo para el chat, encola un POST al webhook (hilo daemon).
    No espera red; no lanza al llamante.
    """
    if not is_chat_heartbeat_enabled(tenant_id, chat_id):
        return
    if not heartbeat_outbound_webhook_url():
        return
    cid_raw = str(chat_id or "").strip()
    cid_eff = normalize_telegram_chat_id_for_outbound(cid_raw) or cid_raw
    uid_raw = str(user_id or "").strip()
    uid_eff = normalize_telegram_chat_id_for_outbound(uid_raw) or uid_raw or cid_eff
    msg = (text or "").strip()
    if not cid_eff or not msg:
        return

    def _run() -> None:
        _post_outbound_sync(cid_eff, uid_eff, msg)

    threading.Thread(target=_run, name="duckclaw-chat-heartbeat", daemon=True).start()
