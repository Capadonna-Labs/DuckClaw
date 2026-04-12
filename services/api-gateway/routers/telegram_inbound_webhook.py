# services/api-gateway/routers/telegram_inbound_webhook.py
"""
Webhook entrante de Telegram (Bot API Update) → mismo pipeline que /api/v1/agent/.../chat.

Contrato principal (recomendado): POST ``/api/v1/telegram/webhook`` con JSON de Update; un proceso
PM2 por bot con su propia URL HTTPS al puerto correcto (ver specs ``Telegram Webhook One Gateway One Port``).

**Multiplex por path:** si ``DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES`` está en formato compacto
(``bot:token:/api/v1/telegram/...`` separado por comas), se registran ``POST`` dinámicos por ruta
y se fijan worker, tenant, token de respuesta y bóveda (ver ``core/telegram_compact_webhook_routes``).

Rutas ``/webhook/finanz`` y ``/webhook/trabajo``: legado para un solo ingress compartido; validación vía
``TELEGRAM_WEBHOOK_SECRET_*`` y cabecera ``X-Telegram-Bot-Api-Secret-Token``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import secrets
import time
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request, status

from core.config import settings
from core.telegram_chunking import gateway_multipart_plain_head_tail
from core.context_injection_delta import (
    build_context_injection_delta,
    context_injection_queue_key,
    push_context_injection_delta_redis,
)
from core.context_injection_rbac import user_may_context_inject
from core.context_injection_vault import resolve_telegram_user_vault_db_path
from core.context_stored_snapshot import fetch_semantic_memory_snapshot
from core.models import ChatRequest
from core.vlm_ingest import (
    VLMBackendUnavailableError,
    extract_pdf_plain_text_from_bytes,
    process_visual_album_batch,
    process_visual_payload,
    push_vlm_state_delta_redis,
    telegram_document_download_limit_bytes,
    telegram_download_file_bytes,
)
from duckclaw.gateway_db import resolve_env_duckdb_path
from core.war_rooms import (
    hit_rate_limit,
    is_war_room_tenant,
    normalize_telegram_bot_username,
    war_room_evaluate_mention_gate,
    war_room_tenant_for_chat,
    wr_append_audit,
    wr_has_member,
    wr_members_count,
)
from duckclaw.integrations.telegram import (
    TELEGRAM_WEBHOOK_SECRET_HTTP_HEADER,
    TelegramBotApiAsyncClient,
    telegram_bot_token_override,
)
from duckclaw.utils.telegram_markdown_v2 import llm_markdown_to_telegram_html
from duckclaw.integrations.telegram.telegram_webhook_multiplex import (
    TelegramWebhookResolvedDispatch,
    telegram_webhook_header_fingerprint,
    telegram_webhook_resolve_dispatch,
)

from core.telegram_compact_webhook_routes import (
    TelegramPathWebhookBinding,
    fastapi_relative_path,
    load_path_webhook_bindings_from_env,
)

_log = logging.getLogger("duckclaw.gateway.telegram_inbound_webhook")

_TELEGRAM_WEBHOOK_DEDUPE_KEY_PREFIX = "duckclaw:dedupe:telegram:webhook:update"
_TELEGRAM_WEBHOOK_DEDUPE_TTL_SECONDS = 172800
_WORKER_ALIAS_CACHE_TTL_SECONDS = 60
_worker_alias_cache: set[str] = set()
_worker_alias_cache_ts: float = 0.0
_VISUAL_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}

_CONTEXT_ADD_RE = re.compile(
    r"^/context(?:@[^\s]+)?\s+--add(?:\s+(.*))?$",
    re.DOTALL | re.IGNORECASE,
)
_CONTEXT_SUMMARY_RE = re.compile(
    r"^/context(?:@[^\s]+)?\s+--(?:summary|summarize|peek|db)\s*$",
    re.IGNORECASE,
)


def _parse_context_add_command(text: str) -> tuple[bool, str]:
    """(False, '') si no es el comando; (True, body) si es /context --add (body puede estar vacío)."""
    m = _CONTEXT_ADD_RE.match((text or "").strip())
    if not m:
        return False, ""
    return True, (m.group(1) or "").strip()


def _telegram_message_has_vlm_block(s: str) -> bool:
    t = (s or "").strip()
    return "[VLM_CONTEXT" in t and "Contexto visual adjunto:" in t


def _telegram_message_has_gateway_document_enrichment(s: str) -> bool:
    """PDF texto extraído en gateway o META de adjunto no parseado (sin VLM imagen)."""
    t = (s or "").strip()
    return "[CONTENIDO_TEXTO_EXTRAIDO_PDF]" in t or "[META: ATTACHED_DOCUMENT_NOT_PARSED" in t


def _resolve_context_add_body(*, raw_caption: str, current_text: str) -> tuple[bool, str]:
    """
    /context --add debe detectarse con el caption/texto crudo de Telegram.

    Tras VLM el mensaje enriquecido ya no empieza por ``/context``; sin esto,
    ``/context --add`` + foto no encola memoria ni manda SUMMARIZE_NEW_CONTEXT.
    Si hay bloque VLM o enriquecimiento PDF/META del gateway, el cuerpo a inyectar
    y resumir es el ``current_text`` completo.
    """
    is_add, body = _parse_context_add_command(raw_caption)
    if not is_add:
        return False, ""
    cur = (current_text or "").strip()
    if _telegram_message_has_vlm_block(cur) or _telegram_message_has_gateway_document_enrichment(cur):
        return True, cur
    return True, (body or "").strip()


def _parse_context_summary_command(text: str) -> bool:
    """``/context --summary`` | ``--summarize`` | ``--peek`` | ``--db``: leer memoria semántica y resumir (sin escribir)."""
    return bool(_CONTEXT_SUMMARY_RE.match((text or "").strip()))


def _summarize_new_context_directive(injected_text: str) -> str:
    t = (injected_text or "").strip()
    return (
        f"[SYSTEM_DIRECTIVE: SUMMARIZE_NEW_CONTEXT]\n{t}\n\n"
        "Sintetiza este nuevo contexto ingresado a memoria VSS. Formato: bullet points técnicos "
        "alineados con el dominio del worker activo."
    )


def _summarize_stored_context_directive(snapshot: str) -> str:
    t = (snapshot or "").strip()
    return (
        f"[SYSTEM_DIRECTIVE: SUMMARIZE_STORED_CONTEXT]\n{t}\n\n"
        "Este bloque se obtuvo leyendo ``main.semantic_memory`` en DuckDB (contexto ya persistido). "
        "Sintetiza en bullet points técnicos alineados al dominio del worker activo. "
        "No digas que acabas de guardar o encolar nada; es solo lectura de lo almacenado."
    )


def schedule_telegram_context_summary_background(
    *,
    directive_msg: str,
    telegram_header_html: str,
    log_label: str,
    invoke_agent_chat: Callable[..., Awaitable[Any]],
    resolve_effective_telegram_bot_token: Callable[[], str],
    worker_id: str,
    chat_id: int | str,
    tenant_id: str,
    vault_uid: str,
    username: str,
    chat_type: str,
    redis_client: Any,
    telegram_mcp_state: Any,
    telegram_forced_vault_db_path: str | None,
    reply_token: str | None,
    redis_session_id: str,
) -> None:
    """Invoca el grafo con directiva de resumen y envía la respuesta por Bot API (segundo plano)."""
    # Mismo session_id que el webhook multiplex (p. ej. quanttrader:1726618406) y lock Redis activo:
    # si skip_session_lock=True y session_id=chat_id puro, el resumen en background abre DuckDB RO
    # mientras el usuario manda /team: fly abre RW al mismo .duckdb → «different configuration».
    bg_payload = ChatRequest(
        message=directive_msg,
        chat_id=str(chat_id),
        user_id=vault_uid,
        username=username,
        chat_type=chat_type,
        tenant_id=tenant_id,
        is_system_prompt=True,
        skip_session_lock=False,
    )

    async def _bg_summarize_task() -> None:
        try:
            tok = (reply_token or "").strip() or (resolve_effective_telegram_bot_token() or "").strip()
            if not tok:
                _log.warning("%s: sin token de bot, no se puede enviar resumen chat_id=%s", log_label, chat_id)
                return
            with telegram_bot_token_override(tok):
                try:
                    # El resumen post `/context` ya trae el contenido en el mensaje:
                    # usar `:memory:` evita abrir la bóveda real en RO mientras
                    # DuckClaw-DB-Writer intenta persistir CONTEXT_INJECTION en RW.
                    res = await invoke_agent_chat(
                        bg_payload,
                        worker_id,
                        redis_session_id,
                        tenant_id,
                        redis_client=redis_client,
                        telegram_multipart_tail_delivery="native",
                        telegram_mcp=telegram_mcp_state,
                        telegram_forced_vault_db_path=":memory:",
                        outbound_telegram_bot_token=(reply_token or "").strip() or None,
                    )
                except HTTPException as exc:
                    detail = exc.detail
                    if isinstance(detail, dict):
                        msg_err = str(detail.get("detail") or detail)
                    else:
                        msg_err = str(detail)
                    _log.warning("%s invoke falló: %s", log_label, msg_err)
                    if msg_err:
                        try:
                            client_e = TelegramBotApiAsyncClient(tok)
                            await client_e.send_message(
                                chat_id=chat_id,
                                text=msg_err[:3900],
                                parse_mode=None,
                            )
                        except Exception as send_exc:  # noqa: BLE001
                            _log.warning("%s no pudo enviar error al usuario: %s", log_label, send_exc)
                    return

            reply_local = (res.get("response") or "").strip() if isinstance(res, dict) else ""
            used_fb = False
            try:
                from duckclaw.forge.atoms.user_reply_nl_synthesis import (
                    telegram_stored_context_summary_body_when_model_trivial,
                )

                _fb = telegram_stored_context_summary_body_when_model_trivial(
                    directive_msg,
                    reply_local,
                    html_header_will_duplicate_title=bool((telegram_header_html or "").strip()),
                )
                if _fb is not None:
                    reply_local = _fb
                    used_fb = True
                    _log.info(
                        "%s: cuerpo sustituido por fallback determinístico "
                        "(respuesta del invoke aún trivial; red de seguridad)",
                        log_label,
                    )
            except Exception as exc:  # noqa: BLE001
                _log.debug("%s: fallback determinístico omitido: %s", log_label, exc)
            if not reply_local:
                _log.warning(
                    "%s: respuesta vacía tenant_id=%s chat_id=%s worker_id=%s",
                    log_label,
                    tenant_id,
                    chat_id,
                    worker_id,
                )
                try:
                    client_e = TelegramBotApiAsyncClient(tok)
                    await client_e.send_message(
                        chat_id=chat_id,
                        text=(
                            "No se generó texto de resumen. Revisa /tasks o los logs del gateway."
                        ),
                        parse_mode=None,
                    )
                except Exception as send_exc:  # noqa: BLE001
                    _log.warning("%s no pudo enviar aviso de vacío: %s", log_label, send_exc)
                return

            head_plain = ""
            tail_plain_ctx = ""
            if isinstance(res, dict) and not used_fb:
                head_plain = (res.get("telegram_reply_head_plain") or "").strip()
                tail_plain_ctx = (res.get("telegram_multipart_tail_plain") or "").strip()
            if tail_plain_ctx and head_plain:
                body_slice = head_plain
            else:
                mh, mt = gateway_multipart_plain_head_tail(reply_local, llm_markdown_to_telegram_html)
                if mh is not None and (mt or "").strip():
                    head_plain = mh
                    tail_plain_ctx = mt
                    body_slice = head_plain
                else:
                    body_slice = reply_local

            client_r = TelegramBotApiAsyncClient(tok)
            body_html = llm_markdown_to_telegram_html(body_slice)
            combined = telegram_header_html + body_html
            cap = 4096 - 16
            if len(combined) > cap:
                combined = combined[: max(0, cap - 1)] + "…"
            sent = await client_r.send_message(chat_id=chat_id, text=combined, parse_mode="HTML")
            if not sent.get("ok"):
                plain_hdr = re.sub(r"<[^>]+>", "", telegram_header_html)
                await client_r.send_message(
                    chat_id=chat_id,
                    text=(plain_hdr + body_slice)[:3900],
                    parse_mode=None,
                )
            if tail_plain_ctx:
                from core.telegram_multipart_tail_dispatch_async import dispatch_telegram_multipart_tail_async

                await dispatch_telegram_multipart_tail_async(
                    tail_plain=tail_plain_ctx,
                    session_id=redis_session_id,
                    user_id=str(vault_uid or "").strip() or str(chat_id),
                    telegram_multipart_tail_delivery="native",
                    effective_telegram_bot_token=resolve_effective_telegram_bot_token,
                    n8n_outbound_push_sync=_telegram_multipart_tail_sync_stub,
                    telegram_mcp=telegram_mcp_state,
                    redis_client=redis_client,
                    tenant_id=tenant_id,
                )
        except Exception as exc:  # noqa: BLE001
            _log.warning("%s background invoke failed: %s", log_label, exc)

    asyncio.create_task(_bg_summarize_task())


def _telegram_entities_for_message(msg: dict[str, Any]) -> list[dict[str, Any]]:
    """Fotos/documentos usan caption_entities; texto plano usa entities."""
    if (msg.get("caption") or "").strip():
        raw = msg.get("caption_entities")
    else:
        raw = msg.get("entities")
    if isinstance(raw, list):
        return [x for x in raw if isinstance(x, dict)]
    return []


def _telegram_webhook_default_worker_id() -> str:
    """Worker de entrada al grafo: alinea con PM2 / ecosystem sin duplicar nombres."""
    for key in ("DUCKCLAW_TELEGRAM_DEFAULT_WORKER", "DUCKCLAW_DEFAULT_WORKER_ID"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    proc = (os.environ.get("DUCKCLAW_PM2_PROCESS_NAME") or "").strip()
    if proc:
        from duckclaw.integrations.telegram.telegram_agent_token import (
            PM2_GATEWAY_APP_TO_WORKER_ID,
        )

        mapped = PM2_GATEWAY_APP_TO_WORKER_ID.get(proc)
        if mapped:
            return mapped
    return "finanz"


def _telegram_webhook_default_tenant_id() -> str:
    """Tenant en el ChatRequest para trazas; _invoke_chat sigue normalizando con _effective_tenant_id."""
    for key in ("DUCKCLAW_TELEGRAM_DEFAULT_TENANT", "DUCKCLAW_GATEWAY_TENANT_ID"):
        v = (os.environ.get(key) or "").strip()
        if v:
            return v
    return "default"


def _telegram_webhook_parallel_processing_enabled() -> bool:
    """Alineado con _chat_parallel_invocations_enabled del gateway: respuesta HTTP 200 al instante."""
    return (os.environ.get("DUCKCLAW_CHAT_PARALLEL_INVOCATIONS") or "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _normalize_alias(value: str) -> str:
    return re.sub(r"[^a-z0-9_]", "", str(value or "").strip().lower())


def _resolve_dynamic_worker_aliases() -> set[str]:
    """
    Resuelve aliases desde inventario real de workers/manifests.
    Evita hardcode de nombres de bots en el router.
    """
    global _worker_alias_cache, _worker_alias_cache_ts
    now = time.monotonic()
    if _worker_alias_cache and (now - _worker_alias_cache_ts) <= _WORKER_ALIAS_CACHE_TTL_SECONDS:
        return set(_worker_alias_cache)

    aliases: set[str] = set()
    try:
        from duckclaw.workers.factory import list_workers
        from duckclaw.workers.manifest import load_manifest

        for wid in list_workers():
            raw_wid = str(wid or "").strip()
            if raw_wid:
                aliases.add(raw_wid.lower())
                norm = _normalize_alias(raw_wid)
                if norm:
                    aliases.add(norm)
            try:
                spec = load_manifest(raw_wid)
            except Exception:
                continue
            for candidate in (
                getattr(spec, "worker_id", ""),
                getattr(spec, "logical_worker_id", ""),
                getattr(spec, "name", ""),
            ):
                c = str(candidate or "").strip()
                if not c:
                    continue
                aliases.add(c.lower().replace(" ", "_"))
                norm = _normalize_alias(c)
                if norm:
                    aliases.add(norm)
    except Exception as exc:  # noqa: BLE001
        _log.warning("WR aliases dinámicos no disponibles: %s", exc)

    if "duckclaw" not in aliases:
        aliases.add("duckclaw")
    _worker_alias_cache = aliases
    _worker_alias_cache_ts = now
    return set(aliases)


async def _wr_vlm_collect_album_items(
    redis_client: Any,
    *,
    tenant_id: str,
    media_group_id: str,
    file_id: str,
    mime_type: str,
    caption: str,
) -> list[dict[str, str]] | None:
    """
    Agrupa hasta 3 file_id por media_group_id. Devuelve None si otro webhook tiene el lock
    (ese proceso hará el batch); una lista vacía si no hubo entradas válidas tras coordinar.
    """
    album_key = f"duckclaw:vlm:album:{tenant_id}:{media_group_id}"
    row = json.dumps(
        {"file_id": (file_id or "").strip(), "mime": (mime_type or "image/jpeg").strip(), "cap": (caption or "").strip()},
        ensure_ascii=False,
    )
    await redis_client.rpush(album_key, row)
    await redis_client.expire(album_key, 180)
    lock_key = f"duckclaw:vlm:album_lock:{tenant_id}:{media_group_id}"
    got = await redis_client.set(lock_key, "1", nx=True, ex=25)
    if not got:
        return None
    try:
        prev_n = -1
        stable = 0
        for _ in range(32):
            await asyncio.sleep(0.1)
            n = int(await redis_client.llen(album_key))
            if n == prev_n and n > 0:
                stable += 1
                if stable >= 2:
                    break
            else:
                stable = 0
            prev_n = n
        raw_rows = await redis_client.lrange(album_key, 0, -1)
        try:
            await redis_client.delete(album_key)
        except Exception:
            pass
        seen: set[str] = set()
        ordered: list[dict[str, str]] = []
        for raw in raw_rows or []:
            if isinstance(raw, (bytes, bytearray)):
                raw = raw.decode("utf-8", errors="replace")
            try:
                d = json.loads(str(raw))
            except json.JSONDecodeError:
                continue
            fid = str(d.get("file_id") or "").strip()
            if not fid or fid in seen:
                continue
            seen.add(fid)
            ordered.append(
                {
                    "file_id": fid,
                    "mime": str(d.get("mime") or "image/jpeg").strip().lower() or "image/jpeg",
                    "cap": str(d.get("cap") or "").strip(),
                }
            )
            if len(ordered) >= 3:
                break
        return ordered
    finally:
        try:
            await redis_client.delete(lock_key)
        except Exception:
            pass


async def _ingest_telegram_visual_enrich_text(
    *,
    text: str,
    visual: dict[str, Any],
    visual_from_parent_reply: bool,
    tenant_id: str,
    user_id: str,
    chat_id: Any,
    token_v: str,
    redis_client: Any,
    private_dm: bool,
) -> tuple[str, bool]:
    """
    Descarga imagen, VLM, devuelve texto enriquecido para el Manager.

    Returns:
        (nuevo_texto, True) si hay que cortar el webhook sin invocar chat (p. ej. MIME inválido).
        (nuevo_texto, False) en caso contrario.
    """
    mime_type = (visual.get("mime_type") or "").strip().lower()
    if mime_type and mime_type not in _VISUAL_ALLOWED_MIME:
        _log.info(
            "telegram_inbound tag=VLM_MIME_REJECTED chat_id=%s mime=%s private_dm=%s",
            chat_id,
            (mime_type or "unknown")[:128],
            private_dm,
        )
        cap_ok = bool((text or "").strip())
        # PDF/otros no-imagen con caption o comando → seguir el pipeline (sin VLM), no cortar el webhook.
        if cap_ok:
            _log.info(
                "telegram_inbound tag=VLM_MIME_PASSTHROUGH_CAPTION chat_id=%s mime=%s caption_len=%s",
                chat_id,
                (mime_type or "unknown")[:128],
                len(text or ""),
            )
            out_text = text
            fid = (visual.get("file_id") or "").strip()
            if mime_type == "application/pdf" and fid and token_v:
                try:
                    pdf_raw = await telegram_download_file_bytes(
                        token_v,
                        fid,
                        max_bytes=telegram_document_download_limit_bytes(),
                    )
                    extracted = extract_pdf_plain_text_from_bytes(pdf_raw)
                    if extracted.strip():
                        out_text = (
                            f"{text}\n\n"
                            "[CONTENIDO_TEXTO_EXTRAIDO_PDF]\n"
                            f"{extracted.strip()}\n"
                        )
                        _log.info(
                            "telegram_inbound tag=PDF_TEXT_EXTRACTED chat_id=%s chars=%s",
                            chat_id,
                            len(extracted.strip()),
                        )
                except Exception as exc:  # noqa: BLE001
                    _log.warning("telegram_inbound pdf extract: %s", exc)
            if out_text is text:
                meta = (
                    f"[META: ATTACHED_DOCUMENT_NOT_PARSED mime={(mime_type or 'unknown')[:80]}] "
                    "El adjunto no aportó texto utilizable en el gateway (no es imagen VLM; PDF vacío/escaneado "
                    "u otro formato sin extractor). Prohibido inventar contenido del archivo; sintetiza solo el caption.\n\n"
                )
                out_text = meta + text
            return out_text, False
        return text, True

    mgid = (visual.get("media_group_id") or "").strip()
    try:
        _log.info(
            "telegram_inbound tag=VLM_PAYLOAD_RECEIVED tenant_id=%s chat_id=%s user_id=%s "
            "file_id_prefix=%s caption_len=%s from_reply=%s mgid=%s private_dm=%s",
            tenant_id,
            chat_id,
            user_id,
            str(visual.get("file_id") or "")[:16],
            len(text or ""),
            visual_from_parent_reply,
            mgid or "-",
            private_dm,
        )
        out: dict[str, Any] | None = None
        use_album = bool(mgid and redis_client is not None)
        if use_album:
            album_items = await _wr_vlm_collect_album_items(
                redis_client,
                tenant_id=tenant_id,
                media_group_id=mgid,
                file_id=(visual.get("file_id") or "").strip(),
                mime_type=mime_type or "image/jpeg",
                caption=text,
            )
            if album_items is None:
                return text, False
            if not album_items:
                return text, False
            cap_merged = next((it["cap"] for it in album_items if it.get("cap")), "") or text
            if len(album_items) == 1:
                one = album_items[0]
                out = await process_visual_payload(
                    bot_token=token_v,
                    file_id=one["file_id"],
                    caption=cap_merged,
                    mime_type=one["mime"],
                    media_group_id=mgid,
                )
            else:
                pairs = [(it["file_id"], it["mime"]) for it in album_items]
                out = await process_visual_album_batch(
                    bot_token=token_v,
                    items=pairs,
                    caption=cap_merged,
                    media_group_id=mgid,
                )
        else:
            out = await process_visual_payload(
                bot_token=token_v,
                file_id=(visual.get("file_id") or "").strip(),
                caption=text,
                mime_type=(mime_type or "image/jpeg"),
                media_group_id=mgid,
            )
        if out and out.get("vlm_summary"):
            enriched = (
                f"Usuario dice: {text or '(sin caption)'}\n"
                f"Contexto visual adjunto: {out['vlm_summary']}\n"
                f"[VLM_CONTEXT image_hash={out.get('image_hash','')} confidence={out.get('confidence_score',0.0)}]"
            ).strip()
            if redis_client is not None:
                await push_vlm_state_delta_redis(
                    redis_client,
                    tenant_id=tenant_id,
                    image_hash=str(out.get("image_hash") or ""),
                    vlm_summary=str(out["vlm_summary"]),
                    confidence_score=float(out.get("confidence_score", 0.0)),
                )
            _log.info(
                "vlm tag=extracted tenant_id=%s album=%s count=%s hash_prefix=%s private_dm=%s",
                tenant_id,
                bool(mgid),
                int(out.get("image_count", 1)),
                str(out.get("image_hash") or "")[:12],
                private_dm,
            )
            return enriched, False
    except Exception as exc:  # noqa: BLE001
        if isinstance(exc, VLMBackendUnavailableError):
            try:
                c = TelegramBotApiAsyncClient(token_v)
                await c.send_message(chat_id=chat_id, text=str(exc))
            except Exception as send_exc:  # noqa: BLE001
                _log.warning("VLM unavailable send_message failed: %s", send_exc)
            return text, True
        _log.warning("VLM ingest falló (private_dm=%s): %s", private_dm, exc)
    return text, False


def _extract_visual_payload(msg: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {
        "file_id": "",
        "mime_type": "",
        "media_group_id": str(msg.get("media_group_id") or "").strip(),
    }
    photo = msg.get("photo")
    if isinstance(photo, list) and photo:
        best = photo[-1] if isinstance(photo[-1], dict) else photo[0]
        if isinstance(best, dict):
            out["file_id"] = str(best.get("file_id") or "").strip()
        out["mime_type"] = "image/jpeg"
        return out
    doc = msg.get("document")
    if isinstance(doc, dict):
        out["file_id"] = str(doc.get("file_id") or "").strip()
        out["mime_type"] = str(doc.get("mime_type") or "").strip().lower()
    return out


def _extract_visual_payload_with_reply(msg: dict[str, Any]) -> tuple[dict[str, str], bool]:
    """
    Si el usuario responde a un mensaje con foto/documento visual, hereda file_id para VLM.
    Así un hilo \"foto → @bot analiza\" funciona cuando el segundo mensaje es respuesta a la foto.
    """
    visual = _extract_visual_payload(msg)
    if visual.get("file_id"):
        return visual, False
    rtm = msg.get("reply_to_message")
    if not isinstance(rtm, dict):
        return visual, False
    pv = _extract_visual_payload(rtm)
    if not pv.get("file_id"):
        return visual, False
    return pv, True


KNOWN_TELEGRAM_PATH_WEBHOOK_ROUTES = frozenset(
    {"finanz", "finanzas", "trabajo", "jobhunter", "job-hunter"}
)


def _telegram_path_route_family(route_key: str | None) -> str | None:
    if not (route_key or "").strip():
        return None
    rk = str(route_key).strip().lower()
    if rk in ("finanz", "finanzas"):
        return "finanz"
    if rk in ("trabajo", "jobhunter", "job-hunter"):
        return "trabajo"
    return None


def _webhook_secret_ok_finanz_path(header_secret: str | None) -> bool:
    fin = (os.environ.get("TELEGRAM_WEBHOOK_SECRET_FINANZ") or "").strip()
    leg = (os.environ.get("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    hdr = (header_secret or "").strip()
    if fin:
        return bool(hdr) and secrets.compare_digest(hdr, fin)
    if leg:
        return bool(hdr) and secrets.compare_digest(hdr, leg)
    return True


def _telegram_multipart_tail_sync_stub(*, chat_id: str, user_id: str, text: str) -> None:
    """Firma requerida por ``dispatch_telegram_multipart_tail_async``; salida solo nativa/MCP."""
    del chat_id, user_id, text


def _webhook_secret_ok_trabajo_path(header_secret: str | None) -> bool:
    job = (os.environ.get("TELEGRAM_WEBHOOK_SECRET_TRABAJO") or "").strip()
    leg = (os.environ.get("TELEGRAM_WEBHOOK_SECRET") or "").strip()
    hdr = (header_secret or "").strip()
    if job:
        return bool(hdr) and secrets.compare_digest(hdr, job)
    if leg:
        return bool(hdr) and secrets.compare_digest(hdr, leg)
    return True


def build_telegram_inbound_webhook_router(
    *,
    invoke_agent_chat: Callable[..., Awaitable[Any]],
    resolve_effective_telegram_bot_token: Callable[[], str],
) -> APIRouter:
    """
    Factory para no importar ``main`` desde este módulo (evita ciclos).

    - invoke_agent_chat: típicamente ``_invoke_chat`` del gateway.

    Rutas adicionales ``…/webhook/finanz`` y ``…/webhook/trabajo`` (legado): mismo host cuando un solo
    funnel recibe todos los bots; ``secret_token`` por bot
    (``TELEGRAM_WEBHOOK_SECRET_FINANZ`` / ``TELEGRAM_WEBHOOK_SECRET_TRABAJO`` o ``TELEGRAM_WEBHOOK_SECRET``).
    Modo recomendado: un webhook estándar ``…/webhook`` por gateway y URL pública que termine en el puerto
    PM2 de ese proceso (sin depender de estas rutas).
    """

    router = APIRouter(prefix="/api/v1/telegram", tags=["telegram-inbound-webhook"])

    _compact_path_bindings: list[TelegramPathWebhookBinding] = []
    _raw_compact_routes = (os.environ.get("DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES") or "").strip()
    if _raw_compact_routes and not _raw_compact_routes.startswith("[") and ":/api/" in _raw_compact_routes:
        try:
            _compact_path_bindings = load_path_webhook_bindings_from_env()
        except ValueError as exc:
            _log.error(
                "DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES (compacto) inválido; arranca el gateway tras corregir .env: %s",
                exc,
            )
            raise RuntimeError(f"DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES compacto inválido: {exc}") from exc

    async def _telegram_webhook_core(
        request: Request,
        path_route_raw: str | None,
    ) -> dict[str, str]:
        header_secret = request.headers.get(TELEGRAM_WEBHOOK_SECRET_HTTP_HEADER)
        default_token = (resolve_effective_telegram_bot_token() or "").strip()

        path_family = _telegram_path_route_family(path_route_raw)
        worker_id: str
        tenant_id: str
        reply_token: str
        multiplex_forced_vault: str | None = None

        path_mux: TelegramPathWebhookBinding | None = getattr(
            request.state, "duckclaw_telegram_path_binding", None
        )
        if path_mux is not None:
            worker_id = path_mux.worker_id
            tenant_id = path_mux.tenant_id
            reply_token = path_mux.bot_token
            multiplex_forced_vault = path_mux.forced_vault_db_path
            _log.info(
                "telegram path multiplex: request bot_name=%s worker_id=%s tenant_id=%s path=%s",
                path_mux.bot_name,
                worker_id,
                tenant_id,
                path_mux.webhook_path,
            )
        elif path_family == "finanz":
            if not _webhook_secret_ok_finanz_path(header_secret):
                _log.warning(
                    "telegram webhook: 403 — path finanz: cabecera %s inválida.",
                    TELEGRAM_WEBHOOK_SECRET_HTTP_HEADER,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "type": "about:blank",
                        "title": "Forbidden",
                        "status": 403,
                        "detail": "Secreto de webhook de Telegram inválido o ausente (ruta finanz).",
                    },
                )
            worker_id = (os.environ.get("DUCKCLAW_TELEGRAM_FINANZ_ENTRY_WORKER") or "finanz").strip()
            tenant_id = (os.environ.get("DUCKCLAW_FINANZ_TENANT_ID") or "Finanzas").strip()
            # Multiplex: TELEGRAM_FINANZ_TOKEN explícito. Gateway dedicado Finanz suele tener solo
            # TELEGRAM_BOT_TOKEN; sin fallback las respuestas usan un token viejo en PM2 JSON y el
            # mensaje aparece en el chat del otro bot (mismo user_id en DM).
            reply_token = (os.environ.get("TELEGRAM_FINANZ_TOKEN") or "").strip()
            if not reply_token:
                reply_token = default_token
            if not reply_token:
                _log.error(
                    "telegram webhook path finanz: falta TELEGRAM_FINANZ_TOKEN y token efectivo del proceso"
                )
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "type": "about:blank",
                        "title": "Server Error",
                        "status": 500,
                        "detail": "Sin token de bot: configure TELEGRAM_FINANZ_TOKEN o TELEGRAM_BOT_TOKEN.",
                    },
                )
        elif path_family == "trabajo":
            if not _webhook_secret_ok_trabajo_path(header_secret):
                _log.warning(
                    "telegram webhook: 403 — path trabajo: cabecera %s inválida.",
                    TELEGRAM_WEBHOOK_SECRET_HTTP_HEADER,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "type": "about:blank",
                        "title": "Forbidden",
                        "status": 403,
                        "detail": "Secreto de webhook de Telegram inválido o ausente (ruta trabajo).",
                    },
                )
            worker_id = (os.environ.get("DUCKCLAW_DEFAULT_WORKER_ID") or "Job-Hunter").strip()
            tenant_id = (os.environ.get("DUCKCLAW_GATEWAY_TENANT_ID") or "trabajo").strip()
            reply_token = (
                os.environ.get("TELEGRAM_JOB_HUNTER_TOKEN")
                or os.environ.get("TELEGRAM_BOT_TOKEN")
                or ""
            ).strip()
            if not reply_token:
                _log.error("telegram webhook path trabajo: falta TELEGRAM_JOB_HUNTER_TOKEN")
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail={
                        "type": "about:blank",
                        "title": "Server Error",
                        "status": 500,
                        "detail": "TELEGRAM_JOB_HUNTER_TOKEN no configurado.",
                    },
                )
        else:
            resolved = telegram_webhook_resolve_dispatch(
                header_secret,
                default_worker_id=_telegram_webhook_default_worker_id(),
                default_tenant_id=_telegram_webhook_default_tenant_id(),
                default_bot_token=default_token,
            )
            if resolved == "reject":
                _log.warning(
                    "telegram webhook: 403 — cabecera %s no coincide con TELEGRAM_WEBHOOK_SECRET ni con "
                    "ninguna entrada de DUCKCLAW_TELEGRAM_WEBHOOK_ROUTES.",
                    TELEGRAM_WEBHOOK_SECRET_HTTP_HEADER,
                )
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "type": "about:blank",
                        "title": "Forbidden",
                        "status": 403,
                        "detail": "Secreto de webhook de Telegram inválido o ausente.",
                    },
                )

            if isinstance(resolved, TelegramWebhookResolvedDispatch):
                worker_id = resolved.worker_id
                tenant_id = resolved.tenant_id
                reply_token = resolved.bot_token
                multiplex_forced_vault = resolved.forced_vault_db_path
            else:
                _tag, worker_id, tenant_id, reply_token = resolved

        # Misma regla que SIATA/jobhunter: multiplex primero; legado finanz solo con DUCKCLAW_FINANZ_DB_PATH.
        telegram_forced_vault_db_path: str | None = None
        if multiplex_forced_vault:
            telegram_forced_vault_db_path = multiplex_forced_vault
        elif path_family == "finanz":
            _v = (os.environ.get("DUCKCLAW_FINANZ_DB_PATH") or "").strip()
            telegram_forced_vault_db_path = resolve_env_duckdb_path(_v) if _v else None

        _log.info(
            "telegram_webhook_dispatch secret_fp=%s worker_id=%s tenant_id=%s path_route=%s",
            telegram_webhook_header_fingerprint(header_secret),
            worker_id,
            tenant_id,
            (path_route_raw or "").strip() or "(default)",
        )

        try:
            body = await request.json()
        except json.JSONDecodeError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "type": "about:blank",
                    "title": "Bad Request",
                    "status": 400,
                    "detail": "Cuerpo JSON inválido.",
                },
            )

        early_msg = body.get("message") or body.get("edited_message")
        early_chat_id = None
        if isinstance(early_msg, dict):
            _ec = early_msg.get("chat") or {}
            if isinstance(_ec, dict):
                early_chat_id = _ec.get("id")
        _em = early_msg if isinstance(early_msg, dict) else None
        update_id = body.get("update_id")
        _log.info(
            "telegram_inbound_early update_id=%s chat_id=%s has_photo=%s has_document=%s "
            "text_len=%s caption_len=%s reply_to_message=%s",
            update_id,
            early_chat_id,
            bool(_em and _em.get("photo")),
            bool(_em and _em.get("document")),
            len(str((_em.get("text") if _em else None) or "")),
            len(str((_em.get("caption") if _em else None) or "")),
            bool(_em and _em.get("reply_to_message")),
        )

        redis_client = getattr(request.app.state, "redis", None)
        if update_id is not None and redis_client is not None:
            _fp = telegram_webhook_header_fingerprint(header_secret)
            dedupe_key = f"{_TELEGRAM_WEBHOOK_DEDUPE_KEY_PREFIX}:{_fp}:{update_id}"
            try:
                first_time = await redis_client.set(
                    dedupe_key,
                    "1",
                    nx=True,
                    ex=_TELEGRAM_WEBHOOK_DEDUPE_TTL_SECONDS,
                )
                if not first_time:
                    _log.info(
                        "telegram_inbound_dedupe_drop update_id=%s chat_id=%s",
                        update_id,
                        early_chat_id,
                    )
                    return {"ok": "true"}
            except Exception as exc:  # noqa: BLE001
                _log.warning("telegram webhook dedupe omitido (redis): %s", exc)

        msg = body.get("message") or body.get("edited_message")
        if not isinstance(msg, dict):
            return {"ok": "true"}

        chat = msg.get("chat") or {}
        if not isinstance(chat, dict):
            return {"ok": "true"}
        chat_id = chat.get("id")
        if chat_id is None:
            return {"ok": "true"}

        text = (msg.get("text") or msg.get("caption") or "").strip()
        telegram_raw_caption = text
        tg_entities = _telegram_entities_for_message(msg)
        visual, visual_from_parent_reply = _extract_visual_payload_with_reply(msg)
        has_visual = bool(visual.get("file_id"))
        is_slash_command = text.startswith("/")
        from_user = msg.get("from") if isinstance(msg.get("from"), dict) else {}
        user_id_raw = from_user.get("id")
        user_id = str(user_id_raw if user_id_raw is not None else chat_id)
        username = str(
            from_user.get("username")
            or from_user.get("first_name")
            or from_user.get("last_name")
            or "Usuario"
        )
        chat_type = str(chat.get("type") or "private")
        tenant_id = war_room_tenant_for_chat(chat_type, chat_id, tenant_id)

        # DM / chat privado: fotos/álbumes pasan por VLM (no solo War Rooms).
        if has_visual and not is_war_room_tenant(tenant_id):
            token_v = (reply_token or "").strip() or (
                resolve_effective_telegram_bot_token() or ""
            ).strip()
            if not token_v:
                _log.warning("telegram inbound: imagen en DM sin token de bot")
            else:
                text, drop_early = await _ingest_telegram_visual_enrich_text(
                    text=text,
                    visual=visual,
                    visual_from_parent_reply=visual_from_parent_reply,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    chat_id=chat_id,
                    token_v=token_v,
                    redis_client=redis_client,
                    private_dm=True,
                )
                if drop_early:
                    return {"ok": "true"}
            if has_visual and not (text or "").strip():
                text = (
                    "[META: VLM_GATEWAY_DOWN] El usuario envió una imagen por Telegram (sin caption); "
                    "el servicio de visión del gateway no produjo resumen (p. ej. MLX en "
                    "DUCKCLAW_VLM_MLX_BASE_URL inactivo y sin OPENAI_API_KEY de respaldo). "
                    "No hay bloque [VLM_CONTEXT]. Pide una descripción breve del contenido. "
                    "No afirmes que no puedes procesar imágenes: aquí falló la ingesta VLM, no el rol del asistente."
                )

        # War Rooms: grupos/supergrupos usan tenant soberano wr_<group_id>.
        if is_war_room_tenant(tenant_id):
            from core.gateway_acl_db import get_war_room_acl_duckdb

            db = get_war_room_acl_duckdb()
            sender_is_owner = bool(
                str(user_id or "").strip()
                and str(user_id).strip()
                == str(os.environ.get("DUCKCLAW_OWNER_ID") or os.environ.get("DUCKCLAW_ADMIN_CHAT_ID") or "").strip()
            )
            sender_is_member = wr_has_member(db, tenant_id, user_id)
            group_has_members = wr_members_count(db, tenant_id) > 0
            bootstrap_mode = not group_has_members

            if not bootstrap_mode and not sender_is_member and not sender_is_owner:
                event = "UNAUTHORIZED_COMMAND_ATTEMPT" if is_slash_command else "UNAUTHORIZED_MEMBER"
                _log.info("war_room_filter tag=unauthorized_member tenant_id=%s user_id=%s", tenant_id, user_id)
                wr_append_audit(
                    db,
                    tenant_id=tenant_id,
                    sender_id=user_id,
                    target_agent=None,
                    event_type=event,
                    payload=(text or f"chat_id={chat_id}")[:1000],
                )
                return {"ok": "true"}
            if bootstrap_mode:
                wr_append_audit(
                    db,
                    tenant_id=tenant_id,
                    sender_id=user_id,
                    target_agent=None,
                    event_type="BOOTSTRAP_MODE",
                    payload="wr_members vacío: zero-trust y mention-gate relajados temporalmente",
                )

            # Mention gate ANTES del rate limit: los drops no consumen cupo anti-spam.
            current_bot_username = normalize_telegram_bot_username(settings.TELEGRAM_BOT_USERNAME)
            if not current_bot_username:
                _log.warning(
                    "war_room_gate: TELEGRAM_BOT_USERNAME vacío en settings; las menciones solo "
                    "coincidirán con texto literal @user o 'duckclaw' (configure .env)."
                )
            wr_gate = war_room_evaluate_mention_gate(
                combined_text=text,
                entities=tg_entities,
                has_visual_media=has_visual,
                current_bot_username=settings.TELEGRAM_BOT_USERNAME,
                bootstrap_mode=bootstrap_mode,
            )
            if not wr_gate.allowed:
                _log.info(
                    "war_room_gate decision=%s tenant_id=%s user_id=%s chat_id=%s has_visual=%s text_preview=%s",
                    wr_gate.decision,
                    tenant_id,
                    user_id,
                    chat_id,
                    has_visual,
                    (text or "")[:120],
                )
                wr_append_audit(
                    db,
                    tenant_id=tenant_id,
                    sender_id=user_id,
                    target_agent=None,
                    event_type="DROP_NO_MENTION",
                    payload=(
                        f"decision={wr_gate.decision};visual={has_visual}:{(visual.get('mime_type') or '')}"[:1000]
                    ),
                )
                return {"ok": "true"}
            _log.info(
                "war_room_gate decision=%s tenant_id=%s user_id=%s chat_id=%s has_visual=%s bot_user=%s",
                wr_gate.decision,
                tenant_id,
                user_id,
                chat_id,
                has_visual,
                current_bot_username or "(unset)",
            )
            wr_append_audit(
                db,
                tenant_id=tenant_id,
                sender_id=user_id,
                target_agent=None,
                event_type=wr_gate.decision,
                payload=(text or "")[:1000],
            )

            # Fly commands no cuentan para anti-spam (deben seguir operativos bajo carga).
            if not is_slash_command:
                is_allowed, notify_cooldown, ttl = await hit_rate_limit(
                    redis_client,
                    tenant_id=tenant_id,
                    user_id=user_id,
                    cooldown_seconds=300,
                )
                if not is_allowed:
                    if notify_cooldown:
                        _log.info(
                            "war_room_filter tag=rate_limited_notified tenant_id=%s user_id=%s",
                            tenant_id,
                            user_id,
                        )
                        token_rl = (reply_token or "").strip() or (resolve_effective_telegram_bot_token() or "").strip()
                        if token_rl:
                            try:
                                client_rl = TelegramBotApiAsyncClient(token_rl)
                                await client_rl.send_message(
                                    chat_id=chat_id,
                                    text=f"Cooldown activo. Intenta de nuevo en {max(1, int(ttl))} segundos.",
                                    parse_mode=None,
                                )
                            except Exception as send_exc:  # noqa: BLE001
                                _log.warning("telegram webhook cooldown notify falló: %s", send_exc)
                        wr_append_audit(
                            db,
                            tenant_id=tenant_id,
                            sender_id=user_id,
                            target_agent=None,
                            event_type="RATE_LIMIT_NOTIFIED",
                            payload=(text or "")[:1000],
                        )
                    else:
                        _log.info(
                            "war_room_filter tag=rate_limited_silenced tenant_id=%s user_id=%s",
                            tenant_id,
                            user_id,
                        )
                        wr_append_audit(
                            db,
                            tenant_id=tenant_id,
                            sender_id=user_id,
                            target_agent=None,
                            event_type="RATE_LIMIT_SILENCED",
                            payload=(text or "")[:1000],
                        )
                    return {"ok": "true"}

            if has_visual:
                if visual_from_parent_reply:
                    _log.info(
                        "war_room_filter tag=visual_from_reply tenant_id=%s user_id=%s",
                        tenant_id,
                        user_id,
                    )
                mime_type = (visual.get("mime_type") or "").strip().lower()
                skip_vlm = False
                if mime_type and mime_type not in _VISUAL_ALLOWED_MIME:
                    wr_append_audit(
                        db,
                        tenant_id=tenant_id,
                        sender_id=user_id,
                        target_agent=None,
                        event_type="VLM_MIME_REJECTED",
                        payload=(mime_type or "unknown")[:128],
                    )
                    cap_ok_wr = bool((text or "").strip())
                    if not cap_ok_wr:
                        return {"ok": "true"}
                    skip_vlm = True
                    _log.info(
                        "war_room_filter tag=VLM_MIME_PASSTHROUGH_CAPTION tenant_id=%s mime=%s caption_len=%s",
                        tenant_id,
                        (mime_type or "unknown")[:128],
                        len(text or ""),
                    )
                token_v = (reply_token or "").strip() or (resolve_effective_telegram_bot_token() or "").strip()
                mgid = (visual.get("media_group_id") or "").strip()
                if token_v and not skip_vlm:
                    try:
                        _log.info(
                            "war_room inbound tag=VLM_PAYLOAD_RECEIVED tenant_id=%s user_id=%s "
                            "file_id_prefix=%s caption_len=%s from_reply=%s mgid=%s",
                            tenant_id,
                            user_id,
                            str(visual.get("file_id") or "")[:16],
                            len(text or ""),
                            visual_from_parent_reply,
                            mgid or "-",
                        )
                        wr_append_audit(
                            db,
                            tenant_id=tenant_id,
                            sender_id=user_id,
                            target_agent=None,
                            event_type="VLM_PAYLOAD_RECEIVED",
                            payload=(visual.get("mime_type") or "image/jpeg")[:128],
                        )
                        out: dict[str, Any] | None = None
                        use_album = bool(mgid and redis_client is not None)
                        if use_album:
                            album_items = await _wr_vlm_collect_album_items(
                                redis_client,
                                tenant_id=tenant_id,
                                media_group_id=mgid,
                                file_id=(visual.get("file_id") or "").strip(),
                                mime_type=mime_type or "image/jpeg",
                                caption=text,
                            )
                            if album_items is None:
                                return {"ok": "true"}
                            if not album_items:
                                return {"ok": "true"}
                            cap_merged = next((it["cap"] for it in album_items if it.get("cap")), "") or text
                            if len(album_items) == 1:
                                one = album_items[0]
                                out = await process_visual_payload(
                                    bot_token=token_v,
                                    file_id=one["file_id"],
                                    caption=cap_merged,
                                    mime_type=one["mime"],
                                    media_group_id=mgid,
                                )
                            else:
                                pairs = [(it["file_id"], it["mime"]) for it in album_items]
                                out = await process_visual_album_batch(
                                    bot_token=token_v,
                                    items=pairs,
                                    caption=cap_merged,
                                    media_group_id=mgid,
                                )
                        else:
                            out = await process_visual_payload(
                                bot_token=token_v,
                                file_id=(visual.get("file_id") or "").strip(),
                                caption=text,
                                mime_type=(mime_type or "image/jpeg"),
                                media_group_id=mgid,
                            )
                        if out and out.get("vlm_summary"):
                            text = (
                                f"Usuario dice: {text or '(sin caption)'}\n"
                                f"Contexto visual adjunto: {out['vlm_summary']}\n"
                                f"[VLM_CONTEXT image_hash={out.get('image_hash','')} confidence={out.get('confidence_score',0.0)}]"
                            ).strip()
                            await push_vlm_state_delta_redis(
                                redis_client,
                                tenant_id=tenant_id,
                                image_hash=str(out.get("image_hash") or ""),
                                vlm_summary=str(out["vlm_summary"]),
                                confidence_score=float(out.get("confidence_score", 0.0)),
                            )
                            wr_append_audit(
                                db,
                                tenant_id=tenant_id,
                                sender_id=user_id,
                                target_agent=None,
                                event_type="VLM_CONTEXT_EXTRACTED",
                                payload=str(out.get("image_hash") or "")[:256],
                            )
                            _log.info(
                                "vlm tag=extracted tenant_id=%s album=%s count=%s hash_prefix=%s",
                                tenant_id,
                                bool(mgid),
                                int(out.get("image_count", 1)),
                                str(out.get("image_hash") or "")[:12],
                            )
                    except Exception as exc:  # noqa: BLE001
                        if isinstance(exc, VLMBackendUnavailableError):
                            try:
                                client_vlm = TelegramBotApiAsyncClient(token_v)
                                await client_vlm.send_message(chat_id=chat_id, text=str(exc))
                            except Exception as send_exc:  # noqa: BLE001
                                _log.warning("war_room VLM unavailable send failed: %s", send_exc)
                            return {"ok": "true"}
                        _log.warning("VLM ingest falló: %s", exc)
                        wr_append_audit(
                            db,
                            tenant_id=tenant_id,
                            sender_id=user_id,
                            target_agent=None,
                            event_type="VLM_INGEST_FAILED",
                            payload=str(exc)[:500],
                        )

        is_ctx_add, ctx_body = _resolve_context_add_body(
            raw_caption=telegram_raw_caption,
            current_text=text,
        )
        if is_ctx_add:
            token_ctx = (reply_token or "").strip() or (resolve_effective_telegram_bot_token() or "").strip()

            async def _send_ctx_reply(html: str) -> None:
                if not token_ctx:
                    _log.warning("context_injection: sin token de bot para responder")
                    return
                try:
                    c = TelegramBotApiAsyncClient(token_ctx)
                    await c.send_message(chat_id=chat_id, text=html, parse_mode="HTML")
                except Exception as exc:  # noqa: BLE001
                    _log.warning("context_injection send_message failed: %s", exc)

            if not ctx_body:
                await _send_ctx_reply(
                    llm_markdown_to_telegram_html(
                        "Uso: `/context --add` requiere texto después de `--add`."
                    )
                )
                return {"ok": "true"}

            vault_uid = str(user_id or "").strip() or str(chat_id)
            if not user_may_context_inject(
                tenant_id=tenant_id,
                user_id=vault_uid,
                telegram_guard_acl_db_path=telegram_forced_vault_db_path,
            ):
                await _send_ctx_reply(
                    llm_markdown_to_telegram_html(
                        "No autorizado: solo administradores pueden usar `/context --add`."
                    )
                )
                return {"ok": "true"}

            try:
                target_db = resolve_telegram_user_vault_db_path(
                    tenant_id=tenant_id,
                    vault_user_id=vault_uid,
                    telegram_forced_vault_db_path=telegram_forced_vault_db_path,
                )
                delta = build_context_injection_delta(
                    tenant_id=tenant_id,
                    raw_text=ctx_body,
                    user_id=vault_uid,
                    target_db_path=target_db,
                )
            except Exception as exc:  # noqa: BLE001
                _log.exception("context_injection prepare failed: %s", exc)
                await _send_ctx_reply(
                    llm_markdown_to_telegram_html("No se pudo preparar la inyección de contexto.")
                )
                return {"ok": "true"}

            if redis_client is None:
                _log.error("context_injection: Redis no disponible; no se puede encolar CONTEXT_INJECTION")
                await _send_ctx_reply(
                    llm_markdown_to_telegram_html(
                        "Error interno: Redis no está configurado; el contexto no se pudo encolar para persistir."
                    )
                )
                return {"ok": "true"}

            try:
                await push_context_injection_delta_redis(redis_client, delta)
                _log.info(
                    "context_injection LPUSH ok queue=%s tenant=%s user=%s db=%s",
                    context_injection_queue_key(),
                    tenant_id,
                    vault_uid,
                    target_db,
                )
            except Exception as exc:  # noqa: BLE001
                _log.exception("context_injection LPUSH falló: %s", exc)
                await _send_ctx_reply(
                    llm_markdown_to_telegram_html(
                        "No se pudo encolar el contexto en Redis; revisa logs del gateway y que DuckClaw-DB-Writer esté activo."
                    )
                )
                return {"ok": "true"}

            telegram_mcp_state = getattr(request.app.state, "telegram_mcp", None)
            _redis_sess_ctx = f"{path_mux.bot_name}:{chat_id}" if path_mux is not None else str(chat_id)
            schedule_telegram_context_summary_background(
                directive_msg=_summarize_new_context_directive(ctx_body),
                telegram_header_html="<b>Resumen del contexto inyectado</b>\n\n",
                log_label="SUMMARIZE_NEW_CONTEXT",
                invoke_agent_chat=invoke_agent_chat,
                resolve_effective_telegram_bot_token=resolve_effective_telegram_bot_token,
                worker_id=worker_id,
                chat_id=chat_id,
                tenant_id=tenant_id,
                vault_uid=vault_uid,
                username=username,
                chat_type=chat_type,
                redis_client=redis_client,
                telegram_mcp_state=telegram_mcp_state,
                telegram_forced_vault_db_path=telegram_forced_vault_db_path,
                reply_token=reply_token,
                redis_session_id=_redis_sess_ctx,
            )

            await _send_ctx_reply(
                llm_markdown_to_telegram_html(
                    "Contexto encolado para memoria semántica. Resumen en segundo plano."
                )
            )
            return {"ok": "true"}

        if _parse_context_summary_command(text):
            token_sum = (reply_token or "").strip() or (resolve_effective_telegram_bot_token() or "").strip()

            async def _send_ctx_summary_reply(html: str) -> None:
                if not token_sum:
                    _log.warning("context_summary: sin token de bot para responder")
                    return
                try:
                    c = TelegramBotApiAsyncClient(token_sum)
                    await c.send_message(chat_id=chat_id, text=html, parse_mode="HTML")
                except Exception as exc:  # noqa: BLE001
                    _log.warning("context_summary send_message failed: %s", exc)

            vault_uid_sum = str(user_id or "").strip() or str(chat_id)
            if not user_may_context_inject(
                tenant_id=tenant_id,
                user_id=vault_uid_sum,
                telegram_guard_acl_db_path=telegram_forced_vault_db_path,
            ):
                await _send_ctx_summary_reply(
                    llm_markdown_to_telegram_html(
                        "No autorizado: solo administradores pueden usar `/context --summary`."
                    )
                )
                return {"ok": "true"}

            try:
                target_db_sum = resolve_telegram_user_vault_db_path(
                    tenant_id=tenant_id,
                    vault_user_id=vault_uid_sum,
                    telegram_forced_vault_db_path=telegram_forced_vault_db_path,
                )
            except Exception as exc:  # noqa: BLE001
                _log.exception("context_summary resolve vault failed: %s", exc)
                await _send_ctx_summary_reply(
                    llm_markdown_to_telegram_html("No se pudo resolver la bóveda DuckDB para leer contexto.")
                )
                return {"ok": "true"}

            snapshot = fetch_semantic_memory_snapshot(target_db_sum)
            if not (snapshot or "").strip():
                pending_ctx = 0
                qkey = context_injection_queue_key()
                if redis_client is not None:
                    try:
                        pending_ctx = int(await redis_client.llen(qkey))
                    except Exception:  # noqa: BLE001
                        pending_ctx = 0
                if pending_ctx > 0:
                    empty_msg = (
                        f"No hay filas aún en `main.semantic_memory`, pero hay **{pending_ctx}** inyección(es) "
                        f"en cola Redis (`{qkey}`). El **db-writer** debe estar en ejecución para persistir; "
                        "si solo corre el gateway, los `/context --add` quedan encolados."
                    )
                else:
                    empty_msg = (
                        "No hay filas en `main.semantic_memory` en esta bóveda (o la tabla aún no existe). "
                        "Inyecta contexto con `/context --add …` primero."
                    )
                await _send_ctx_summary_reply(llm_markdown_to_telegram_html(empty_msg))
                return {"ok": "true"}

            telegram_mcp_sum = getattr(request.app.state, "telegram_mcp", None)
            _redis_sess_sum = f"{path_mux.bot_name}:{chat_id}" if path_mux is not None else str(chat_id)
            schedule_telegram_context_summary_background(
                directive_msg=_summarize_stored_context_directive(snapshot),
                telegram_header_html="<b>Resumen del contexto (base de datos)</b>\n\n",
                log_label="SUMMARIZE_STORED_CONTEXT",
                invoke_agent_chat=invoke_agent_chat,
                resolve_effective_telegram_bot_token=resolve_effective_telegram_bot_token,
                worker_id=worker_id,
                chat_id=chat_id,
                tenant_id=tenant_id,
                vault_uid=vault_uid_sum,
                username=username,
                chat_type=chat_type,
                redis_client=redis_client,
                telegram_mcp_state=telegram_mcp_sum,
                telegram_forced_vault_db_path=telegram_forced_vault_db_path,
                reply_token=reply_token,
                redis_session_id=_redis_sess_sum,
            )
            await _send_ctx_summary_reply(
                llm_markdown_to_telegram_html(
                    "Leyendo `main.semantic_memory` desde DuckDB (solo lectura). Resumen en segundo plano."
                )
            )
            return {"ok": "true"}

        payload = ChatRequest(
            message=text,
            chat_id=str(chat_id),
            user_id=user_id,
            username=username,
            chat_type=chat_type,
            tenant_id=tenant_id,
        )

        # Evita colisión de estado entre bots distintos en el mismo chat_id de Telegram (DM).
        # En multiplex por path, usamos sesión namespaced por bot/worker.
        if path_mux is not None:
            session_id = f"{path_mux.bot_name}:{chat_id}"
        else:
            session_id = str(chat_id)
        telegram_mcp = getattr(request.app.state, "telegram_mcp", None)

        async def _invoke_and_reply() -> None:
            try:
                res = await invoke_agent_chat(
                    payload,
                    worker_id,
                    session_id,
                    tenant_id,
                    redis_client=redis_client,
                    telegram_multipart_tail_delivery="native",
                    telegram_mcp=telegram_mcp,
                    telegram_forced_vault_db_path=telegram_forced_vault_db_path,
                    outbound_telegram_bot_token=(reply_token or "").strip() or None,
                )
            except HTTPException as exc:
                detail = exc.detail
                if isinstance(detail, dict):
                    msg_err = str(detail.get("detail") or detail)
                else:
                    msg_err = str(detail)
                _log.warning("telegram webhook invoke falló: %s", msg_err)
                token_e = (reply_token or "").strip() or (resolve_effective_telegram_bot_token() or "").strip()
                if token_e and msg_err:
                    try:
                        client_e = TelegramBotApiAsyncClient(token_e)
                        await client_e.send_message(
                            chat_id=chat_id,
                            text=msg_err[:3900],
                            parse_mode=None,
                        )
                    except Exception as send_exc:  # noqa: BLE001
                        _log.warning("telegram webhook no pudo enviar error al usuario: %s", send_exc)
                return

            reply_local = (res.get("response") or "").strip() if isinstance(res, dict) else ""
            if not reply_local:
                _log.warning(
                    "telegram webhook: invoke_agent_chat devolvió respuesta vacía tenant_id=%s "
                    "chat_id=%s msg_len=%s worker_id=%s",
                    tenant_id,
                    chat_id,
                    len(payload.message or ""),
                    worker_id,
                )
                return

            token_r = (reply_token or "").strip() or (resolve_effective_telegram_bot_token() or "").strip()
            if not token_r:
                _log.warning("telegram webhook: hay respuesta pero falta TELEGRAM_BOT_TOKEN")
                return

            client_r = TelegramBotApiAsyncClient(token_r)
            tail_plain = (res.get("telegram_multipart_tail_plain") or "").strip() if isinstance(res, dict) else ""
            head_plain = (res.get("telegram_reply_head_plain") or "").strip() if isinstance(res, dict) else ""
            if tail_plain and head_plain:
                reply_plain = head_plain
            else:
                mh, mt = gateway_multipart_plain_head_tail(reply_local, llm_markdown_to_telegram_html)
                if mh is not None and (mt or "").strip():
                    head_plain = mh
                    tail_plain = mt
                    reply_plain = head_plain
                else:
                    reply_plain = reply_local
            reply_html = llm_markdown_to_telegram_html(reply_plain)
            cap_msg = 4096 - 16
            if len(reply_html) > cap_msg:
                reply_html = reply_html[: max(0, cap_msg - 1)] + "…"
            sent = await client_r.send_message(
                chat_id=chat_id, text=reply_html, parse_mode="HTML"
            )
            if not sent.get("ok"):
                await client_r.send_message(
                    chat_id=chat_id,
                    text=reply_plain[:3900],
                    parse_mode=None,
                )
            if tail_plain:
                from core.telegram_multipart_tail_dispatch_async import dispatch_telegram_multipart_tail_async

                await dispatch_telegram_multipart_tail_async(
                    tail_plain=tail_plain,
                    session_id=str(chat_id),
                    user_id=(str(user_id or "").strip() or str(chat_id)),
                    telegram_multipart_tail_delivery="native",
                    effective_telegram_bot_token=resolve_effective_telegram_bot_token,
                    n8n_outbound_push_sync=_telegram_multipart_tail_sync_stub,
                    telegram_mcp=telegram_mcp,
                    redis_client=redis_client,
                    tenant_id=tenant_id,
                )

        async def _invoke_and_reply_safe() -> None:
            try:
                with telegram_bot_token_override(reply_token):
                    await _invoke_and_reply()
            except Exception as exc:  # noqa: BLE001
                _log.exception("telegram webhook: fallo en invocación en segundo plano: %s", exc)

        if _telegram_webhook_parallel_processing_enabled():
            asyncio.create_task(_invoke_and_reply_safe())
            return {"ok": "true"}

        with telegram_bot_token_override(reply_token):
            await _invoke_and_reply()
        return {"ok": "true"}

    if _compact_path_bindings:

        @router.post("/webhook")
        async def telegram_bot_update_webhook(request: Request) -> dict[str, str]:
            try:
                _body = await request.json()
                _upd = _body.get("update_id")
            except Exception:
                _upd = None
            _log.error(
                "telegram path multiplex: POST a /api/v1/telegram/webhook ignorado (no se enruta a Finanz). "
                "Los bots siguen usando la URL genérica en Telegram. Registra webhook por path: "
                "`python scripts/register_webhooks.py` con DUCKCLAW_PUBLIC_URL. "
                "Rutas configuradas: %s. update_id=%s",
                ", ".join(b.webhook_path for b in _compact_path_bindings),
                _upd,
            )
            return {"ok": "true"}

    else:

        @router.post("/webhook")
        async def telegram_bot_update_webhook(request: Request) -> dict[str, str]:
            return await _telegram_webhook_core(request, None)

    @router.post("/webhook/{route_key}")
    async def telegram_bot_update_webhook_pathed(request: Request, route_key: str) -> dict[str, str]:
        rk = (route_key or "").strip().lower()
        if rk not in KNOWN_TELEGRAM_PATH_WEBHOOK_ROUTES:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail={
                    "type": "about:blank",
                    "title": "Not Found",
                    "status": 404,
                    "detail": "Webhook path desconocido.",
                },
            )
        return await _telegram_webhook_core(request, rk)

    for _pb in _compact_path_bindings:
        _rel = fastapi_relative_path(_pb.webhook_path)

        def _make_path_handler(binding: TelegramPathWebhookBinding) -> Callable[..., Awaitable[dict[str, str]]]:
            async def _path_webhook(request: Request) -> dict[str, str]:
                request.state.duckclaw_telegram_bot_name = binding.bot_name
                request.state.duckclaw_telegram_path_binding = binding
                return await _telegram_webhook_core(request, None)

            return _path_webhook

        router.add_api_route(
            _rel,
            _make_path_handler(_pb),
            methods=["POST"],
            name=f"telegram_compact_{_pb.bot_name}",
        )
        _log.info(
            "telegram path multiplex: ruta %s registrada para el bot %s (worker_id=%s, tenant_id=%s)",
            _pb.webhook_path,
            _pb.bot_name,
            _pb.worker_id,
            _pb.tenant_id,
        )

    return router
