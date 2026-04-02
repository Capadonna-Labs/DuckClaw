# services/api-gateway/routers/telegram_inbound_webhook.py
"""
Webhook entrante de Telegram (Bot API Update) → mismo pipeline que /api/v1/agent/.../chat.

Contrato: POST ``/api/v1/telegram/webhook`` con JSON de Update; validación opcional vía
``TELEGRAM_WEBHOOK_SECRET`` y cabecera ``X-Telegram-Bot-Api-Secret-Token``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, HTTPException, Request, status

from core.config import settings
from core.models import ChatRequest
from core.vlm_ingest import (
    process_visual_album_batch,
    process_visual_payload,
    push_vlm_state_delta_redis,
)
from core.war_rooms import (
    ensure_war_room_schema,
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

_log = logging.getLogger("duckclaw.gateway.telegram_inbound_webhook")

_TELEGRAM_WEBHOOK_DEDUPE_KEY_PREFIX = "duckclaw:dedupe:telegram:webhook:update"
_TELEGRAM_WEBHOOK_DEDUPE_TTL_SECONDS = 172800
_WORKER_ALIAS_CACHE_TTL_SECONDS = 60
_worker_alias_cache: set[str] = set()
_worker_alias_cache_ts: float = 0.0
_VISUAL_ALLOWED_MIME = {"image/jpeg", "image/png", "image/webp"}


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


def build_telegram_inbound_webhook_router(
    *,
    invoke_agent_chat: Callable[..., Awaitable[Any]],
    resolve_effective_telegram_bot_token: Callable[[], str],
) -> APIRouter:
    """
    Factory para no importar ``main`` desde este módulo (evita ciclos).

    - invoke_agent_chat: típicamente ``_invoke_chat`` del gateway.
    """

    router = APIRouter(prefix="/api/v1/telegram", tags=["telegram-inbound-webhook"])

    @router.post("/webhook")
    async def telegram_bot_update_webhook(request: Request) -> dict[str, str]:
        header_secret = request.headers.get(TELEGRAM_WEBHOOK_SECRET_HTTP_HEADER)
        default_token = (resolve_effective_telegram_bot_token() or "").strip()
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
        else:
            _tag, worker_id, tenant_id, reply_token = resolved

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
            ensure_war_room_schema(db)
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
                if mime_type and mime_type not in _VISUAL_ALLOWED_MIME:
                    wr_append_audit(
                        db,
                        tenant_id=tenant_id,
                        sender_id=user_id,
                        target_agent=None,
                        event_type="VLM_MIME_REJECTED",
                        payload=(mime_type or "unknown")[:128],
                    )
                    return {"ok": "true"}
                token_v = (reply_token or "").strip() or (resolve_effective_telegram_bot_token() or "").strip()
                mgid = (visual.get("media_group_id") or "").strip()
                if token_v:
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
                        _log.warning("VLM ingest falló: %s", exc)
                        wr_append_audit(
                            db,
                            tenant_id=tenant_id,
                            sender_id=user_id,
                            target_agent=None,
                            event_type="VLM_INGEST_FAILED",
                            payload=str(exc)[:500],
                        )

        payload = ChatRequest(
            message=text,
            chat_id=str(chat_id),
            user_id=user_id,
            username=username,
            chat_type=chat_type,
            tenant_id=tenant_id,
        )

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
            reply_plain = reply_local[:3500]
            reply_html = llm_markdown_to_telegram_html(reply_plain)
            sent = await client_r.send_message(
                chat_id=chat_id, text=reply_html, parse_mode="HTML"
            )
            if not sent.get("ok"):
                await client_r.send_message(
                    chat_id=chat_id,
                    text=reply_local[:3900],
                    parse_mode=None,
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

    return router
