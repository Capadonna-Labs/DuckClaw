"""
Heartbeat de observabilidad por chat: flag en Redis + DM proactivo vía **Bot API nativa**
(``TELEGRAM_BOT_TOKEN``) o webhook opcional ``DUCKCLAW_HEARTBEAT_WEBHOOK_URL``.

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
from pathlib import Path
from typing import Any, Callable
from urllib.error import HTTPError, URLError
from urllib import request as urllib_request

from duckclaw.heartbeat_runtime_settings import (
    HEARTBEAT_RUNTIME_DOMAIN,
    HEARTBEAT_RUNTIME_KEY,
    resolve_heartbeat_runtime_state,
    upsert_heartbeat_runtime_state,
)
from duckclaw.graphs.tool_catalog import (
    ADMIN_HEARTBEAT_SQL_TOOL_NAMES,
    heartbeat_message_for_tool_name,
)
from duckclaw.runtime_session_settings import runtime_session_actor
from duckclaw.write_commands import UpsertRuntimeSettingCommand
from duckclaw.integrations.telegram import effective_telegram_bot_token_outbound
from duckclaw.integrations.telegram.telegram_agent_token import (
    canonical_manifest_worker_id,
    resolve_telegram_token_for_worker_id,
    telegram_worker_ids_match_for_compact_route,
)
from duckclaw.utils.telegram_markdown_v2 import llm_markdown_to_telegram_html

_log = logging.getLogger(__name__)

_HEARTBEAT_KEY_PREFIX = "duckclaw:heartbeat:"
_HEARTBEAT_TTL_SECONDS = 7 * 24 * 3600
_heartbeat_runtime_db_provider: Callable[[], Any] | None = None

# SQL tools: omit query/result preview in admin SSE heartbeats on "done" phase.
ADMIN_SQL_TOOL_NAMES = ADMIN_HEARTBEAT_SQL_TOOL_NAMES


def configure_heartbeat_runtime_db_provider(provider: Callable[[], Any] | None) -> None:
    """Inject a DB provider for runtime callers that cannot pass a handle."""
    global _heartbeat_runtime_db_provider
    _heartbeat_runtime_db_provider = provider


def _heartbeat_runtime_db(db: Any = None) -> Any:
    if db is not None:
        return db
    provider = _heartbeat_runtime_db_provider
    if provider is None:
        return None
    try:
        return provider()
    except Exception:
        return None


def normalize_telegram_chat_id_for_outbound(chat_id: str | None) -> str:
    """
    Algunos clientes mandan un etiquetado tipo «@Juan (1726618406)».
    Telegram sendMessage/sendPhoto exige el id numérico; el webhook outbound debe recibirlo así.
    """
    s = str(chat_id or "").strip()
    if not s:
        return ""
    if s == "admin-playground" or s.startswith(
        ("admin-section-", "admin-ui", "admin-conv-")
    ):
        return s
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
    """Webhook HTTP opcional de salida proactiva (solo si no hay Bot API)."""
    return (os.getenv("DUCKCLAW_HEARTBEAT_WEBHOOK_URL") or "").strip()


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
    guardó con un tenant efectivo del gateway y un nodo del grafo lee otro tenant.
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


def _release_ro_handle_for_writer(db: Any) -> tuple[bool, Any]:
    release = getattr(db, "release_file_handle_for_external_writer", None)
    suspend = getattr(db, "suspend_readonly_file_handle", None)
    resume = getattr(db, "resume_readonly_file_handle", None)
    if callable(release):
        release()
        return bool(callable(resume)), resume
    if callable(suspend) and callable(resume):
        suspend()
        return True, resume
    return False, resume


def _legacy_redis_heartbeat_enabled(tenant_id: str, chat_id: str) -> bool:
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


def _set_legacy_redis_heartbeat_enabled(tenant_id: str, chat_id: str, on: bool) -> tuple[bool, str]:
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


def _set_heartbeat_runtime_state_via_writer(
    db: Any,
    *,
    tenant_id: str,
    chat_id: str,
    on: bool,
) -> tuple[bool, str]:
    raw_path = str(getattr(db, "_path", "") or "").strip()
    if not raw_path or raw_path == ":memory:":
        return False, "Ruta de bóveda no resuelta"
    try:
        target_db_path = str(Path(raw_path).expanduser().resolve())
    except OSError:
        target_db_path = raw_path
    try:
        from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync
    except Exception as exc:
        return False, f"cola DuckDB no disponible: {exc}"

    released_ro, resume = _release_ro_handle_for_writer(db)
    try:
        for cid in heartbeat_chat_id_variants(chat_id):
            command = UpsertRuntimeSettingCommand(
                tenant_id=str(tenant_id or "default").strip() or "default",
                actor_email=runtime_session_actor(cid),
                domain=HEARTBEAT_RUNTIME_DOMAIN,
                key=HEARTBEAT_RUNTIME_KEY,
                value="on" if on else "off",
                value_kind="boolean",
            )
            task_id = enqueue_typed_command(
                command,
                db_path=target_db_path,
                user_id=str(chat_id or "default").strip() or "default",
            )
            status = poll_task_status_sync(task_id, timeout_sec=30.0)
            if status is None:
                return False, "timeout esperando db-writer"
            if status.status != "success":
                return False, (status.detail or "db-writer failed")[:500]
        return True, ""
    finally:
        if released_ro and callable(resume):
            try:
                resume()
            except Exception:
                pass


def admin_heartbeat_channel(chat_id: str) -> str:
    """Canal Redis pub/sub para heartbeats en consola admin (SSE)."""
    cid = str(chat_id or "").strip() or "unknown"
    return f"duckclaw:admin-heartbeat:{cid}"


def parse_instance_label(label: str | None) -> tuple[str, int]:
    """
    Parsea etiqueta de instancia swarm (p. ej. ``worker-alpha 2``).
    Devuelve (worker_id, swarm_slot); slot mínimo 1.
    """
    raw = (label or "").strip()
    if not raw:
        return "", 1
    m = re.match(r"^(.+?)\s+(\d+)$", raw)
    if m:
        return m.group(1).strip(), max(1, int(m.group(2)))
    return raw, 1


def publish_admin_tool_event(
    chat_id: str,
    tool_name: str,
    phase: str,
    *,
    worker_id: str | None = None,
    detail: str = "",
    elapsed_ms: float | int | None = None,
) -> None:
    """
    Heartbeat admin por herramienta (SSE). Un solo bloque por tool en la UI:
    ``start`` abre cronómetro; ``done``/``error`` actualiza el mismo bloque con ``elapsed_ms``.
  """
    ph = (phase or "start").strip().lower()
    if ph not in ("start", "done", "error"):
        return
    name = (tool_name or "").strip() or "tool"
    tool_detail = ""
    if ph == "error" and (detail or "").strip():
        s = re.sub(r"\s+", " ", (detail or "").strip())
        tool_detail = s[:319] + "…" if len(s) > 320 else s
    # El playground completo recibe estos eventos vía SSE. En desktop lite la
    # consola sigue gateway.log, por lo que hay que registrar el mismo ciclo de
    # vida allí. No incluir detail: puede traer SQL, rutas o resultados.
    worker_label = (worker_id or "").strip() or "unknown"
    duration_suffix = ""
    if elapsed_ms is not None and ph in ("done", "error"):
        try:
            duration_suffix = f" | elapsed_ms={float(elapsed_ms):.0f}"
        except (TypeError, ValueError):
            pass
    _log.info(
        "tool_usage: worker=%s | tool=%s | phase=%s%s",
        worker_label,
        name,
        ph,
        duration_suffix,
    )
    text = f"🔄 Usando: {name}"
    publish_admin_chat_heartbeat(
        chat_id,
        text,
        kind="tool",
        worker_id=worker_id,
        tool_name=name,
        tool_phase=ph,
        tool_detail=tool_detail or None,
        elapsed_ms=elapsed_ms if ph in ("done", "error") else None,
    )


def publish_admin_chat_heartbeat(
    chat_id: str,
    text: str,
    *,
    kind: str = "status",
    worker_id: str | None = None,
    swarm_slot: int | None = None,
    instance_label: str | None = None,
    artifact_id: str | None = None,
    artifact_ids: list[str] | None = None,
    artifact_tenant_id: str | None = None,
    sandbox_run_id: str | None = None,
    tool_name: str | None = None,
    tool_phase: str | None = None,
    tool_detail: str | None = None,
    elapsed_ms: float | int | None = None,
) -> None:
    """
    Publica heartbeat para la UI admin (playground / widget flotante).
    Fire-and-forget; no lanza al llamante.
    """
    cid = str(chat_id or "").strip()
    msg = (text or "").strip()
    if not cid or not msg:
        return
    url = _redis_url()
    try:
        from duckclaw.spawn_profile import spawn_inline_writes_enabled

        lite_ok = spawn_inline_writes_enabled()
    except Exception:
        lite_ok = False
    if not url and not lite_ok:
        return
    wid = (worker_id or "").strip()
    slot = swarm_slot
    if instance_label:
        parsed_wid, parsed_slot = parse_instance_label(instance_label)
        if parsed_wid:
            wid = parsed_wid
        slot = parsed_slot
    if slot is None or slot < 1:
        slot = 1
    body: dict[str, Any] = {"text": msg, "kind": (kind or "status").strip() or "status"}
    if wid:
        body["worker_id"] = wid
    body["swarm_slot"] = int(slot)
    aid = (artifact_id or "").strip()
    if aid:
        body["artifact_id"] = aid
    aids = [str(x).strip() for x in (artifact_ids or []) if str(x).strip()]
    if aids:
        body["artifact_ids"] = aids
    srid = (sandbox_run_id or "").strip()
    if srid:
        body["sandbox_run_id"] = srid
    tid = (artifact_tenant_id or "").strip()
    if tid:
        body["artifact_tenant_id"] = tid
    tn = (tool_name or "").strip()
    if tn:
        body["tool_name"] = tn
    tp = (tool_phase or "").strip().lower()
    if tp in ("start", "done", "error"):
        body["tool_phase"] = tp
    td = (tool_detail or "").strip()
    if td and tp == "error":
        body["tool_detail"] = td
    if elapsed_ms is not None:
        try:
            body["elapsed_ms"] = max(0.0, float(elapsed_ms))
        except (TypeError, ValueError):
            pass
    payload = json.dumps(body, ensure_ascii=False)
    # Tool phases must publish in order (fast tools otherwise emit done before start).
    sync_tool_phase = bool(tn and tp in ("start", "done", "error"))

    def _run() -> None:
        channel = admin_heartbeat_channel(cid)
        try:
            from duckclaw.spawn_profile import spawn_inline_writes_enabled

            # Desktop lite: same in-process store the SSE listener uses (no Redis).
            if spawn_inline_writes_enabled():
                from duckclaw.lite_session_store import LITE_SESSION_STORE

                LITE_SESSION_STORE.publish(channel, payload)
                return
        except Exception as exc:
            _log.debug("admin chat heartbeat lite publish failed chat_id=%r: %s", cid, exc)
            return
        if not url:
            return
        try:
            import redis as redis_sync  # noqa: PLC0415

            client = redis_sync.Redis.from_url(url, decode_responses=True)
            client.publish(channel, payload)
        except Exception as exc:
            _log.debug("admin chat heartbeat publish failed chat_id=%r: %s", cid, exc)

    if sync_tool_phase:
        _run()
    else:
        threading.Thread(target=_run, name="duckclaw-admin-heartbeat-pub", daemon=True).start()


def _admin_heartbeat_kind(text: str, *, log_plan_title: str | None = None) -> str:
    raw = (text or "").strip()
    if (
        "🔄" in raw
        or "herramienta" in raw.lower()
        or "Paso actual" in raw
        or "✅ Terminé" in raw
    ):
        return "tool"
    if (log_plan_title or "").strip():
        return "plan"
    if "📖" in raw or "Objetivo:" in raw or "Pasos que voy" in raw:
        return "plan"
    return "status"


def admin_report_chat_id(chat_id: str | None) -> str:
    """Normaliza chat_id de consola admin (p. ej. email (admin-conv-…)) → report_id."""
    cid = str(chat_id or "").strip()
    if not cid:
        return ""
    import re

    m = re.search(r"(admin-conv-[a-f0-9]+)", cid, re.IGNORECASE)
    if m:
        return m.group(1)
    if cid.startswith("admin-conv-"):
        return cid.split()[0]
    return cid


def is_admin_ui_chat_session(chat_id: str | None) -> bool:
    """Sesiones de la consola admin (SSE); sin egress a Bot API / Telegram."""
    cid = str(chat_id or "").strip()
    if not cid:
        return False
    if cid in ("admin-playground",):
        return True
    if (
        cid.startswith("admin-section-")
        or cid.startswith("admin-ui")
        or cid.startswith("admin-conv-")
    ):
        return True
    return "admin-conv-" in cid


def is_chat_heartbeat_enabled(tenant_id: str, chat_id: str, *, db: Any = None) -> bool:
    runtime_db = _heartbeat_runtime_db(db)
    for cid in heartbeat_chat_id_variants(chat_id):
        resolved = resolve_heartbeat_runtime_state(
            runtime_db,
            tenant_id=str(tenant_id or "default").strip() or "default",
            chat_id=cid,
        )
        if resolved is not None:
            return resolved
    return _legacy_redis_heartbeat_enabled(tenant_id, chat_id)


def set_chat_heartbeat_enabled(
    tenant_id: str,
    chat_id: str,
    on: bool,
    *,
    db: Any = None,
) -> tuple[bool, str]:
    """Persist on/off in DB-first runtime settings; Redis remains legacy fallback."""
    if db is None:
        return _set_legacy_redis_heartbeat_enabled(tenant_id, chat_id, on)
    if bool(getattr(db, "_read_only", False)):
        return _set_heartbeat_runtime_state_via_writer(
            db,
            tenant_id=tenant_id,
            chat_id=chat_id,
            on=on,
        )
    try:
        for cid in heartbeat_chat_id_variants(chat_id):
            upsert_heartbeat_runtime_state(
                db,
                tenant_id=tenant_id,
                chat_id=cid,
                enabled=on,
                updated_by="heartbeat",
            )
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
    Texto plano (válido para Telegram sin Markdown).

    ``subagent_header`` (p. ej. ``worker-alpha 1``) va en la misma línea intro para no
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
    return heartbeat_message_for_tool_name(name)


def format_heartbeat_elapsed(elapsed_sec: float | None) -> str:
    """Texto corto para DM de progreso (p. ej. «⏱️ 12.3s»)."""
    if elapsed_sec is None:
        return ""
    try:
        e = max(0.0, float(elapsed_sec))
    except (TypeError, ValueError):
        return ""
    if e < 60:
        return f"⏱️ {e:.2f}s"
    m = int(e // 60)
    s = int(e % 60)
    return f"⏱️ {m}m {s}s"


def format_tool_duration_ms(elapsed_ms: float | int | None) -> str:
    """Duración de una tool en admin SSE (p. ej. «⏱️ 95ms» o «⏱️ 48.20s»)."""
    if elapsed_ms is None:
        return ""
    try:
        ms = max(0.0, float(elapsed_ms))
    except (TypeError, ValueError):
        return ""
    if ms < 1000:
        return f"⏱️ {ms:.0f}ms"
    return format_heartbeat_elapsed(ms / 1000.0)


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
    Antepone ``worker-alpha 1`` y opcionalmente el título del plan del manager
    a los DMs de progreso por herramienta. ``elapsed_sec`` = segundos desde el
    inicio del turno del subagente (``subagent_turn_started_monotonic``).
    """
    head = (subagent_header or "").strip()
    body = (tool_message or "").strip()
    if not body:
        return ""
    segments: list[str] = []
    if head:
        segments.append(head)
    segments.append(body)
    elapsed_txt = format_heartbeat_elapsed(elapsed_sec)
    if elapsed_txt:
        segments.append(elapsed_txt)
    return " — ".join(segments)


def _resolve_heartbeat_outbound_bot_token(
    outbound_bot_token: str | None,
    routing_worker_id: str | None,
) -> str:
    """
    Token Bot API para DM de heartbeat: explícito, TELEGRAM_<worker>_TOKEN,
    DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES compacto, o token global si no hay worker.
    """
    explicit = (outbound_bot_token or "").strip()
    if explicit:
        return explicit
    wid = (routing_worker_id or "").strip()
    if not wid:
        return effective_telegram_bot_token_outbound()
    cw = canonical_manifest_worker_id(wid)
    if not cw:
        return effective_telegram_bot_token_outbound()
    t = (resolve_telegram_token_for_worker_id(wid) or "").strip()
    if t:
        return t
    try:
        from duckclaw.integrations.telegram.compact_webhook_routes import load_path_webhook_bindings_from_env

        for b in load_path_webhook_bindings_from_env():
            if telegram_worker_ids_match_for_compact_route(wid, b.worker_id):
                return (str(b.bot_token) or "").strip()
    except Exception:
        _log.debug("chat heartbeat: lookup token compact routes failed", exc_info=True)
    _log.warning(
        "chat heartbeat: sin token Bot API para worker_id=%r; no se usa TELEGRAM_BOT_TOKEN genérico",
        wid,
    )
    return ""


def _post_outbound_sync(
    chat_id: str,
    user_id: str,
    text: str,
    *,
    plan_title_log: str | None = None,
    outbound_bot_token: str | None = None,
    routing_worker_id: str | None = None,
) -> None:
    cid = normalize_telegram_chat_id_for_outbound(chat_id) or str(chat_id or "").strip()
    uid_raw = str(user_id or "").strip()
    uid = normalize_telegram_chat_id_for_outbound(uid_raw) or uid_raw or cid
    raw = (text or "").strip()
    if not cid or not raw:
        return

    token = _resolve_heartbeat_outbound_bot_token(outbound_bot_token, routing_worker_id)
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

    url = heartbeat_outbound_webhook_url()
    if not url:
        _log.warning(
            "chat heartbeat: sin TELEGRAM_BOT_TOKEN ni DUCKCLAW_HEARTBEAT_WEBHOOK_URL chat_id=%r",
            cid,
        )
        return
    secret = (os.getenv("DUCKCLAW_OUTBOUND_WEBHOOK_SECRET") or "").strip()
    headers = {"Content-Type": "application/json"}
    if secret:
        headers["X-DuckClaw-Secret"] = secret
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
            "Comprueba que la URL de webhook esté activa. response_body=%r",
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
    routing_worker_id: str | None = None,
) -> None:
    """
    Si el heartbeat está activo para el chat, encola un POST al webhook (hilo daemon).
    No espera red; no lanza al llamante.

    ``log_worker_id`` (p. ej. ``worker-alpha 1``) y ``log_username`` alimentan ``set_log_context``
    en ese hilo para que las líneas «chat heartbeat» en PM2 identifiquen al subagente.
    ``log_plan_title`` se añade a la línea de log del envío nativo (título del plan del manager).
    ``outbound_bot_token``: token explícito (p. ej. webhook multiplex); los hilos no heredan ContextVar.
    ``routing_worker_id``: id de plantilla (p. ej. ``worker-alpha``) para resolver token desde
    ``TELEGRAM_*_TOKEN`` o ``DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES`` cuando no hay ContextVar.
    """
    hb_on = is_chat_heartbeat_enabled(tenant_id, chat_id)
    if is_admin_ui_chat_session(chat_id):
        kind = _admin_heartbeat_kind(text, log_plan_title=log_plan_title)
        label = (log_worker_id or "").strip()
        wid, slot = parse_instance_label(label)
        if not wid and (routing_worker_id or "").strip():
            wid = (routing_worker_id or "").strip()
            slot = 1
        publish_admin_chat_heartbeat(
            chat_id,
            text,
            kind=kind,
            worker_id=wid or None,
            swarm_slot=slot,
        )
        # Admin playground usa solo Redis pub/SSE; nunca Bot API (evita chat_id=34864 y duplicados).
        return
    if not hb_on:
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
    route_wid = (routing_worker_id or "").strip() or None

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
                    routing_worker_id=route_wid,
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
                routing_worker_id=route_wid,
            )

    threading.Thread(target=_run, name="duckclaw-chat-heartbeat", daemon=True).start()
