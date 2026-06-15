"""Team access command ownership for the generic Telegram whitelist."""

from __future__ import annotations

from collections.abc import Callable
import json
import logging
import os
from pathlib import Path
from typing import Any

from duckclaw.commands.team_templates import configure_team_template_admin_checker


# Telegram Guard whitelist persistence (DuckDB table in schema `main`)
_AUTHORIZED_USERS_TABLE = "authorized_users"
_AUTHORIZED_USERS_DDL = ""

_team_access_acl_db_provider: Callable[[], Any] | None = None


def configure_team_access_acl_db_provider(provider: Callable[[], Any] | None) -> None:
    """Attach the runtime read facade used by graph command execution."""
    global _team_access_acl_db_provider
    _team_access_acl_db_provider = provider


def _sql_escape_literal(v: Any, max_len: int = 256) -> str:
    s = "" if v is None else str(v)
    return s.replace("'", "''")[:max_len]


def _ensure_authorized_users_table(db: Any) -> None:
    """Legacy compatibility shim; schema creation lives in shared migrations/db-writer."""
    return None


def _is_gateway_owner_user(user_id: str) -> bool:
    """Coincide con el bypass del API Gateway (DUCKCLAW_OWNER_ID / DUCKCLAW_ADMIN_CHAT_ID)."""
    uid = str(user_id or "").strip()
    if not uid:
        return False
    owner = (os.environ.get("DUCKCLAW_OWNER_ID") or os.environ.get("DUCKCLAW_ADMIN_CHAT_ID") or "").strip()
    return bool(owner and uid == owner)


def _is_team_admin(db: Any, *, tenant_id: str, requester_id: str) -> bool:
    if _is_gateway_owner_user(requester_id):
        return True
    rid = str(requester_id or "").strip()
    # Consola admin (playground): requester_id suele ser "admin-ui" sin user_id Telegram numérico.
    if rid == "admin-ui":
        return True
    return _get_authorized_role(db, tenant_id=tenant_id, user_id=rid) == "admin"


configure_team_template_admin_checker(_is_team_admin)


def _get_authorized_role(db: Any, *, tenant_id: str, user_id: str) -> str:
    _ensure_authorized_users_table(db)
    tid = _sql_escape_literal(tenant_id, max_len=128)
    uid = _sql_escape_literal(user_id, max_len=128)
    try:
        raw = db.query(
            f"SELECT role FROM main.{_AUTHORIZED_USERS_TABLE} "
            f"WHERE lower(tenant_id)=lower('{tid}') AND user_id='{uid}' LIMIT 1"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if rows and isinstance(rows[0], dict):
            return (rows[0].get("role") or "").strip().lower()
    except Exception:
        pass
    return ""


def _list_authorized_users(db: Any, *, tenant_id: str) -> list[dict[str, str]]:
    _ensure_authorized_users_table(db)
    tid = _sql_escape_literal(tenant_id, max_len=128)
    try:
        raw = db.query(
            f"SELECT user_id, username, role FROM main.{_AUTHORIZED_USERS_TABLE} "
            f"WHERE lower(tenant_id)=lower('{tid}') ORDER BY user_id"
        )
        rows = json.loads(raw) if isinstance(raw, str) else (raw or [])
        if isinstance(rows, list):
            out: list[dict[str, str]] = []
            for r in rows:
                if isinstance(r, dict):
                    out.append(
                        {
                            "user_id": str(r.get("user_id") or "").strip(),
                            "username": str(r.get("username") or "").strip(),
                            "role": str(r.get("role") or "").strip(),
                        }
                    )
            return out
    except Exception as exc:
        logging.getLogger("duckclaw.team_whitelist").warning(
            "authorized_users list query failed tenant_id=%r: %s", tenant_id, exc
        )
    return []


def _team_username_by_user_id(db: Any, tenant_id: str | None, user_id: Any) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    uid = str(user_id or "").strip()
    if not uid:
        return ""
    for u in _list_authorized_users(db, tenant_id=tid):
        if str(u.get("user_id") or "").strip() == uid:
            return str(u.get("username") or "").strip()
    return ""


def _player_label(
    username: Any,
    chat_id: Any,
    *,
    db: Any | None = None,
    tenant_id: str | None = None,
) -> str:
    """Etiqueta legible para /team (Telegram mention o @alias)."""
    uname = str(username or "").strip()
    cid = str(chat_id or "").strip() or "unknown"
    if not uname and db is not None:
        uname = _team_username_by_user_id(db, tenant_id, chat_id)
    if uname:
        if cid.isdigit():
            return f"[@{uname}](tg://user?id={cid})"
        return f"@{uname}"
    if cid.isdigit():
        return f"[{cid}](tg://user?id={cid})"
    return cid


def _player_label_log(
    username: Any,
    chat_id: Any,
    *,
    db: Any | None = None,
    tenant_id: str | None = None,
) -> str:
    """Formato para logs PM2: @alias (user_id)."""
    uname = str(username or "").strip()
    if not uname and db is not None:
        uname = _team_username_by_user_id(db, tenant_id, chat_id)
    cid = str(chat_id or "").strip() or "unknown"
    return f"@{uname} ({cid})" if uname else cid


def _resolve_team_add_uid_and_username(tokens: list[str]) -> tuple[str, str]:
    """
    ``/team --add``: el orden documentado es ``<user_id> [nombre]``, pero en Telegram
    es habitual escribir ``<nombre> <user_id> [user|admin]``. Si hay exactamente un token
    con aspecto de Telegram user id (solo dígitos, longitud razonable), se usa como
    ``user_id`` y el resto como nombre para mostrar.
    """
    tks = [t.strip() for t in tokens if t.strip()]
    if not tks:
        return "", "Usuario"
    # Telegram user_id es numérico; en tests se usan ids cortos (p. ej. 999).
    digit_indices = [i for i, x in enumerate(tks) if x.isdigit() and 3 <= len(x) <= 20]
    if len(digit_indices) == 1:
        i = digit_indices[0]
        uid = tks[i]
        name_parts = [tks[j] for j in range(len(tks)) if j != i]
        uname = " ".join(name_parts).strip() or "Usuario"
        return uid, uname
    if len(digit_indices) >= 2:
        i = digit_indices[-1]
        uid = tks[i]
        name_parts = [tks[j] for j in range(len(tks)) if j != i]
        uname = " ".join(name_parts).strip() or "Usuario"
        return uid, uname
    uid0 = tks[0]
    uname = (" ".join(tks[1:]).strip() if len(tks) > 1 else "Usuario") or "Usuario"
    return uid0, uname


def _dedupe_authorized_users_by_user_id(users: list[dict[str, str]]) -> list[dict[str, str]]:
    """
    Unifica filas por ``user_id`` (p. ej. duplicados legacy por distinto casing de ``tenant_id`` en PK).
    Si hay varias filas, se prioriza la que tenga rol ``admin``.
    """
    rank = {"admin": 3, "user": 2, "operator": 2, "observer": 1}

    def _score(u: dict[str, str]) -> int:
        r = (u.get("role") or "").strip().lower()
        return int(rank.get(r, 2))

    best: dict[str, dict[str, str]] = {}
    for u in users:
        uid = str(u.get("user_id") or "").strip()
        if not uid:
            continue
        if uid not in best or _score(u) > _score(best[uid]):
            best[uid] = u
    out = list(best.values())
    out.sort(key=lambda x: str(x.get("user_id") or ""))
    return out


def _command_connection(db: Any) -> Any:
    con = getattr(db, "_con", None)
    if con is not None:
        return con
    if getattr(db, "_native", None) is not None and hasattr(db, "release_file_handle_for_external_writer"):
        try:
            db.release_file_handle_for_external_writer()
            db.resume_file_handle()
            con = getattr(db, "_con", None)
            if con is not None:
                return con
        except Exception:
            return db
    return db


def _dispatch_authorized_user_command_inline(db: Any, command: Any) -> None:
    from duckclaw.schema_migrations import run_pending_migrations  # noqa: PLC0415
    from duckclaw.write_command_handlers import dispatch_command  # noqa: PLC0415

    payload = json.loads(command.to_redis_payload())
    conn = _command_connection(db)
    try:
        run_pending_migrations(conn)
        conn.execute("BEGIN TRANSACTION")
        dispatch_command(conn, payload)
        conn.execute("COMMIT")
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise


def _upsert_authorized_user(db: Any, *, tenant_id: str, user_id: str, username: str, role: str = "user") -> None:
    from duckclaw.write_commands import UpsertAuthorizedUserCommand  # noqa: PLC0415

    _dispatch_authorized_user_command_inline(
        db,
        UpsertAuthorizedUserCommand(
            tenant_id=tenant_id,
            user_id=user_id,
            username=username or "Usuario",
            role="admin" if str(role or "user").strip().lower() == "admin" else "user",
        ),
    )


def _delete_authorized_user(db: Any, *, tenant_id: str, user_id: str) -> None:
    from duckclaw.write_commands import DeleteAuthorizedUserCommand  # noqa: PLC0415

    _dispatch_authorized_user_command_inline(
        db,
        DeleteAuthorizedUserCommand(
            tenant_id=tenant_id,
            user_id=user_id,
        ),
    )


def _invalidate_whitelist_redis_cache(*, tenant_id: str, user_id: str) -> None:
    """
    El Gateway cachea roles en Redis (TTL ~1h). Tras /team --rm o --add, hay que borrar la clave
    o los usuarios revocados siguen pasando _lookup_whitelist_role hasta que expire el TTL.
    Misma convención que services/api-gateway/main.py: whitelist:{tenant_lower}:{user_id}
    """
    tid = str(tenant_id or "default").strip().lower() or "default"
    uid = str(user_id or "").strip()
    if not uid:
        return
    url = (os.environ.get("REDIS_URL") or os.environ.get("DUCKCLAW_REDIS_URL") or "").strip()
    if not url:
        return
    key = f"whitelist:{tid}:{uid}"
    try:
        import redis as redis_sync  # noqa: PLC0415

        client = redis_sync.Redis.from_url(url, decode_responses=True)
        client.delete(key)
    except Exception:
        pass


def _team_whitelist_audit_enabled() -> bool:
    v = (os.environ.get("DUCKCLAW_TEAM_WHITELIST_DEBUG") or "").strip().lower()
    return v in ("1", "true", "yes", "on")


def _audit_team_whitelist_rw(message: str, **data: Any) -> None:
    if not _team_whitelist_audit_enabled():
        return
    logging.getLogger("duckclaw.team_whitelist").info("%s %s", message, data)


def _paths_same_duckdb_file(a: str, b: str) -> bool:
    if not (a or "").strip() or not (b or "").strip():
        return False
    pa = Path(str(a).strip()).expanduser().resolve()
    pb = Path(str(b).strip()).expanduser().resolve()
    if str(pa) == str(pb):
        return True
    try:
        return bool(pa.samefile(pb))
    except OSError:
        return False


def _try_duckdb_checkpoint_rw(db: Any) -> None:
    if getattr(db, "_read_only", True):
        return
    try:
        db.execute("CHECKPOINT")
    except Exception:
        pass


def _db_path_for_team_access_write(acl_db: Any, fallback_db: Any) -> str:
    for candidate in (acl_db, fallback_db):
        try:
            raw = getattr(candidate, "_path", "") or ""
            if raw and str(raw).strip() not in ("", ":memory:"):
                return str(Path(str(raw)).expanduser().resolve())
        except Exception:
            continue
    try:
        from duckclaw.gateway_db import get_gateway_db_path  # noqa: PLC0415

        return str(Path(get_gateway_db_path()).resolve())
    except Exception:
        return ""


def _can_apply_team_command_on_existing_rw(db: Any, target_db_path: str) -> bool:
    if getattr(db, "_read_only", True) is not False:
        return False
    try:
        raw = getattr(db, "_path", "") or ""
        if not raw or str(raw).strip() in ("", ":memory:"):
            return not target_db_path
        return _paths_same_duckdb_file(str(raw), target_db_path) if target_db_path else True
    except Exception:
        return False


def _enqueue_team_access_command(db: Any, acl_db: Any, command: Any, *, requester_id: str) -> str:
    target_db_path = _db_path_for_team_access_write(acl_db, db)
    if not target_db_path:
        raise ValueError("No se pudo resolver la DuckDB de ACL para /team")
    try:
        from duckclaw.spawn_profile import spawn_inline_writes_enabled  # noqa: PLC0415

        if spawn_inline_writes_enabled() and _can_apply_team_command_on_existing_rw(db, target_db_path):
            _audit_team_whitelist_rw(
                "typed_command_inline_existing_rw",
                command_type=getattr(command, "command_type", ""),
                reason="spawn_inline",
            )
            _dispatch_authorized_user_command_inline(db, command)
            return str(getattr(command, "task_id", "") or "")
    except Exception:
        raise
    try:
        from duckclaw.db_write_queue import enqueue_typed_command, poll_task_status_sync  # noqa: PLC0415

        task_id = enqueue_typed_command(
            command,
            db_path=target_db_path,
            user_id=str(requester_id or "default").strip() or "default",
        )
    except Exception as exc:
        if not _can_apply_team_command_on_existing_rw(db, target_db_path):
            raise
        _audit_team_whitelist_rw(
            "typed_command_inline_existing_rw",
            command_type=getattr(command, "command_type", ""),
            reason=type(exc).__name__,
        )
        _dispatch_authorized_user_command_inline(db, command)
        return str(getattr(command, "task_id", "") or "")

    status = poll_task_status_sync(task_id, timeout_sec=0.25, interval_sec=0.05)
    if status is None:
        if _can_apply_team_command_on_existing_rw(db, target_db_path):
            _audit_team_whitelist_rw(
                "typed_command_inline_existing_rw",
                command_type=getattr(command, "command_type", ""),
                reason="writer_status_timeout",
            )
            _dispatch_authorized_user_command_inline(db, command)
        return task_id
    if status.status == "failed":
        raise RuntimeError(status.detail or "db-writer rejected team access command")
    return task_id


def _enqueue_authorized_user_command(db: Any, acl_db: Any, command: Any, *, requester_id: str) -> str:
    return _enqueue_team_access_command(db, acl_db, command, requester_id=requester_id)


def _team_whitelist_db(fly_db: Any) -> Any:
    """
    Whitelist ``main.authorized_users`` se lee de la misma DuckDB que el hub
    (``get_gateway_db_path()``), vía la conexión RO efímera configurada por runtime.

    Excepción: en el API Gateway el bloque fly ya abrió ``fly_db`` en RW sobre ese
    archivo; abrir un segundo ``duckdb.connect(..., read_only=True)`` en paralelo
    puede lanzar ``ConnectionException``. En ese caso reutilizamos ``fly_db``.
    """
    try:
        from duckclaw.gateway_db import get_gateway_db_path  # noqa: PLC0415

        gw = str(Path(get_gateway_db_path()).resolve())
        fp = ""
        try:
            fpraw = getattr(fly_db, "_path", "") or ""
            if fpraw and str(fpraw).strip() not in ("", ":memory:"):
                fp = str(Path(str(fpraw)).expanduser().resolve())
        except Exception:
            fp = ""
        same = _paths_same_duckdb_file(fp, gw) if fp else False
        fly_rw = getattr(fly_db, "_read_only", True) is False
        if same and fly_rw and hasattr(fly_db, "query"):
            return fly_db
        if _team_access_acl_db_provider is not None:
            return _team_access_acl_db_provider()
        return fly_db
    except Exception:
        return fly_db


def _authorized_users_rw_connection(fly_db: Any) -> tuple[Any, Callable[[], None]]:
    """
    Shim legacy: las mutaciones nuevas usan comandos tipados; no abre una conexión RW.
    """
    acl_ro = _team_whitelist_db(fly_db)

    def _noop() -> None:
        return None

    return acl_ro, _noop


def execute_team_whitelist(db: Any, tenant_id: Any, requester_id: Any, args: str) -> str:
    """
    Telegram Guard spec: /team lista y muta authorized_users por tenant.
    - /team                           -> lista autorizados (para tenant)
    - /team --add <user_id> [nombre] [admin|user] (también nombre primero si el id es numérico)
    - /team --rm <user_id>            (admin u owner)
    """
    acl = _team_whitelist_db(db)
    tid = str(tenant_id or "default").strip() or "default"
    rid = str(requester_id or "").strip()

    raw = (args or "").strip()

    if not raw:
        users = _dedupe_authorized_users_by_user_id(_list_authorized_users(acl, tenant_id=tid))
        if not users:
            hint = ""
            if _is_gateway_owner_user(rid):
                hint = (
                    " Como eres el owner del gateway (DUCKCLAW_OWNER_ID o DUCKCLAW_ADMIN_CHAT_ID), puedes ejecutar "
                    "`/team --add <user_id> [nombre] [admin]` para dar de alta."
                )
            return f"No hay usuarios autorizados para tenant '{tid}'.{hint}"
        body_lines: list[str] = []
        for u in users:
            uid = str(u.get("user_id") or "").strip()
            uname = str(u.get("username") or "").strip()
            role = (u.get("role") or "user").strip().lower() or "user"
            label = _player_label(uname, uid, db=acl, tenant_id=tid)
            body_lines.append(f"- {label} ({uid}) · rol: {role}")
        return f"🦆 Usuarios autorizados (tenant '{tid}'):\n" + "\n".join(body_lines)

    if raw.startswith("--rm "):
        if not rid:
            return "❌ Acceso denegado."
        if not _is_team_admin(acl, tenant_id=tid, requester_id=rid):
            return "❌ Acceso denegado: solo administradores pueden eliminar usuarios."
        target_uid = raw[5:].strip().split()[0]
        if not target_uid:
            return "Uso: /team --rm <user_id>"
        from duckclaw.write_commands import DeleteAuthorizedUserCommand  # noqa: PLC0415

        _enqueue_authorized_user_command(
            db,
            acl,
            DeleteAuthorizedUserCommand(
                tenant_id=tid,
                actor_email=f"telegram:{rid or 'system'}",
                user_id=target_uid,
            ),
            requester_id=rid or "default",
        )
        _invalidate_whitelist_redis_cache(tenant_id=tid, user_id=target_uid)
        target_label = _player_label("", target_uid, db=acl, tenant_id=tid)
        return f"✅ Eliminado {target_label} del tenant '{tid}'."

    if raw.startswith("--add ") or raw.strip() == "--add":
        if not rid:
            return "❌ Acceso denegado."
        if not _is_team_admin(acl, tenant_id=tid, requester_id=rid):
            return "❌ Acceso denegado: solo administradores pueden agregar usuarios."
        ids_part = raw[6:].strip() if raw.startswith("--add ") else ""
        tokens = [t for t in ids_part.split() if t.strip()]
        if not tokens:
            return "Uso: /team --add <user_id> [nombre] [admin|user]"
        role_out = "user"
        if len(tokens) >= 2 and tokens[-1].lower() == "admin":
            role_out = "admin"
            tokens = tokens[:-1]
        if len(tokens) >= 2 and tokens[-1].lower() == "user":
            tokens = tokens[:-1]
        if not tokens:
            return "Uso: /team --add <user_id> [nombre] [admin|user]"
        target_uid, uname = _resolve_team_add_uid_and_username(tokens)
        if not (target_uid or "").strip():
            return "Uso: /team --add <user_id> [nombre] [admin|user]"
        from duckclaw.write_commands import UpsertAuthorizedUserCommand  # noqa: PLC0415

        _enqueue_authorized_user_command(
            db,
            acl,
            UpsertAuthorizedUserCommand(
                tenant_id=tid,
                actor_email=f"telegram:{rid or 'system'}",
                user_id=target_uid,
                username=uname,
                role="admin" if role_out == "admin" else "user",
            ),
            requester_id=rid or "default",
        )
        _invalidate_whitelist_redis_cache(tenant_id=tid, user_id=target_uid)
        target_label = _player_label(uname, target_uid, db=acl, tenant_id=tid)
        return f"✅ Añadido {target_label} (role={role_out}) al tenant '{tid}'."

    if raw == "--shared-list" or raw.startswith("--shared-list"):
        if not rid:
            return "❌ Acceso denegado."
        if not _is_team_admin(acl, tenant_id=tid, requester_id=rid):
            return "❌ Acceso denegado: solo administradores pueden listar permisos de bases compartidas."
        from duckclaw.shared_db_grants import list_shared_grants_for_tenant

        grants = list_shared_grants_for_tenant(acl, tenant_id=tid)
        if not grants:
            return (
                f"🗂 No hay filas en user_shared_db_access para tenant '{tid}'. "
                "Sin filas, cualquier usuario whitelist puede usar rutas shared válidas (compat). "
                "Admin: /team --shared-grant <user_id> <resource_key> (ej. default o *)."
            )
        grant_lines: list[str] = []
        for g in grants:
            grant_lines.append(
                f"- user={g.get('user_id')} key={g.get('resource_key')} at={g.get('created_at')}"
            )
        return f"🗂 Bases compartidas permitidas (tenant '{tid}'):\n\n" + "\n".join(grant_lines)

    if raw.startswith("--shared-grant "):
        if not rid:
            return "❌ Acceso denegado."
        if not _is_team_admin(acl, tenant_id=tid, requester_id=rid):
            return "❌ Acceso denegado: solo administradores."
        rest = raw[len("--shared-grant ") :].strip().split(None, 1)
        if len(rest) < 2:
            return (
                "Uso: /team --shared-grant <user_id> <resource_key>\n"
                "resource_key: default, * (todas), o slug (env DUCKCLAW_SHARED_RESOURCE_<SLUG>)."
            )
        target_uid, rkey = rest[0], rest[1].strip()
        from duckclaw.shared_db_grants import validate_resource_key
        from duckclaw.write_commands import UpsertSharedDbGrantCommand  # noqa: PLC0415

        if not validate_resource_key(rkey):
            return "resource_key inválido (usa default, * o slug alfanumérico)."
        _enqueue_team_access_command(
            db,
            acl,
            UpsertSharedDbGrantCommand(
                tenant_id=tid,
                actor_email=f"telegram:{rid or 'system'}",
                user_id=target_uid,
                resource_key=rkey,
            ),
            requester_id=rid or "default",
        )
        return f"✅ Grant shared '{rkey}' → user {target_uid} (tenant '{tid}')."

    if raw.startswith("--shared-revoke "):
        if not rid:
            return "❌ Acceso denegado."
        if not _is_team_admin(acl, tenant_id=tid, requester_id=rid):
            return "❌ Acceso denegado: solo administradores."
        rest = raw[len("--shared-revoke ") :].strip().split(None, 1)
        if len(rest) < 2:
            return "Uso: /team --shared-revoke <user_id> <resource_key>"
        target_uid, rkey = rest[0], rest[1].strip()
        from duckclaw.shared_db_grants import validate_resource_key
        from duckclaw.write_commands import DeleteSharedDbGrantCommand  # noqa: PLC0415

        if not validate_resource_key(rkey):
            return "resource_key inválido."
        _enqueue_team_access_command(
            db,
            acl,
            DeleteSharedDbGrantCommand(
                tenant_id=tid,
                actor_email=f"telegram:{rid or 'system'}",
                user_id=target_uid,
                resource_key=rkey,
            ),
            requester_id=rid or "default",
        )
        return f"✅ Revocado shared '{rkey}' para user {target_uid}."

    return (
        "Uso: /team | /team --add ... | /team --rm ... | /team --shared-list | "
        "/team --shared-grant <user_id> <resource_key> | /team --shared-revoke <user_id> <resource_key>"
    )
