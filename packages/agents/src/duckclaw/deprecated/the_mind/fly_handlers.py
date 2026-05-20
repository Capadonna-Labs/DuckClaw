"""
The Mind — fly command handlers (deprecated).

No importar desde runtime de producción. Ver specs/features/platform/THE_MIND_DEPRECATION.md
"""

from __future__ import annotations

import json
import os
import random
import re
import string
import time
from typing import Any, Optional

from duckclaw.deprecated.the_mind.the_mind_outbound import (
    broadcast_message_to_players,
    deal_cards_for_level,
    send_telegram_dm,
)


def _skip_runtime_ddl(db: Any) -> bool:
    from duckclaw.graphs.on_the_fly_commands import _skip_runtime_ddl as _fn

    return _fn(db)


def _list_authorized_users(db: Any, *, tenant_id: str) -> list[dict[str, str]]:
    from duckclaw.graphs.on_the_fly_commands import _list_authorized_users as _fn

    return _fn(db, tenant_id=tenant_id)


def _player_label(
    username: Any,
    chat_id: Any,
    *,
    db: Any | None = None,
    tenant_id: str | None = None,
) -> str:
    from duckclaw.graphs.on_the_fly_commands import _player_label as _fn

    return _fn(username, chat_id, db=db, tenant_id=tenant_id)


def _player_label_log(
    username: Any,
    chat_id: Any,
    *,
    db: Any | None = None,
    tenant_id: str | None = None,
) -> str:
    from duckclaw.graphs.on_the_fly_commands import _player_label_log as _fn

    return _fn(username, chat_id, db=db, tenant_id=tenant_id)


def get_chat_state(db: Any, chat_id: Any, key: str) -> str | None:
    from duckclaw.graphs.on_the_fly_commands import get_chat_state as _fn

    return _fn(db, chat_id, key)


def _get_authorized_role(db: Any, *, tenant_id: str, user_id: str) -> str:
    from duckclaw.graphs.on_the_fly_commands import _get_authorized_role as _fn

    return _fn(db, tenant_id=tenant_id, user_id=user_id)


def _ensure_the_mind_schema(db: Any) -> None:
    """DDL único para The Mind + migraciones ligeras."""
    if _skip_runtime_ddl(db):
        return
    db.execute(
        "CREATE TABLE IF NOT EXISTS the_mind_games ("
        "game_id VARCHAR PRIMARY KEY, "
        "status VARCHAR, "
        "current_level INTEGER, "
        "lives INTEGER, "
        "shurikens INTEGER, "
        "cards_played INTEGER[])"
    )
    try:
        import json as _json

        info = db.query("PRAGMA table_info('the_mind_games')")
        rows = _json.loads(info) if isinstance(info, str) else (info or [])
        col_names = {str(r.get("name")) for r in rows if isinstance(r, dict)}
        if "chat_id" in col_names and "game_id" not in col_names:
            db.execute("ALTER TABLE the_mind_games RENAME COLUMN chat_id TO game_id")
        if "level" in col_names and "current_level" not in col_names:
            db.execute("ALTER TABLE the_mind_games RENAME COLUMN level TO current_level")
        if "status" not in col_names:
            db.execute("ALTER TABLE the_mind_games ADD COLUMN status VARCHAR DEFAULT 'waiting'")
    except Exception:
        pass
    db.execute(
        "CREATE TABLE IF NOT EXISTS the_mind_players ("
        "game_id VARCHAR, "
        "chat_id VARCHAR, "
        "username VARCHAR, "
        "cards INTEGER[], "
        "is_ready BOOLEAN, "
        "PRIMARY KEY (game_id, chat_id))"
    )
    try:
        db.execute("ALTER TABLE the_mind_players ADD COLUMN user_id VARCHAR")
    except Exception:
        pass
    db.execute(
        "CREATE TABLE IF NOT EXISTS the_mind_moves ("
        "game_id VARCHAR, "
        "chat_id VARCHAR, "
        "username VARCHAR, "
        "move_type VARCHAR, "
        "card_value INTEGER, "
        "level INTEGER, "
        "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )


def _merge_the_mind_player(
    db: Any,
    game_id: str,
    chat_id: str,
    username: str,
    *,
    user_id: str | None = None,
) -> None:
    """Inserta o actualiza jugador en partida (preserva mano si ya existía)."""
    uid = (user_id or "").strip() or None
    ex = list(
        db.execute(
            "SELECT 1 FROM the_mind_players WHERE game_id = ? AND chat_id = ?",
            (game_id, chat_id),
        )
    )
    if ex:
        if uid:
            db.execute(
                "UPDATE the_mind_players SET username = ?, user_id = COALESCE(?, user_id) "
                "WHERE game_id = ? AND chat_id = ?",
                (username or "", uid, game_id, chat_id),
            )
        else:
            db.execute(
                "UPDATE the_mind_players SET username = ? WHERE game_id = ? AND chat_id = ?",
                (username or "", game_id, chat_id),
            )
    else:
        db.execute(
            "INSERT INTO the_mind_players (game_id, chat_id, username, cards, is_ready, user_id) "
            "VALUES (?, ?, ?, ARRAY[]::INTEGER[], FALSE, ?)",
            (game_id, chat_id, username or "", uid),
        )


def _mind_tx_begin(db: Any) -> None:
    try:
        db.execute("BEGIN TRANSACTION")
    except Exception:
        try:
            db.execute("BEGIN")
        except Exception:
            pass


def _mind_tx_commit(db: Any) -> None:
    try:
        db.execute("COMMIT")
    except Exception:
        pass


def _mind_tx_rollback(db: Any) -> None:
    try:
        db.execute("ROLLBACK")
    except Exception:
        pass


def _insert_mind_move(
    db: Any,
    *,
    game_id: str,
    chat_id: str,
    username: str,
    move_type: str,
    card_value: int | None = None,
    level: int | None = None,
) -> None:
    try:
        db.execute(
            """
            INSERT INTO the_mind_moves (game_id, chat_id, username, move_type, card_value, level)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                game_id,
                chat_id,
                username or "",
                move_type,
                int(card_value) if card_value is not None else None,
                int(level) if level is not None else None,
            ),
        )
    except Exception:
        pass


def _team_username_by_user_id(db: Any, tenant_id: str | None, user_id: Any) -> str:
    tid = str(tenant_id or "default").strip() or "default"
    uid = str(user_id or "").strip()
    if not uid:
        return ""
    for u in _list_authorized_users(db, tenant_id=tid):
        if str(u.get("user_id") or "").strip() == uid:
            return str(u.get("username") or "").strip()
    return ""


def _player_label(username: Any, chat_id: Any, *, db: Any | None = None, tenant_id: str | None = None) -> str:
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


def _player_label_log(username: Any, chat_id: Any, *, db: Any | None = None, tenant_id: str | None = None) -> str:
    """Formato para logs PM2: @alias (user_id)."""
    uname = str(username or "").strip()
    if not uname and db is not None:
        uname = _team_username_by_user_id(db, tenant_id, chat_id)
    cid = str(chat_id or "").strip() or "unknown"
    return f"@{uname} ({cid})" if uname else cid


def _chat_log_identity_for_context(
    chat_id: Any,
    *,
    db: Any | None = None,
    tenant_id: str | None = None,
) -> str:
    """Etiqueta para cabecera de logs PM2: @alias (user_id) con fallback a user_id."""
    cid = str(chat_id if chat_id is not None else "unknown").strip() or "unknown"
    uname = ""
    if db is not None:
        try:
            uname = str(get_chat_state(db, chat_id, "username") or "").strip()
        except Exception:
            uname = ""
        if not uname:
            uname = _team_username_by_user_id(db, tenant_id, chat_id)
    return f"@{uname} ({cid})" if uname else cid


def _notify_level_up_with_private_hands(
    db: Any,
    game_id: str,
    completed_level: int,
    next_level: int,
    *,
    exclude_chat_id: str | None = None,
) -> None:
    """Envía DM individual a cada jugador al subir nivel con su nueva mano (solo sus cartas)."""
    try:
        rows = list(
            db.execute(
                "SELECT chat_id, username, cards FROM the_mind_players WHERE game_id = ?",
                (game_id,),
            )
        )
        exclude = (exclude_chat_id or "").strip()
        for pchat, puname, cards in rows:
            cid = str(pchat or "").strip()
            if exclude and cid == exclude:
                continue
            hand = sorted(int(c) for c in list(cards or []))
            send_telegram_dm(
                cid,
                f"🃏 Tus nuevas cartas: {hand}",
                username=str(puname or ""),
                db=db,
                tenant_id="default",
            )
    except Exception:
        pass


_THE_MIND_MAX_LEVEL = 12


def _team_allows_user(db: Any, tenant_id: str | None, user_id: Any) -> tuple[bool, str]:
    """
    Si hay al menos un usuario en authorized_users del tenant, solo esos user_id
    pueden crear/unirse a partidas The Mind. Si la lista está vacía, no se restringe
    (compatibilidad con despliegues sin whitelist).
    """
    tid = str(tenant_id or "default").strip() or "default"
    users = _list_authorized_users(db, tenant_id=tid)
    if not users:
        return True, ""
    uid = str(user_id or "").strip()
    if not uid:
        return False, "Falta identidad de usuario (user_id). El Gateway debe enviar user_id para The Mind."
    allowed = {str(u.get("user_id") or "").strip() for u in users if u.get("user_id")}
    if uid in allowed:
        return True, ""
    return (
        False,
        "Solo pueden jugar usuarios listados en /team para este tenant. Pide a un admin que ejecute `/team --add <tu_user_id>`.",
    )


def _all_mind_players_in_team(db: Any, game_id: str, tenant_id: str | None) -> tuple[bool, str]:
    """
    Si /team no está vacío, todos los jugadores deben tener user_id y estar en la whitelist.
    Si /team está vacío, no se exige user_id (compatibilidad con clientes sin identidad).
    """
    tid = str(tenant_id or "default").strip() or "default"
    roster = _list_authorized_users(db, tenant_id=tid)
    if not roster:
        return True, ""
    allowed = {str(u.get("user_id") or "").strip() for u in roster if u.get("user_id")}
    rows = list(db.execute("SELECT user_id FROM the_mind_players WHERE game_id = ?", (game_id,)))
    for (uid_raw,) in rows:
        uid = str(uid_raw or "").strip()
        if not uid:
            return (
                False,
                "No se puede iniciar: falta user_id en algún jugador. Con /team configurado, cada uno debe usar `/join` desde un cliente que envíe user_id al Gateway.",
            )
        if uid not in allowed:
            return (
                False,
                f"No se puede iniciar: {_player_label('', uid, db=db, tenant_id=tid)} no está en /team para este tenant.",
            )
    return True, ""


def _the_mind_invite_hint(db: Any, tenant_id: str | None, game_id: str) -> str:
    """Texto corto: equipo /team, DMs vs avisos, pasos para invitar e iniciar."""
    tid = str(tenant_id or "default").strip() or "default"
    users = _list_authorized_users(db, tenant_id=tid)
    if users:
        team_lines = []
        for u in users:
            uid = str(u.get("user_id") or "").strip()
            uname = str(u.get("username") or "").strip()
            label = f"@{uname}" if uname else uid
            team_lines.append(f"- {label}")
        team_block = "\n".join(team_lines)
    else:
        team_block = "(Nadie en /team: un admin debe usar /team --add <user_id> [nombre].)"

    return (
        "\n\n---\n"
        "Cómo invitar e iniciar:\n"
        "• Solo pueden unirse quienes estén en /team (tenant actual).\n"
        "• Las cartas solo se envían a los chat_id registrados en la partida: cada jugador debe /join desde su DM con el bot (no basta con un grupo).\n"
        "• Requiere webhook de salida en el gateway (p. ej. DUCKCLAW_TELEGRAM_SEND_WEBHOOK_URL); si falta, verás aviso al iniciar.\n"
        "• Cartas: cada jugador recibe un mensaje distinto por DM.\n"
        "• Avisos del juego (nivel, errores, victoria): el mismo texto a todos los DM de la partida.\n"
        f"• Equipo autorizado ahora:\n{team_block}\n"
        f"• Pasos: cada jugador abre DM con el bot y envía /join {game_id}.\n"
        f"• Luego el anfitrión: /start_mind {game_id} (mínimo 2 jugadores; ver /game).\n"
    


    )
def _new_game_id() -> str:
    """Genera un identificador de partida único (game_id)."""
    # timestamp en segundos + sufijo aleatorio corto
    import time
    import random
    import string

    ts = int(time.time())
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=4))
    return f"game_{ts}_{suffix}"


def execute_new_game(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
) -> str:
    """/new_game the_mind: crea una nueva partida de The Mind y devuelve el game_id."""
    game_type = (args or "").strip().lower()
    if game_type not in ("the_mind", "themind", "themindcrupier"):
        return "Uso: /new_game the_mind"
    try:
        _ensure_the_mind_schema(db)
        tid = str(tenant_id or "default").strip() or "default"
        ok, err = _team_allows_user(db, tid, requester_id)
        if not ok:
            return err
        game_id = _new_game_id()
        db.execute(
            "INSERT INTO the_mind_games (game_id, status, current_level, lives, shurikens, cards_played) "
            "VALUES (?, 'waiting', 1, 3, 1, ARRAY[]::INTEGER[])",
            (game_id,),
        )
        cid = str(chat_id).replace("'", "''")[:256]
        uname = get_chat_state(db, chat_id, "username") or ""
        rid = str(requester_id or "").strip() or None
        _merge_the_mind_player(db, game_id, cid, uname, user_id=rid)
        base = (
            f"🧠 The Mind: partida creada con id {game_id}. "
            f"Cada jugador debe enviar `/join {game_id}` desde el chat privado (DM) con el bot para quedar registrado y recibir cartas."
        )
        return base + _the_mind_invite_hint(db, tid, game_id)
    except Exception as e:
        return f"No se pudo crear la partida de The Mind: {e}"


def execute_join_game(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
) -> str:
    """/join <game_id>: añade al jugador (este chat) a la partida indicada."""
    game_id = (args or "").strip()
    if not game_id:
        return "Uso: /join <game_id>. Ejemplo: /join game_1234"
    try:
        _ensure_the_mind_schema(db)
        tid = str(tenant_id or "default").strip() or "default"
        ok, err = _team_allows_user(db, tid, requester_id)
        if not ok:
            return err
        rows = list(
            db.execute(
                "SELECT game_id, status FROM the_mind_games WHERE game_id = ?", (game_id,)
            )
        )
        if not rows:
            return f"No existe ninguna partida con id {game_id}."
        status = str(rows[0][1] or "").strip().lower()
        if status not in ("waiting", "playing"):
            return (
                f"La partida {game_id} no acepta más jugadores (estado actual: {status or 'desconocido'})."
            
            )
        cid = str(chat_id).replace("'", "''")[:256]
        uname = get_chat_state(db, chat_id, "username") or ""
        rid = str(requester_id or "").strip() or None
        _merge_the_mind_player(db, game_id, cid, uname, user_id=rid)
        # Avisar por DM al/los admin del tenant cuando alguien se une.
        try:
            n_rows = list(
                db.execute("SELECT COUNT(*) FROM the_mind_players WHERE game_id = ?", (game_id,))
            )
            n_players = int(n_rows[0][0]) if n_rows else 0
            actor = _player_label(uname, (rid or chat_id), db=db, tenant_id=tid)
            admin_users = [
                u for u in _list_authorized_users(db, tenant_id=tid)
                if (u.get("role") or "").strip().lower() == "admin"
            ]
            notice = (
                f"🧠 {actor} se unió a la partida {game_id}. "
                f"Jugadores: {n_players}. Usa /start_mind {game_id} cuando estén todos."
            )
            sent_to: set[str] = set()
            for u in admin_users:
                admin_uid = str(u.get("user_id") or "").strip()
                if not admin_uid or admin_uid in sent_to:
                    continue
                send_telegram_dm(
                    admin_uid,
                    notice,
                    username=str(u.get("username") or ""),
                    db=db,
                    tenant_id=tid,
                )
                sent_to.add(admin_uid)
        except Exception:
            # Best-effort: no bloquear el join por problemas de notificación.
            pass
        return (
            f"✅ Te has unido a la partida {game_id}. Espera a que el anfitrión inicie con `/start_mind {game_id}`."
        
        )
    except Exception as e:
        return f"No se pudo unir a la partida: {e}"


def execute_list_mind_games(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
) -> str:
    """/game: listar partidas activas; /game --end cierra tu partida activa; admin: /game --rm <game_id>|all cancela partidas activas."""
    raw = (args or "").strip()
    tid = str(tenant_id or "default").strip() or "default"
    rid = str(requester_id or "").strip()

    # End current player's active game (self-service)
    if raw == "--end":
        cid = str(chat_id).replace("'", "''")[:256]
        try:
            _ensure_the_mind_schema(db)
            rows = list(
                db.execute(
                    """
                    SELECT g.game_id
                    FROM the_mind_games g
                    JOIN the_mind_players p ON p.game_id = g.game_id
                    WHERE p.chat_id = ? AND lower(COALESCE(g.status, '')) IN ('waiting', 'playing')
                    ORDER BY g.rowid DESC
                    LIMIT 1
                    """,
                    (cid,),
                )
            )
            if not rows:
                return "No estás en ninguna partida activa."
            game_id = str(rows[0][0] or "").strip()
            if not game_id:
                return "No estás en ninguna partida activa."
            db.execute(
                "UPDATE the_mind_games SET status = 'cancelled' WHERE game_id = ?",
                (game_id,),
            )
            try:
                broadcast_message_to_players(
                    db,
                    game_id,
                    f"🛑 Partida finalizada: {game_id}",
                    exclude_chat_id=cid,
                )
            except Exception:
                pass
            return f"🛑 Partida finalizada: {game_id}"
        except Exception as e:
            return f"No se pudo finalizar la partida: {e}"

    # Admin-only cancel flow
    if raw.startswith("--rm "):
        role = _get_authorized_role(db, tenant_id=tid, user_id=rid) if rid else ""
        if role != "admin":
            return "Solo el admin puede cancelar partidas."

        target = raw[5:].strip().split()[0] if raw[5:].strip() else ""
        if not target:
            return "Uso: /game --rm <game_id> | /game --rm all"
        try:
            _ensure_the_mind_schema(db)
            if target.lower() == "all":
                rows = list(
                    db.execute(
                        """
                        SELECT game_id
                        FROM the_mind_games
                        WHERE lower(COALESCE(status, '')) IN ('waiting', 'playing')
                        ORDER BY game_id DESC
                        """
                    )
                )
                game_ids = [str(r[0]) for r in rows if r and r[0]]
                if not game_ids:
                    return "No hay partidas activas que cancelar."
                db.execute(
                    """
                    UPDATE the_mind_games
                    SET status = 'cancelled'
                    WHERE lower(COALESCE(status, '')) IN ('waiting', 'playing')
                    """
                )
                return f"🗑️ Partida(s) cancelada(s): [{', '.join(game_ids)}]"

            rows = list(
                db.execute(
                    """
                    SELECT game_id
                    FROM the_mind_games
                    WHERE game_id = ? AND lower(COALESCE(status, '')) IN ('waiting', 'playing')
                    LIMIT 1
                    """,
                    (target,),
                )
            )
            if not rows:
                return "No hay partidas activas que cancelar."
            game_id = str(rows[0][0])
            db.execute(
                "UPDATE the_mind_games SET status = 'cancelled' WHERE game_id = ?",
                (game_id,),
            )
            return f"🗑️ Partida(s) cancelada(s): [{game_id}]"
        except Exception as e:
            return f"No se pudo cancelar partidas: {e}"
    try:
        _ensure_the_mind_schema(db)
        rows = list(
            db.execute(
                """
                SELECT g.game_id, g.status, g.current_level, g.lives,
                       COUNT(p.chat_id) AS n
                FROM the_mind_games g
                LEFT JOIN the_mind_players p ON p.game_id = g.game_id
                WHERE lower(COALESCE(g.status, '')) IN ('waiting', 'playing')
                GROUP BY g.game_id, g.status, g.current_level, g.lives
                ORDER BY g.game_id DESC
                """
            )
        )
    except Exception as e:
        return f"No se pudo listar partidas: {e}"
    if not rows:
        return (
            "No hay partidas activas (waiting/playing). Usa /new_mind para crear una."
        
        )
    # Durante partida: para un jugador en estado playing devolver estado resumido (sin revelar manos).
    try:
        cid = str(chat_id).replace("'", "''")[:256]
        current = list(
            db.execute(
                """
                SELECT g.game_id, g.current_level, g.lives, g.shurikens, g.cards_played
                FROM the_mind_games g
                JOIN the_mind_players p ON p.game_id = g.game_id
                WHERE g.status = 'playing' AND p.chat_id = ?
                ORDER BY g.rowid DESC
                LIMIT 1
                """,
                (cid,),
            )
        )
        if current:
            game_id, lvl, lives, stars, cards_played = current[0]
            total_remaining_rows = list(
                db.execute(
                    "SELECT cards FROM the_mind_players WHERE game_id = ?",
                    (game_id,),
                )
            )
            remaining = sum(len(list(r[0] or [])) for r in total_remaining_rows)
            cards_table = list(cards_played or [])
            return (
                f"🧠 Nivel: {int(lvl or 1)} | Vidas: {int(lives or 0)} | Estrellas: {int(stars or 0)}\n"
                f"Cartas en mesa: {cards_table} | Cartas restantes: {remaining}"
            
            )
    except Exception:
        pass

    lines: list[str] = []
    for r in rows:
        gid, st, lvl, lives, n = r[0], r[1], r[2], r[3], r[4]
        players_rows = list(
            db.execute(
                "SELECT chat_id, username FROM the_mind_players WHERE game_id = ? ORDER BY chat_id",
                (gid,),
            )
        )
        # Importante: evitar Markdown links `[...] (tg://...)` aquí, porque algunos nodos Telegram
        # Algunos nodos usan parse_mode Markdown/MarkdownV2 y pueden fallar con entidades TextUrl anidadas.
        players_labels = [
            _player_label_log(uname, pchat, db=db, tenant_id=tid)
            for pchat, uname in players_rows
        ]
        players_text = ", ".join(players_labels) if players_labels else "sin jugadores"
        lines.append(
            f"• {gid} — estado={st or '?'} | jugadores={int(n or 0)} | "
            f"nivel={int(lvl or 1)} | vidas={int(lives or 0)} | "
            f"participantes={players_text}"
        )
    body = "\n".join(lines)
    return f"🧠 Partidas activas:\n{body}"


def execute_start_game(db: Any, chat_id: Any, args: str) -> str:
    """/start_game [game_id]: cambia el estado de la partida a 'playing' para comenzar el nivel 1."""
    game_id = (args or "").strip()
    try:
        if not game_id:
            # Inferir: última partida 'waiting' creada
            rows = list(
                db.execute(
                    "SELECT game_id FROM the_mind_games WHERE status = 'waiting' ORDER BY rowid DESC LIMIT 1"
                )
            )
            if not rows:
                return (
                    "No encontré ninguna partida en estado 'waiting'. Usa `/new_mind` o `/new_game the_mind`."
                
                )
            game_id = str(rows[0][0])
        rows = list(
            db.execute(
                "SELECT status FROM the_mind_games WHERE game_id = ?", (game_id,)
            )
        )
        if not rows:
            return f"No existe ninguna partida con id {game_id}."
        status = str(rows[0][0] or "").strip().lower()
        if status == "playing":
            return f"La partida {game_id} ya está en juego."
        if status not in ("waiting",):
            return (
                f"No se puede iniciar la partida {game_id} desde el estado {status or 'desconocido'}."
            
            )
        db.execute(
            "UPDATE the_mind_games SET status = 'playing', current_level = COALESCE(current_level, 1) "
            "WHERE game_id = ?",
            (game_id,),
        )
        return (
            f"🧠 The Mind: partida {game_id} en estado playing. Reparte cartas con `/start_mind {game_id}` o `/deal`."
        
        )
    except Exception as e:
        return f"No se pudo iniciar la partida: {e}"


def execute_start_mind(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
) -> str:
    """
    /start_mind [game_id]: pasa la partida a playing, reparte el Nivel 1 por DM
    y anuncia por broadcast.
    """
    try:
        _ensure_the_mind_schema(db)
        tid = str(tenant_id or "default").strip() or "default"
        starter_id = str(requester_id or "").strip() or str(chat_id or "").strip()
        starter_role = _get_authorized_role(db, tenant_id=tid, user_id=starter_id)
        if starter_role != "admin":
            return "Solo el admin puede iniciar la partida."
        ok_host, err_host = _team_allows_user(db, tid, requester_id)
        if not ok_host:
            return err_host
        game_id = (args or "").strip()
        cid = str(chat_id).replace("'", "''")[:256]

        if not game_id:
            rows = list(
                db.execute(
                    """
                    SELECT g.game_id
                    FROM the_mind_games g
                    JOIN the_mind_players p ON p.game_id = g.game_id
                    WHERE g.status = 'waiting' AND p.chat_id = ?
                    ORDER BY g.rowid DESC
                    LIMIT 1
                    """,
                    (cid,),
                )
            )
            if not rows:
                rows = list(
                    db.execute(
                        "SELECT game_id FROM the_mind_games WHERE status = 'waiting' "
                        "ORDER BY rowid DESC LIMIT 1"
                    )
                )
            if not rows:
                return (
                    "No encontré ninguna partida en espera. Usa `/new_mind` o `/new_game the_mind`."
                
                )
            game_id = str(rows[0][0])

        rows = list(
            db.execute(
                "SELECT status FROM the_mind_games WHERE game_id = ?", (game_id,)
            )
        )
        if not rows:
            return f"No existe ninguna partida con id {game_id}."
        status = str(rows[0][0] or "").strip().lower()
        if status != "waiting":
            return (
                f"La partida {game_id} no está en espera (estado: {status or 'desconocido'}). "
                "Solo se puede `/start_mind` desde 'waiting'."
            

            )
        n_players = list(
            db.execute(
                "SELECT COUNT(*) FROM the_mind_players WHERE game_id = ?", (game_id,)
            )
        )
        count = int(n_players[0][0]) if n_players else 0
        if count < 1:
            return "No hay jugadores en esta partida."

        allow_solo = (os.environ.get("DUCKCLAW_THE_MIND_ALLOW_SOLO") or "").strip().lower() in (
            "1",
            "true",
            "yes",
        )
        if count < 2 and not allow_solo:
            return (
                f"Solo hay {count} jugador(es) en la partida {game_id}. "
                "Se necesitan al menos 2: cada uno debe enviar `/join "
                f"{game_id}` por DM con el bot. Usa /game para ver el estado. "
                "(Modo 1 jugador: define DUCKCLAW_THE_MIND_ALLOW_SOLO=true en el gateway.)"
            

            )
        ok_roster, err_roster = _all_mind_players_in_team(db, game_id, tid)
        if not ok_roster:
            return err_roster

        db.execute(
            "UPDATE the_mind_games SET status = 'playing', current_level = 1, "
            "cards_played = ARRAY[]::INTEGER[] WHERE game_id = ?",
            (game_id,),
        )
        # Orden requerido de mensajes al iniciar:
        # 1) anuncio global de comienzo, 2) DM "Nivel 1 ...", 3) DM con cartas.
        broad_res = broadcast_message_to_players(
            db,
            game_id,
            "🎮 ¡La partida ha comenzado! Recuerden: sin comunicación. "
            "Jueguen en orden ascendente. Vidas: 3 | Estrellas: 1",
        )
        try:
            players = list(
                db.execute(
                    "SELECT chat_id, username FROM the_mind_players WHERE game_id = ?",
                    (game_id,),
                )
            )
            for pchat, puname in players:
                send_telegram_dm(
                    str(pchat or ""),
                    (
                        "🧠 Nivel 1 — tienes 1 carta(s). Cuando quieras jugar una, "
                        "escribe /play <número>. No le digas tu carta a nadie."
                    ),
                    username=str(puname or ""),
                    db=db,
                    tenant_id=tid,
                )
        except Exception:
            pass
        deal_res = deal_cards_for_level(db, game_id, 1)
        return (
            f"🧠 Partida {game_id} iniciada (Nivel 1 en BD).\n"
            f"• {broad_res.summary_line}\n"
            f"• {deal_res.summary_line}"
        
        )
    except Exception as e:
        return f"No se pudo iniciar The Mind: {e}"


def execute_deal(db: Any, chat_id: Any, args: str) -> str:
    """/deal [game_id]: reparte cartas según current_level de la partida en juego."""
    try:
        _ensure_the_mind_schema(db)
        game_id = (args or "").strip()
        cid = str(chat_id).replace("'", "''")[:256]
        if not game_id:
            rows = list(
                db.execute(
                    """
                    SELECT g.game_id, g.current_level
                    FROM the_mind_games g
                    JOIN the_mind_players p ON p.game_id = g.game_id
                    WHERE g.status = 'playing' AND p.chat_id = ?
                    ORDER BY g.rowid DESC
                    LIMIT 1
                    """,
                    (cid,),
                )
            )
            if not rows:
                return (
                    "No hay partida en juego para este chat. Usa `/join` y `/start_mind` primero."
                
                )
            game_id = str(rows[0][0])
            lvl = int(rows[0][1] or 1)
        else:
            lr = list(
                db.execute(
                    "SELECT current_level FROM the_mind_games WHERE game_id = ? AND status = 'playing'",
                    (game_id,),
                )
            )
            if not lr:
                return f"No hay partida en juego con id {game_id}."
            lvl = int(lr[0][0] or 1)
        deal_res = deal_cards_for_level(db, game_id, lvl)
        return f"🃏 {deal_res.summary_line}"
    except Exception as e:
        return f"No se pudo repartir: {e}"


def execute_play_mind(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: Any = None,
) -> str:
    """/play <numero>: juega una carta en The Mind usando the_mind_games/the_mind_players."""
    num_str = (args or "").strip()
    if not num_str:
        return "Uso: /play <numero>. Ejemplo: /play 15"
    try:
        num = int(num_str)
    except Exception:
        return "La carta debe ser un número entero. Ejemplo: /play 15"
    if num <= 0 or num > 100:
        return "La carta debe estar entre 1 y 100."

    cid = str(chat_id).replace("'", "''")[:256]
    uname = get_chat_state(db, chat_id, "username") or ""
    tid = str(tenant_id or "default").strip() or "default"
    uname_display = _player_label(uname, cid, db=db, tenant_id=tid)

    try:
        _ensure_the_mind_schema(db)
        _mind_tx_begin(db)
        rows = list(
            db.execute(
                """
                SELECT g.game_id, g.cards_played, g.current_level, g.status
                FROM the_mind_games g
                JOIN the_mind_players p ON g.game_id = p.game_id
                WHERE g.status = 'playing' AND p.chat_id = ?
                ORDER BY g.rowid DESC
                LIMIT 1
                """,
                (cid,),
            )
        )
        if not rows:
            _mind_tx_rollback(db)
            return (
                "No encontré ninguna partida en juego asociada a este chat. "
                "Usa `/join` y `/start_mind`."
            
            )
        game_id, cards_played_arr, current_level, _st = rows[0]
        cards_played = list(cards_played_arr or [])
        _insert_mind_move(
            db,
            game_id=str(game_id),
            chat_id=cid,
            username=uname or "",
            move_type="play_attempt",
            card_value=num,
            level=int(current_level or 1),
        )

        prow = list(
            db.execute(
                "SELECT cards FROM the_mind_players WHERE game_id = ? AND chat_id = ?",
                (game_id, cid),
            )
        )
        if not prow:
            _mind_tx_rollback(db)
            return (
                "No encontré tu mano en esta partida. Espera a que se repartan cartas con `/start_mind`."
            
            )
        hand = list(prow[0][0] or [])
        if num not in hand:
            _mind_tx_rollback(db)
            return (
                f"No tienes la carta {num} en tu mano actual. Verifica tus cartas privadas."
            

            )
        lower_exists = False
        offender_name = ""
        offender_chat = ""
        offender_username = ""
        offender_card: int | None = None
        all_rows_for_validation = list(
            db.execute(
                "SELECT chat_id, username, cards FROM the_mind_players WHERE game_id = ?",
                (game_id,),
            )
        )
        for pchat, puname, pcards in all_rows_for_validation:
            if pcards:
                for c in pcards:
                    if int(c) < num:
                        lower_exists = True
                        if offender_card is None or int(c) < offender_card:
                            offender_card = int(c)
                            offender_chat = str(pchat or "")
                            offender_username = str(puname or "")
                            offender_name = _player_label(puname, pchat, db=db, tenant_id=tid)
                        break
            if lower_exists and offender_card is not None and offender_card == 1:
                # No puede existir carta menor que 1; corte rápido.
                break

        if lower_exists:
            life_row = list(
                db.execute(
                    "SELECT lives FROM the_mind_games WHERE game_id = ?", (game_id,)
                )
            )
            lives = int(life_row[0][0] or 0) if life_row else 0
            new_lives = max(lives - 1, 0)

            all_hands = list(
                db.execute(
                    "SELECT chat_id, username, cards FROM the_mind_players WHERE game_id = ?",
                    (game_id,),
                )
            )
            discarded_notes: list[str] = []
            discarded_count = 0
            for pch, puname, pcards in all_hands:
                raw = list(pcards or [])
                # En penalización, descartar solo la carta en conflicto detectada
                # (offender_card) y no todas las menores a `num`.
                discarded_cards: list[int] = []
                new_hand: list[int] = []
                removed_conflict = False
                for c in raw:
                    ci = int(c)
                    if (
                        offender_card is not None
                        and not removed_conflict
                        and ci == int(offender_card)
                    ):
                        discarded_cards.append(ci)
                        removed_conflict = True
                        continue
                    new_hand.append(ci)
                # En penalización, la carta jugada también sale de la mano del actor.
                if str(pch or "") == cid:
                    removed_played = False
                    actor_hand: list[int] = []
                    for c in new_hand:
                        if not removed_played and int(c) == int(num):
                            removed_played = True
                            continue
                        actor_hand.append(int(c))
                    new_hand = actor_hand
                db.execute(
                    "UPDATE the_mind_players SET cards = ? WHERE game_id = ? AND chat_id = ?",
                    (new_hand, game_id, pch),
                )
                owner = _player_label(puname, pch, db=db, tenant_id=tid)
                for dc in discarded_cards:
                    _insert_mind_move(
                        db,
                        game_id=str(game_id),
                        chat_id=str(pch or ""),
                        username=str(puname or ""),
                        move_type="discarded",
                        card_value=int(dc),
                        level=int(current_level or 1),
                    )
                    discarded_notes.append(f"{owner} tenía el {dc} (descartado)")
                    discarded_count += 1
            db.execute(
                "UPDATE the_mind_games SET lives = ? WHERE game_id = ?",
                (new_lives, game_id),
            )
            _insert_mind_move(
                db,
                game_id=str(game_id),
                chat_id=cid,
                username=uname or "",
                move_type="play_error_life_lost",
                card_value=num,
                level=int(current_level or 1),
            )
            if new_lives <= 0:
                db.execute("UPDATE the_mind_games SET status = 'lost' WHERE game_id = ?", (game_id,))

            hands_after_penalty = list(
                db.execute("SELECT cards FROM the_mind_players WHERE game_id = ?", (game_id,))
            )
            level_done_after_penalty = all(len(list(h[0] or [])) == 0 for h in hands_after_penalty)
            lvl_now = int(current_level or 1)
            _mind_tx_commit(db)
            try:
                _obs = get_obs_logger("duckclaw.fly")
                log_fly(
                    _obs,
                    "/play penalty -> game_id=%s actor=%s offender=%s discarded=%s lives=%s",
                    str(game_id),
                    _player_label_log(uname, cid, db=db, tenant_id=tid),
                    _player_label_log(offender_username, offender_chat, db=db, tenant_id=tid),
                    discarded_count,
                    new_lives,
                )
            except Exception:
                pass
            try:
                _ = discarded_notes
                broadcast_message_to_players(
                    db,
                    game_id,
                    f"💀 {uname_display} jugó el {num} pero {offender_name or 'unknown'} tenía el {offender_card or '?'} (descartado). "
                    f"Vidas restantes: {new_lives}",
                    exclude_chat_id=cid,
                )
                if new_lives <= 0:
                    broadcast_message_to_players(
                        db,
                        game_id,
                        f"💀 Game over. Llegaron al Nivel {int(current_level or 1)}. ¡Buen intento!",
                        exclude_chat_id=cid,
                    )
            except Exception:
                pass
            if new_lives <= 0:
                return (
                    f"💀 {uname_display} jugó el {num} pero {offender_name or 'unknown'} tenía el {offender_card or '?'} (descartado). "
                    f"Vidas restantes: {new_lives}\n"
                    f"💀 Game over. Llegaron al Nivel {int(current_level or 1)}. ¡Buen intento!"
                
                )
            if level_done_after_penalty:
                # Regla operativa: una penalización nunca avanza de nivel.
                # Si tras el descarte no quedan cartas, se reinicia el mismo nivel.
                next_lvl = lvl_now
                db.execute(
                    "UPDATE the_mind_games SET cards_played = ARRAY[]::INTEGER[] WHERE game_id = ?",
                    (game_id,),
                )
                try:
                    broadcast_message_to_players(
                        db,
                        game_id,
                        f"⚠️ Penalización en Nivel {lvl_now}. Reiniciando Nivel {next_lvl}...",
                        exclude_chat_id=cid,
                    )
                    deal_cards_for_level(db, game_id, next_lvl, exclude_chat_id=cid)
                except Exception:
                    pass
                try:
                    sender_rows = list(
                        db.execute(
                            "SELECT cards FROM the_mind_players WHERE game_id = ? AND chat_id = ? LIMIT 1",
                            (game_id, cid),
                        )
                    )
                    sender_hand = sorted(int(c) for c in list((sender_rows[0][0] if sender_rows else []) or []))
                except Exception:
                    sender_hand = []
                return (
                    f"💀 {uname_display} jugó el {num} pero {offender_name or 'unknown'} tenía el {offender_card or '?'} (descartado). "
                    f"Vidas restantes: {new_lives}\n"
                    f"⚠️ Penalización en Nivel {lvl_now}. Reiniciando Nivel {next_lvl}...\n"
                    + f"🃏 Tus nuevas cartas: {sender_hand}"
                
                )
            return (
                f"❌ ¡ERROR! {uname_display} jugó el {num}, pero {offender_name or 'unknown'} tenía una carta menor. "
                f"Pierden 1 vida. Vidas restantes: {new_lives}."
            

            )
        hand.remove(num)
        db.execute(
            "UPDATE the_mind_players SET cards = ? WHERE game_id = ? AND chat_id = ?",
            (hand, game_id, cid),
        )
        cards_played.append(num)
        cards_played_sorted = sorted(cards_played)
        db.execute(
            "UPDATE the_mind_games SET cards_played = ? WHERE game_id = ?",
            (cards_played_sorted, game_id),
        )
        _insert_mind_move(
            db,
            game_id=str(game_id),
            chat_id=cid,
            username=uname or "",
            move_type="play_ok",
            card_value=num,
            level=int(current_level or 1),
        )

        lvl_now = int(current_level or 1)
        hands_after = list(
            db.execute("SELECT cards FROM the_mind_players WHERE game_id = ?", (game_id,))
        )
        level_done = all(len(list(h[0] or [])) == 0 for h in hands_after)
        cards_remaining = sum(len(list(h[0] or [])) for h in hands_after)

        _mind_tx_commit(db)

        msg = (
            f"✅ {uname_display} jugó el {num}. Cartas jugadas en este nivel: {cards_played_sorted}."
        )
        try:
            broadcast_message_to_players(
                db,
                game_id,
                f"✅ {uname_display} jugó el {num}. "
                f"Mesa: {cards_played_sorted} | Cartas restantes: {cards_remaining}",
                exclude_chat_id=cid,
            )
        except Exception:
            pass

        if level_done:
            if lvl_now >= _THE_MIND_MAX_LEVEL:
                db.execute(
                    "UPDATE the_mind_games SET status = 'won' WHERE game_id = ?",
                    (game_id,),
                )
                broadcast_message_to_players(
                    db,
                    game_id,
                    f"🏆 ¡Victoria! Han completado los {_THE_MIND_MAX_LEVEL} niveles.",
                )
                msg += " 🏆 ¡Victoria final!"
            else:
                next_lvl = lvl_now + 1
                db.execute(
                    "UPDATE the_mind_games SET cards_played = ARRAY[]::INTEGER[] WHERE game_id = ?",
                    (game_id,),
                )
                broadcast_message_to_players(
                    db,
                    game_id,
                    f"🎉 ¡Nivel {lvl_now} superado! Subiendo al Nivel {next_lvl}...",
                    exclude_chat_id=cid,
                )
                deal_cards_for_level(db, game_id, next_lvl, exclude_chat_id=cid)
                try:
                    sender_rows = list(
                        db.execute(
                            "SELECT cards FROM the_mind_players WHERE game_id = ? AND chat_id = ? LIMIT 1",
                            (game_id, cid),
                        )
                    )
                    sender_hand = sorted(int(c) for c in list((sender_rows[0][0] if sender_rows else []) or []))
                except Exception:
                    sender_hand = []
                msg += (
                    f" 🎉 ¡Nivel {lvl_now} completado! Repartido el Nivel {next_lvl}.\n"
                    f"🃏 Tus nuevas cartas: {sender_hand}"
                )
            return msg

        return msg
    except Exception as e:
        try:
            _mind_tx_rollback(db)
        except Exception:
            pass
        return f"No se pudo registrar la jugada: {e}"


def execute_cards(db: Any, chat_id: Any, args: str) -> str:
    """/cards: muestra las cartas activas del jugador en su partida en curso."""
    _ = args
    try:
        _ensure_the_mind_schema(db)
        cid = str(chat_id).replace("'", "''")[:256]
        rows = list(
            db.execute(
                """
                SELECT p.cards
                FROM the_mind_players p
                JOIN the_mind_games g ON g.game_id = p.game_id
                WHERE p.chat_id = ? AND g.status = 'playing'
                ORDER BY g.rowid DESC
                LIMIT 1
                """,
                (cid,),
            )
        )
        if not rows:
            return "No estás en ninguna partida en curso."
        cards = list(rows[0][0] or [])
        if not cards:
            return "No te quedan cartas en este nivel."
        cards_sorted = sorted(int(c) for c in cards)
        return f"🃏 Tus cartas: {', '.join(str(c) for c in cards_sorted)}"
    except Exception as e:
        return f"No se pudo consultar tus cartas: {e}"
def execute_shuriken(
    db: Any,
    chat_id: Any,
    args: str,
    *,
    tenant_id: Any = None,
) -> str:
    """/shuriken: voto para usar estrella ninja. Se aplica cuando votan todos los jugadores activos."""
    _ = args
    try:
        _ensure_the_mind_schema(db)
        tid = str(tenant_id or "default").strip() or "default"
        cid = str(chat_id).replace("'", "''")[:256]
        rows = list(
            db.execute(
                """
                SELECT g.game_id, g.current_level, g.shurikens, g.status, p.username
                FROM the_mind_games g
                JOIN the_mind_players p ON p.game_id = g.game_id
                WHERE g.status = 'playing' AND p.chat_id = ?
                ORDER BY g.rowid DESC
                LIMIT 1
                """,
                (cid,),
            )
        )
        if not rows:
            return "No encontré ninguna partida en juego asociada a este chat."
        game_id, lvl, stars, status, uname = rows[0]
        if str(status or "").strip().lower() != "playing":
            return "La partida no está en juego."
        stars_i = int(stars or 0)
        if stars_i <= 0:
            return "No quedan estrellas disponibles."

        player_rows = list(
            db.execute("SELECT chat_id, username, cards FROM the_mind_players WHERE game_id = ?", (game_id,))
        )
        if not player_rows:
            return "No hay jugadores en esta partida."
        active_players = [(str(r[0] or ""), str(r[1] or ""), list(r[2] or [])) for r in player_rows]
        active_chat_ids = [p[0] for p in active_players if p[0]]
        if cid not in active_chat_ids:
            return "No estás registrado en esta partida."

        vote_rows = list(
            db.execute(
                """
                SELECT DISTINCT chat_id
                FROM the_mind_moves
                WHERE game_id = ? AND move_type = 'shuriken_vote' AND level = ?
                """,
                (game_id, int(lvl or 1)),
            )
        )
        votes = {str(v[0] or "") for v in vote_rows if v and v[0]}
        if cid not in votes:
            _insert_mind_move(
                db,
                game_id=str(game_id),
                chat_id=cid,
                username=str(uname or ""),
                move_type="shuriken_vote",
                level=int(lvl or 1),
            )
            votes.add(cid)

        active_set = {p[0] for p in active_players if p[0]}
        if votes >= active_set:
            discarded_parts: list[str] = []
            for pchat, puname, cards in active_players:
                if not cards:
                    continue
                lowest = min(cards)
                # Quitar una sola ocurrencia de la menor
                removed = False
                final_cards: list[int] = []
                for c in cards:
                    if not removed and c == lowest:
                        removed = True
                        continue
                    final_cards.append(c)
                db.execute(
                    "UPDATE the_mind_players SET cards = ? WHERE game_id = ? AND chat_id = ?",
                    (final_cards, game_id, pchat),
                )
                discarded_parts.append(
                    f"{_player_label(puname, pchat, db=db, tenant_id=tid)} descartó el {lowest}"
                )
                _insert_mind_move(
                    db,
                    game_id=str(game_id),
                    chat_id=str(pchat),
                    username=str(puname or ""),
                    move_type="shuriken_discard",
                    card_value=int(lowest),
                    level=int(lvl or 1),
                )
            new_stars = max(stars_i - 1, 0)
            db.execute("UPDATE the_mind_games SET shurikens = ? WHERE game_id = ?", (new_stars, game_id))
            try:
                broadcast_message_to_players(
                    db,
                    game_id,
                    f"⭐ Estrella usada. {', '.join(discarded_parts)}. Estrellas restantes: {new_stars}",
                    exclude_chat_id=cid,
                )
            except Exception:
                pass
            return (
                f"⭐ Estrella usada. {', '.join(discarded_parts)}. Estrellas restantes: {new_stars}"
            

            )
        actor = _player_label(uname, cid, db=db, tenant_id=tid)
        for pchat, puser, _ in active_players:
            if pchat and pchat != cid:
                send_telegram_dm(
                    pchat,
                    f"{actor} quiere usar la estrella. Envía /shuriken para confirmar.",
                    username=str(puser or ""),
                    db=db,
                    tenant_id=tid,
                )
        return "⭐ Voto registrado. Esperando a los demás..."
    except Exception as e:
        return f"No se pudo procesar /shuriken: {e}"


def handle_mind_command(
    db: Any,
    chat_id: Any,
    text: str,
    *,
    requester_id: Any = None,
    tenant_id: Any = None,
) -> Optional[str]:
    """Dispatch legacy Mind commands (tests / migración). No usado en producción."""
    from duckclaw.graphs.on_the_fly_commands import parse_command

    name, args = parse_command(text)
    if not name:
        return None
    if name == "start_mind":
        return execute_start_mind(
            db, chat_id, args, requester_id=requester_id, tenant_id=tenant_id
        )
    if name == "new_mind":
        return execute_new_game(
            db, chat_id, "the_mind", requester_id=requester_id, tenant_id=tenant_id
        )
    if name == "new_game":
        return execute_new_game(
            db, chat_id, args, requester_id=requester_id, tenant_id=tenant_id
        )
    if name == "join":
        return execute_join_game(
            db, chat_id, args, requester_id=requester_id, tenant_id=tenant_id
        )
    if name == "game":
        return execute_list_mind_games(
            db, chat_id, args, requester_id=requester_id, tenant_id=tenant_id
        )
    if name == "start_game":
        return execute_start_game(db, chat_id, args)
    if name == "deal":
        return execute_deal(db, chat_id, args)
    if name == "play":
        return execute_play_mind(db, chat_id, args, tenant_id=tenant_id)
    if name == "cards":
        return execute_cards(db, chat_id, args)
    if name == "shuriken":
        return execute_shuriken(db, chat_id, args, tenant_id=tenant_id)
    return None
