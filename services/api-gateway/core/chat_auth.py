"""Telegram Guard: whitelist, alertas admin y autorización de chat."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, Optional

from fastapi import HTTPException

from core.telegram_delivery import effective_telegram_bot_token
from duckclaw.utils.logger import format_chat_id_for_terminal
from duckclaw.utils.telegram_markdown_v2 import escape_telegram_html

_gateway_log = logging.getLogger("duckclaw.gateway")

_AUTHORIZED_USERS_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS main.authorized_users (
    tenant_id VARCHAR,
    user_id VARCHAR,
    username VARCHAR,
    role VARCHAR DEFAULT 'user',
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (tenant_id, user_id)
);
"""


def escape_sql_literal(v: Any, max_len: int = 256) -> str:
    """Escape simple SQL string literals for DuckDB when we don't use parameterized queries."""
    s = "" if v is None else str(v)
    return s.replace("'", "''")[:max_len]


async def lookup_whitelist_role(
    redis_client: Any,
    db: Any,
    tenant_id: str,
    user_id: str,
) -> Optional[str]:
    """Telegram Guard whitelist lookup with Redis cache (TTL=1h) + DuckDB source of truth."""
    key = f"whitelist:{str(tenant_id or '').strip().lower()}:{user_id}"
    if redis_client is not None:
        try:
            cached = await redis_client.get(key)
            if cached:
                return str(cached).strip() or None
        except Exception:
            pass

    tid = escape_sql_literal(tenant_id, max_len=128)
    uid = escape_sql_literal(user_id, max_len=128)

    def _ensure_authorized_users_table() -> None:
        try:
            db.execute(_AUTHORIZED_USERS_TABLE_DDL)
        except Exception:
            return

    try:
        raw = db.query(
            f"SELECT role FROM main.authorized_users "
            f"WHERE lower(tenant_id)=lower('{tid}') AND user_id='{uid}' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            role = (rows[0].get("role") or "").strip()
            if role:
                if redis_client is not None:
                    try:
                        await redis_client.set(key, role, ex=3600)
                    except Exception:
                        pass
                return role
    except Exception:
        _ensure_authorized_users_table()
        try:
            raw = db.query(
                f"SELECT role FROM main.authorized_users "
                f"WHERE lower(tenant_id)=lower('{tid}') AND user_id='{uid}' LIMIT 1"
            )
            rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
            if rows and isinstance(rows[0], dict):
                role = (rows[0].get("role") or "").strip()
                if role:
                    if redis_client is not None:
                        try:
                            await redis_client.set(key, role, ex=3600)
                        except Exception:
                            pass
                    return role
        except Exception:
            pass
    return None


def send_security_alert_to_admin(user_id: str, tenant_id: str) -> None:
    """Alert opcional al admin vía Bot API nativa (TELEGRAM_BOT_TOKEN o token del bot activo)."""
    admin_chat_id = (os.getenv("DUCKCLAW_ADMIN_CHAT_ID") or "").strip()
    plain = (
        f"🚨 Alerta de Seguridad: El usuario {user_id} ha intentado acceder 3 veces "
        f"sin autorización al tenant {tenant_id}."
    )
    if not admin_chat_id:
        _gateway_log.warning("Telegram Guard: DUCKCLAW_ADMIN_CHAT_ID vacío; no hay alerta al admin")
        return

    token = effective_telegram_bot_token()
    if token:
        try:
            from duckclaw.integrations.telegram.telegram_outbound_sync import send_bot_message_sync

            if send_bot_message_sync(
                bot_token=token,
                chat_id=str(admin_chat_id),
                text=escape_telegram_html(plain),
                parse_mode="HTML",
                timeout_sec=15.0,
                log=_gateway_log,
            ):
                _gateway_log.info("Telegram Guard: alerta admin enviada vía Bot API nativa")
                return
        except Exception as exc:  # noqa: BLE001
            _gateway_log.warning("Telegram Guard: falló alerta nativa Bot API: %s", exc)
    _gateway_log.warning(
        "Telegram Guard: alerta admin no enviada (configure TELEGRAM_BOT_TOKEN o token del bot activo)",
    )


def langsmith_auth_log(*, auth_status: str, user_id: str, tenant_id: str) -> None:
    """
    Opcional: un run por request en LangSmith (Telegram Guard) satura el dashboard.

    Por defecto **no** se envía nada a LangSmith. Activar solo si hace falta depuración:
    ``DUCKCLAW_LANGSMITH_LOG_TELEGRAM_GUARD=true``

    La auditoría de seguridad sigue en logs estructurados del gateway (PM2) cuando corresponda.
    """
    try:
        if os.environ.get("DUCKCLAW_LANGSMITH_LOG_TELEGRAM_GUARD", "").strip().lower() not in (
            "1",
            "true",
            "yes",
        ):
            return
        api_key = os.environ.get("LANGCHAIN_API_KEY") or os.environ.get("LANGSMITH_API_KEY")
        if not api_key:
            return
        if os.environ.get("LANGCHAIN_TRACING_V2", "").lower() not in ("true", "1"):
            return

        from langsmith import Client

        from duckclaw.utils.langsmith_trace import create_completed_langsmith_run

        client = Client(api_key=api_key)
        tag = f"auth_status: {auth_status}"
        env_tag = os.getenv("DUCKCLAW_ENV", "dev")
        create_completed_langsmith_run(
            client,
            name="TelegramGuard",
            run_type="chain",
            inputs={"user_id": str(user_id), "tenant_id": str(tenant_id)},
            outputs={"auth_status": auth_status},
            tags=[tag, "telegram_guard", f"env:{env_tag}", f"tenant:{tenant_id}"],
        )
    except Exception:
        pass


async def authorize_or_reject(
    *,
    redis_client: Any,
    tenant_id: str,
    user_id: str,
    is_owner: bool,
    telegram_guard_acl_db_path: str | None = None,
) -> None:
    """
    Raises HTTPException(403) for unauthorized access.
    Also increments unauthorized attempts and triggers admin alert after 3 attempts.

    telegram_guard_acl_db_path:
        Bóveda forzada por multiplex Telegram (p. ej. ruta genérica ``DUCKCLAW_VAULT_DB_PATH``).
        Se usa en otras comprobaciones del request (p. ej. grants / vault); la whitelist
        ``main.authorized_users`` del Telegram Guard **siempre** se lee del hub
        ``get_gateway_db_path()`` (mismo archivo que comandos fly ``/team``) para no desalinear
        altas con rutas por bot.
    """
    del telegram_guard_acl_db_path  # reservado para grants/vault; whitelist usa hub gateway ACL

    if is_owner:
        langsmith_auth_log(auth_status="authorized", user_id=user_id, tenant_id=tenant_id)
        return

    from core.gateway_acl_db import get_gateway_acl_duckdb

    db = get_gateway_acl_duckdb()[0]
    role = await lookup_whitelist_role(redis_client, db, tenant_id, user_id)
    if role:
        langsmith_auth_log(auth_status="authorized", user_id=user_id, tenant_id=tenant_id)
        return

    _gateway_log.warning(
        "[SECURITY_ALERT] Unauthorized access attempt: user_id=%s tenant_id='%s'",
        format_chat_id_for_terminal(str(user_id or "unknown")),
        tenant_id,
    )
    langsmith_auth_log(auth_status="unauthorized_attempt", user_id=user_id, tenant_id=tenant_id)

    if redis_client is not None:
        attempts_key = f"authz_unauthorized_attempts:{tenant_id}:{user_id}"
        try:
            attempts = await redis_client.incr(attempts_key)
            if attempts == 1:
                await redis_client.expire(attempts_key, 3600)
            if attempts >= 3 and attempts - 3 < 1:
                await asyncio.get_running_loop().run_in_executor(
                    None, send_security_alert_to_admin, user_id, tenant_id
                )
        except Exception:
            pass

    raise HTTPException(
        status_code=403,
        detail="Acceso denegado. No tienes autorización para interactuar con este agente.",
    )
